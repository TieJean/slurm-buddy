"""sb eta -- estimated start time for pending job(s)."""

from __future__ import print_function

from .. import format, slurm
from ._common import emit_raw

_COLUMNS = ["jobid", "name", "state", "start", "reason"]
_HEADERS = ["JOBID", "NAME", "STATE", "EST. START", "REASON"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "eta", help="estimated start time for pending jobs"
    )
    p.add_argument("jobid", nargs="+", help="one or more job IDs")
    p.set_defaults(func=run)


def run(args):
    joined = ",".join(args.jobid)
    squeue_args = [
        "--start", "-j", joined, "-h", "-o", "%i|%j|%T|%S|%r",
    ]
    if emit_raw(args, "squeue", squeue_args):
        return 0

    # check=False: an invalid job ID makes squeue exit 1, but valid IDs in
    # the same call still print -- tolerate it and parse what we got.
    rows = slurm.run_table(
        "squeue",
        squeue_args,
        ["jobid", "name", "state", "start", "reason"],
        check=False,
    )

    found = {r["jobid"] for r in rows}
    missing = [j for j in args.jobid if j not in found]

    if not rows:
        print("No pending jobs found for: {0}".format(joined))
        print(format.color(
            "Jobs that are already running or finished have no start estimate.",
            "dim",
        ))
        return 1

    display = []
    for r in rows:
        start = r["start"]
        if not start or start.upper() in ("N/A", "(NULL)"):
            start = "unknown"
        display.append(
            {
                "jobid": r["jobid"],
                "name": r["name"][:24],
                "state": r["state"],
                "start": start,
                "reason": r["reason"],
            }
        )

    print(format.render_table(display, _COLUMNS, _HEADERS))
    print()
    print(format.color(
        "Estimates are best-effort and shift as the queue changes.", "dim"
    ))
    if missing:
        print(format.color(
            "Not pending (running/done/unknown): {0}".format(
                ", ".join(missing)
            ),
            "yellow",
        ))
    return 0
