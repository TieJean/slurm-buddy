"""sb idev -- request an interactive compute node.

This is the Delta replacement for TACC's `idev`: Delta has no `idev` command,
so this builds the equivalent `srun --pty` (or `salloc`) invocation.
"""

from __future__ import print_function

import os
import re
import sys

from .. import config, format, gres, partitions, slurm
from . import whoami

# srun --test-only prints e.g. "Job 1 to start at 2026-05-19T15:00:00 using ..."
_START_AT_RE = re.compile(r"to start at (\S+)")
# Env vars that carry an account into the current shell/job.
_ACCOUNT_ENV = ("SLURM_ACCOUNT", "SALLOC_ACCOUNT", "SBATCH_ACCOUNT")


def add_parser(subparsers):
    p = subparsers.add_parser(
        "idev", help="request an interactive compute node"
    )
    p.add_argument("-p", "--partition", help="partition (default from config)")
    p.add_argument("-t", "--time", help="walltime, e.g. 1:00:00")
    p.add_argument("-c", "--cpus", type=int, help="CPUs per task")
    p.add_argument("-g", "--gpus", type=int, help="GPUs to request")
    p.add_argument("-N", "--nodes", type=int, help="number of nodes")
    p.add_argument("-m", "--mem", help="memory, e.g. 16G")
    p.add_argument("-A", "--account", help="account to charge")
    p.add_argument(
        "--salloc",
        action="store_true",
        help="use salloc instead of srun --pty",
    )
    p.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="print the command without launching",
    )
    p.set_defaults(func=run)


def _resolve_account(requested):
    """Resolve the account to charge. Returns (account, note).

    Priority: --account flag > [idev] account in config > $SLURM_ACCOUNT /
    $SALLOC_ACCOUNT / $SBATCH_ACCOUNT > the user's SLURM default account >
    a sole association. `note` explains where the value came from. Raises
    SlurmError only when no account can be found at all.
    """
    if requested:
        return requested, "from -A"

    cfg = config.get_scoped("idev", "account")
    if cfg:
        return cfg, "from config"

    for var in _ACCOUNT_ENV:
        val = os.environ.get(var)
        if val:
            return val, "from $" + var

    accounts = whoami.user_accounts()
    default = whoami.default_account()
    if default:
        others = [a for a in accounts if a != default]
        if others:
            note = "SLURM default; you also have {0} -- use -A to switch".format(
                ", ".join(others)
            )
        else:
            note = "your SLURM default"
        return default, note

    if len(accounts) == 1:
        return accounts[0], "your only account"
    if not accounts:
        raise slurm.SlurmError(
            "no SLURM account found; pass -A/--account explicitly"
        )
    raise slurm.SlurmError(
        "could not determine your account; pick one with -A ({0})".format(
            ", ".join(accounts)
        )
    )


def _estimate_start(common):
    """Best-effort estimated start time for a job with these resource args.

    Uses `srun --test-only`, which validates and estimates a start time
    WITHOUT submitting or running anything.
    """
    try:
        out = slurm.run_combined("srun", ["--test-only"] + common + ["true"])
    except slurm.SlurmError as exc:
        return "could not estimate ({0})".format(exc)
    match = _START_AT_RE.search(out)
    if match:
        return match.group(1)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else "unknown"


