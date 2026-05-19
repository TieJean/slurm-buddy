"""sb history -- recent finished jobs with exit codes and elapsed time."""

from __future__ import print_function

from .. import config, format, slurm
from ._common import emit_raw

_FMT = "JobID,JobName,Partition,State,ExitCode,Elapsed,Start"
_COLS = ["jobid", "name", "partition", "state", "exitcode", "elapsed", "start"]
_HEADERS = ["JOBID", "NAME", "PARTITION", "STATE", "EXIT", "ELAPSED", "START"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "history", help="recent finished jobs and their exit codes"
    )
    p.add_argument(
        "-d", "--days", type=int,
        help="look back this many days (default from config)",
    )
    p.set_defaults(func=run)


def _state_color(state):
    base = state.split()[0] if state else state
    if base == "COMPLETED":
        return format.color(state, "green")
    if base in ("FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"):
        return format.color(state, "red")
    if base == "CANCELLED":
        return format.color(state, "yellow")
    return state


def run(args):
    days = args.days or int(config.get("history", "days", "7"))
    sacct_args = [
        "-X", "-P", "-n",
        "-S", "now-{0}days".format(days),
        "-o", _FMT,
    ]
    if emit_raw(args, "sacct", sacct_args):
        return 0

    rows = slurm.run_table("sacct", sacct_args, _COLS)
    if not rows:
        print("No finished jobs in the last {0} day(s).".format(days))
        return 0

    for r in rows:
        r["name"] = r["name"][:24]
        r["state"] = _state_color(r["state"])

    print(format.color(
        "finished jobs, last {0} day(s)".format(days), "bold"
    ))
    print()
    print(format.render_table(rows, _COLS, _HEADERS))
    return 0
