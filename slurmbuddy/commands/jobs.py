"""sb jobs -- show running and pending jobs."""

from __future__ import print_function

from .. import format, slurm
from ._common import emit_raw

_FMT = "%i|%j|%T|%P|%M|%l|%D|%R"
_COLS = ["jobid", "name", "state", "partition", "used", "limit", "nodes", "reason"]
_HEADERS = ["JOBID", "NAME", "STATE", "PARTITION", "USED", "LIMIT", "NODES", "REASON/NODELIST"]


def add_parser(subparsers):
    p = subparsers.add_parser("jobs", help="show my (or another user's) jobs")
    p.add_argument("-u", "--user", help="show jobs for this user")
    p.add_argument(
        "-a", "--all", action="store_true", help="show all users' jobs"
    )
    p.set_defaults(func=run)


def run(args):
    squeue_args = ["-h", "-o", _FMT]
    if args.all:
        scope = "all users"
    else:
        user = args.user or slurm.current_user()
        squeue_args += ["-u", user]
        scope = user
    if emit_raw(args, "squeue", squeue_args):
        return 0

    rows = slurm.run_table("squeue", squeue_args, _COLS)
    if not rows:
        print("No jobs in queue for {0}.".format(scope))
        return 0

    for r in rows:
        r["name"] = r["name"][:24]
        r["reason"] = r["reason"][:28]

    print(format.render_table(rows, _COLS, _HEADERS))
    print()
    n_run = sum(1 for r in rows if r["state"] == "RUNNING")
    n_pend = sum(1 for r in rows if r["state"] == "PENDING")
    print(format.color(
        "{0} job(s) for {1}: {2} running, {3} pending".format(
            len(rows), scope, n_run, n_pend
        ),
        "dim",
    ))
    return 0
