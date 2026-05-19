"""sb idev -- request an interactive compute node.

This is the Delta replacement for TACC's `idev`: Delta has no `idev` command,
so this builds the equivalent `srun --pty` (or `salloc`) invocation.
"""

from __future__ import print_function

import os
import sys

from .. import config, format, partitions, slurm
from . import whoami


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
    """Pick an account: explicit flag > config > sole association."""
    if requested:
        return requested
    cfg = config.get("idev", "account")
    if cfg:
        return cfg
    accounts = whoami.user_accounts()
    if len(accounts) == 1:
        return accounts[0]
    if not accounts:
        raise slurm.SlurmError(
            "no SLURM account found; pass --account explicitly"
        )
    raise slurm.SlurmError(
        "multiple accounts available ({0}); pick one with --account".format(
            ", ".join(accounts)
        )
    )


def run(args):
    partition = args.partition or config.get(
        "idev", "partition", "cpu-interactive"
    )
    time = args.time or config.get("idev", "time", "1:00:00")
    cpus = args.cpus or int(config.get("idev", "cpus", "4"))
    nodes = args.nodes or int(config.get("idev", "nodes", "1"))
    account = _resolve_account(args.account)

    # Validate the partition is interactive; suggest a fix if not.
    try:
        interactive = partitions.interactive_partitions()
    except slurm.SlurmError:
        interactive = []
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

    if slurm.is_compute_node():
        sys.stderr.write(
            format.color("warning: ", "yellow")
            + "you already appear to be inside a SLURM allocation.\n"
        )

    shell = os.environ.get("SHELL", "/bin/bash")
    common = [
        "--account=" + account,
        "--partition=" + partition,
        "--nodes={0}".format(nodes),
        "--time=" + time,
        "--cpus-per-task={0}".format(cpus),
    ]
    if args.gpus:
        common.append("--gpus={0}".format(args.gpus))
    if args.mem:
        common.append("--mem=" + args.mem)

    if args.salloc:
        argv = ["salloc"] + common
    else:
        argv = ["srun"] + common + ["--tasks-per-node=1", "--pty", shell]

    print(format.color("$ " + slurm.render_command(argv[0], argv[1:]), "cyan"))

    if args.dry_run or getattr(args, "raw", False):
        return 0

    print(format.color("Requesting node... (Ctrl-C to give up)", "dim"))
    slurm.exec_replace(argv)  # replaces this process; does not return