def _resolve_resources(args, chosen):
    """Resolve GPU and CPU counts. Returns (gpus, cpus, cpus_matched).

    On a GPU partition: default to a configured number of GPUs (capped to one
    node) and match CPUs at the node's cores-per-GPU ratio -- the most CPUs you
    can take without raising the bill under Delta's MAX_TRES accounting.
    Explicit -g / -c always win; `cpus_matched` is True only when CPUs were
    auto-derived from the GPU count.
    """
    node_gpus = gres.total_count(chosen.gres_str) if chosen else 0
    try:
        node_cpus = int(chosen.cpus) if chosen else 0
    except (TypeError, ValueError):
        node_cpus = 0

    if not node_gpus:  # non-GPU partition
        cpus = args.cpus or int(config.get_scoped("idev", "cpus", "4"))
        return (args.gpus or 0), cpus, False

    if args.gpus is not None:
        gpus = args.gpus  # explicit: honored as-is, even if it spans nodes
    else:
        default = int(config.get_scoped("idev", "gpus", "4"))
        gpus = min(default, node_gpus)  # cap the default to a single node

    if args.cpus is not None:
        return gpus, args.cpus, False
    if gpus > 0 and node_cpus:
        return gpus, (node_cpus // node_gpus) * gpus, True
    # GPU partition but resources unreadable -- fall back to the CPU default.
    return gpus, int(config.get_scoped("idev", "cpus", "4")), False


def run(args):
    # partition is cluster-specific: no hardcoded fallback, only -p or the
    # cluster-scoped [idev.<cluster>] config section.
    partition = args.partition or config.get_scoped("idev", "partition")
    time = args.time or config.get_scoped("idev", "time", "1:00:00")
    nodes = args.nodes or int(config.get_scoped("idev", "nodes", "1"))
    account, acct_note = _resolve_account(args.account)

    if not partition:
        raise slurm.SlurmError(
            "no interactive partition configured for this cluster ({0}); "
            "pass -p, or add a 'partition' to an [idev.{0}] section in "
            "~/.config/slurm-buddy/config.ini".format(
                slurm.cluster_name() or "unknown"
            )
        )

    # One sinfo query feeds both the interactive check and the time-limit check.
    try:
        parts = partitions.list_partitions()
    except slurm.SlurmError:
        parts = []
    interactive = sorted({p.name for p in parts if p.is_interactive})
    chosen = next((p for p in parts if p.name == partition), None)

    # Validate the partition is interactive; suggest a fix if not.
    if interactive and partition not in interactive:
        suggestion = partitions.suggest_interactive(partition)
        msg = "'{0}' is not an interactive partition.".format(partition)
        if suggestion:
            msg += " Did you mean '{0}'? Use -p to set it.".format(suggestion)
        else:
            msg += " Interactive partitions: {0}".format(
                ", ".join(interactive)
            )
        sys.stderr.write(format.color("warning: ", "yellow") + msg + "\n")

    # Reject a walltime over the partition's limit up front -- clearer than
    # srun's "Requested time limit is invalid" message.
    if chosen:
        limit_s = format.duration_seconds(chosen.timelimit)
        want_s = format.duration_seconds(time)
        if limit_s is not None and want_s is not None and want_s > limit_s:
            raise slurm.SlurmError(
                "requested time {0} exceeds the {1} limit of partition "
                "'{2}'. Lower -t, or pick a partition with a longer limit "
                "(see `sb queues`).".format(
                    time, format.humanize_time(chosen.timelimit), partition
                )
            )

    if slurm.is_compute_node():
        sys.stderr.write(
            format.color("warning: ", "yellow")
            + "you already appear to be inside a SLURM allocation.\n"
        )

    gpus, cpus, cpus_matched = _resolve_resources(args, chosen)

    shell = os.environ.get("SHELL", "/bin/bash")
    common = [
        "--account=" + account,
        "--partition=" + partition,
        "--nodes={0}".format(nodes),
        "--time=" + time,
        "--cpus-per-task={0}".format(cpus),
    ]
    if gpus:
        common.append("--gpus={0}".format(gpus))
    if args.mem:
        common.append("--mem=" + args.mem)

    if args.salloc:
        argv = ["salloc"] + common
    else:
        argv = ["srun"] + common + ["--tasks-per-node=1", "--pty", shell]

    print(
        format.color("account: ", "bold")
        + account
        + "  " + format.color("(" + acct_note + ")", "dim")
    )
    if gpus:
        res = "{0} GPU, {1} CPU".format(gpus, cpus)
        if cpus_matched:
            res += "  " + format.color(
                "({0} cores/GPU -- max CPUs at no extra billing)".format(
                    cpus // gpus
                ),
                "dim",
            )
        print(format.color("resources: ", "bold") + res)
    print(format.color("$ " + slurm.render_command(argv[0], argv[1:]), "cyan"))

    if args.dry_run or getattr(args, "raw", False):
        if args.dry_run:
            est = _estimate_start(common)
            # A bare ISO timestamp is a real estimate; anything else is a
            # validation message worth highlighting.
            if not re.match(r"\d{4}-\d\d-\d\dT", est):
                est = format.color(est, "yellow")
            print(
                format.color("est. start: ", "bold") + est
                + "  " + format.color("(srun --test-only; best-effort)", "dim")
            )
        return 0

    print(format.color("Requesting node... (Ctrl-C to give up)", "dim"))
    slurm.exec_replace(argv)  # replaces this process; does not return
