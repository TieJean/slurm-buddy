"""sb attach -- open a shell on a node already allocated to one of your jobs.

For workflows where the original job runs detached (sbatch, or `sb idev`
without --salloc): the allocation is up on a compute node, but you still
need a way onto it. This command picks the right job/node and hands you
a shell on it.

Default mode runs `srun --overlap --jobid=<id> --pty $SHELL`, which adds a
job step inside your existing allocation -- cwd is preserved natively and
the step is properly accounted to the job. --overlap is required so the
shell step doesn't block waiting for CPUs/GPUs already held by the primary
step (e.g. a training run pinning all GRES). With --ssh, opens a regular
ssh session into the node instead (relies on pam_slurm_adopt to drop you
in the job's cgroup); cwd is forwarded explicitly so you land where you
started.
"""

from __future__ import print_function

import os

from .. import format, slurm
from ._common import emit_raw

# squeue format: jobid | state | nodelist (used to pick the target).
_RUNNING_FMT = "%i|%T|%N"


def add_parser(subparsers):
    p = subparsers.add_parser(
        "attach",
        help="open a shell on a node allocated to one of your running jobs",
    )
    p.add_argument(
        "jobid", nargs="?",
        help="job ID to attach to (default: your only running job)",
    )
    p.add_argument(
        "--ssh", action="store_true",
        help="use `ssh` into the node instead of `srun --jobid=... --pty`",
    )
    p.add_argument(
        "--node",
        help="for multi-node jobs, the specific node to attach to "
             "(default: first node in the allocation)",
    )
    p.add_argument(
        "--cwd", metavar="DIR",
        help="directory to land in on the node (default: current directory)",
    )
    p.add_argument(
        "-n", "--dry-run", action="store_true",
        help="print the command without launching",
    )
    p.set_defaults(func=run)


def _running_jobs():
    """Return list of {jobid,state,node} for the current user's running jobs."""
    user = slurm.current_user()
    return slurm.run_table(
        "squeue",
        ["-h", "-u", user, "-t", "R", "-o", _RUNNING_FMT],
        ["jobid", "state", "node"],
    )


def _expand_nodelist(nodelist):
    """Expand a SLURM nodelist (e.g. 'gpub[001-003]') to a list of hostnames."""
    try:
        out = slurm.run("scontrol", ["show", "hostnames", nodelist])
    except slurm.SlurmError:
        # Fall back to the compact form if scontrol is unhappy -- harmless
        # for single-node jobs where the compact form is already a hostname.
        return [nodelist]
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _resolve_target(args):
    """Resolve (jobid, node) from args. Picks first node unless --node given."""
    rows = _running_jobs()
    if args.jobid:
        match = next((r for r in rows if r["jobid"] == args.jobid), None)
        if not match:
            raise slurm.SlurmError(
                "job {0} is not in your running jobs (see `sb jobs`)".format(
                    args.jobid
                )
            )
    else:
        if not rows:
            raise slurm.SlurmError(
                "you have no running jobs to attach to (see `sb jobs`)"
            )
        if len(rows) > 1:
            listing = "\n  ".join(
                "{0}  {1}".format(r["jobid"], r["node"]) for r in rows
            )
            raise slurm.SlurmError(
                "multiple running jobs; pass a JOBID to pick one:\n  " + listing
            )
        match = rows[0]

    hosts = _expand_nodelist(match["node"])
    if args.node:
        if args.node not in hosts:
            raise slurm.SlurmError(
                "node '{0}' is not in job {1}'s allocation ({2})".format(
                    args.node, match["jobid"], ", ".join(hosts)
                )
            )
        node = args.node
    else:
        node = hosts[0]
        if len(hosts) > 1:
            print(format.color(
                "note: job spans {0} nodes ({1}); attaching to {2} -- "
                "use --node to pick another.".format(
                    len(hosts), ", ".join(hosts), node
                ),
                "dim",
            ))
    return match["jobid"], node


def _sh_quote(s):
    """Single-quote a string for safe inclusion in a remote shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def run(args):
    jobid, node = _resolve_target(args)
    shell = os.environ.get("SHELL", "/bin/bash")
    cwd = args.cwd or os.getcwd()

    if args.ssh:
        # Forward cwd via the remote command; 2>/dev/null so a missing dir
        # falls back to $HOME instead of erroring out.
        remote = "cd {0} 2>/dev/null; exec {1} -l".format(
            _sh_quote(cwd), _sh_quote(shell)
        )
        argv = ["ssh", "-t", node, remote]
        cmd_name = "ssh"
    else:
        # --overlap lets this step share resources with the primary step,
        # otherwise srun blocks waiting for free CPUs/GPUs when the job is
        # already pinning all of its GRES. --chdir preserves cwd on the node
        # even when nodelist routing would otherwise reset it; --jobid
        # attaches to the existing alloc.
        srun_args = [
            "--overlap",
            "--jobid={0}".format(jobid),
            "--chdir=" + cwd,
            "--pty",
            shell,
        ]
        if args.node:
            srun_args = ["--nodelist=" + args.node] + srun_args
        argv = ["srun"] + srun_args
        cmd_name = "srun"

    if emit_raw(args, cmd_name, argv[1:]):
        return 0

    print(
        format.color("attaching to job ", "bold")
        + jobid + " on " + format.color(node, "cyan")
    )
    print(format.color("$ " + slurm.render_command(argv[0], argv[1:]), "cyan"))

    if args.dry_run:
        return 0

    slurm.exec_replace(argv)  # replaces this process; does not return
