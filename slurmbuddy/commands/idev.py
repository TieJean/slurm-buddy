"""sb idev -- request an interactive compute node.

Builds an `srun --pty` (or `salloc`) invocation for an interactive shell on a
compute node -- a portable equivalent of TACC's `idev`, for the many clusters
that do not ship one. It does not call or depend on any site-specific tool.
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
    p.add_argument(
        "--set-email",
        metavar="ADDR",
        help="save a notification email address (and exit)",
    )
    p.add_argument(
        "--no-mail",
        action="store_true",
        help="do not send a start-of-job email for this run",
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
    """Resolve GPU, CPU, and memory.

    Returns (gpus, cpus, cpus_matched, mem_mb, mem_matched).

    On a GPU partition: default to a configured number of GPUs (capped to one
    node) and match BOTH CPUs and memory at the node's per-GPU ratio -- the
    most resources you can take without raising the bill under Delta's
    MAX_TRES accounting. Without this, Slurm's `DefMemPerCPU` fallback hands
    you ~1 GB/CPU regardless of GPU count, which OOMs anything that loads a
    big checkpoint into host RAM before sharding to GPUs.

    Explicit -g / -c / -m always win. `cpus_matched`/`mem_matched` are True
    only when that resource was auto-derived from the GPU count. `mem_mb` is
    None when memory should be left to Slurm (non-GPU partition, explicit
    --mem, or `chosen.mem` unreadable).
    """
    node_gpus = gres.total_count(chosen.gres_str) if chosen else 0
    try:
        node_cpus = int(chosen.cpus) if chosen else 0
    except (TypeError, ValueError):
        node_cpus = 0
    try:
        node_mem = int(chosen.mem) if chosen else 0  # MB, from sinfo %m
    except (TypeError, ValueError):
        node_mem = 0

    if not node_gpus:  # non-GPU partition
        cpus = args.cpus or int(config.get_scoped("idev", "cpus", "4"))
        return (args.gpus or 0), cpus, False, None, False

    if args.gpus is not None:
        gpus = args.gpus  # explicit: honored as-is, even if it spans nodes
    else:
        default = int(config.get_scoped("idev", "gpus", "4"))
        gpus = min(default, node_gpus)  # cap the default to a single node

    cpus_matched = False
    if args.cpus is not None:
        cpus = args.cpus
    elif gpus > 0 and node_cpus:
        cpus = (node_cpus // node_gpus) * gpus
        cpus_matched = True
    else:
        # GPU partition but CPU count unreadable -- fall back to default.
        cpus = int(config.get_scoped("idev", "cpus", "4"))

    mem_mb = None
    mem_matched = False
    if args.mem is None and gpus > 0 and node_mem:
        # Leave a per-node headroom before splitting across GPUs. Slurm
        # reserves a chunk of each node for the kernel + slurmd
        # (`MemSpecLimit`, ~8.5 GiB on Delta GPU nodes); asking for >
        # `RealMemory - MemSpecLimit` trips "Requested node configuration
        # is not available", which is the failure mode the `--mem` flag
        # is meant to prevent in the first place. 16 GiB is well above
        # the observed MemSpecLimit on Delta and is a small fraction of
        # any GPU node's RAM, so it costs effectively nothing.
        #
        # Rounding per-GPU down to whole GB after the headroom gives a
        # clean display (`--mem=1000G`-style rather than `--mem=1024096M`)
        # and absorbs any leftover MB into additional safety.
        node_headroom_mb = 16 * 1024
        usable = max(0, node_mem - node_headroom_mb)
        per_gpu_gb = (usable // node_gpus) // 1024
        if per_gpu_gb > 0:
            mem_mb = per_gpu_gb * 1024 * gpus
            mem_matched = True

    return gpus, cpus, cpus_matched, mem_mb, mem_matched


def _resolve_email(args):
    """Resolve the notification email. Returns (address_or_None, source_note).

    Order: $SLURM_EMAIL env var > [idev] email in config > an interactive
    prompt (the answer is saved to ~/.config/slurm-buddy/config.ini, so the
    prompt appears only once). The email never lives in the repo.
    """
    if args.no_mail:
        return None, None
    env = os.environ.get("SLURM_EMAIL")
    if env:
        return env, "$SLURM_EMAIL"
    cfg = config.get_scoped("idev", "email")
    if cfg:
        return cfg, "config"
    if not sys.stdin.isatty():  # cannot prompt -- skip mail silently
        return None, None
    try:
        entered = input("notification email for SLURM (blank to skip): ").strip()
    except EOFError:
        return None, None
    if not entered:
        return None, None
    config.set_user_value("idev", "email", entered)
    return entered, "config (saved)"


def run(args):
    # --set-email is a management action: save the address and exit.
    if args.set_email:
        config.set_user_value("idev", "email", args.set_email)
        print(
            format.color("saved notification email: ", "bold")
            + args.set_email
            + "  " + format.color("(~/.config/slurm-buddy/config.ini)", "dim")
        )
        return 0

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

    gpus, cpus, cpus_matched, mem_mb, mem_matched = _resolve_resources(args, chosen)
    email, email_src = _resolve_email(args)

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
    elif mem_mb:
        common.append("--mem={0}M".format(mem_mb))
    if email:
        common += ["--mail-type=BEGIN", "--mail-user=" + email]

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
    if mem_matched:
        mem_str = format.humanize_mem(mem_mb)
        per_gpu = format.humanize_mem(mem_mb // gpus)
        print(
            format.color("memory: ", "bold")
            + mem_str
            + "  " + format.color(
                "({0}/GPU -- matched to node ratio)".format(per_gpu),
                "dim",
            )
        )
    elif args.mem:
        print(format.color("memory: ", "bold") + args.mem)
    if email:
        print(
            format.color("notify: ", "bold")
            + "email on job start -> " + email
            + "  " + format.color("(from " + email_src + ")", "dim")
        )
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
