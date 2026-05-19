"""sb cancel -- cancel job(s), with confirmation."""

from __future__ import print_function

from .. import format, slurm
from ._common import confirm, emit_raw


def add_parser(subparsers):
    p = subparsers.add_parser("cancel", help="cancel job(s)")
    p.add_argument("jobid", nargs="*", help="job IDs to cancel")
    p.add_argument(
        "--all", action="store_true", help="cancel all of my jobs"
    )
    p.add_argument(
        "-y", "--yes", action="store_true", help="skip the confirmation prompt"
    )
    p.set_defaults(func=run)


def _my_job_ids():
    user = slurm.current_user()
    rows = slurm.run_table(
        "squeue", ["-h", "-u", user, "-o", "%i"], ["jobid"]
    )
    return [r["jobid"] for r in rows if r["jobid"]]


def run(args):
    if args.all and args.jobid:
        raise slurm.SlurmError("pass either job IDs or --all, not both")

    if args.all:
        targets = _my_job_ids()
        if not targets:
            print("You have no jobs to cancel.")
            return 0
    elif args.jobid:
        targets = args.jobid
    else:
        raise slurm.SlurmError("nothing to cancel: give job IDs or --all")

    scancel_args = list(targets)
    if emit_raw(args, "scancel", scancel_args):
        return 0

    label = ", ".join(targets)
    if not args.yes:
        prompt = "Cancel {0} job(s): {1}?".format(len(targets), label)
        if not confirm(prompt):
            print("Aborted; nothing cancelled.")
            return 1

    slurm.run("scancel", scancel_args)
    print(format.color(
        "Cancelled {0} job(s): {1}".format(len(targets), label), "green"
    ))
    return 0
