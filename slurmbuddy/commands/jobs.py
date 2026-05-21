"""sb jobs -- show running and pending jobs."""

from __future__ import print_function

import re

from .. import format, slurm
from ._common import emit_raw

_FMT = "%i|%j|%T|%P|%M|%l|%L|%D|%S|%R"
_COLS = ["jobid", "name", "state", "partition", "used", "limit", "remaining",
         "nodes", "eta", "reason"]
_HEADERS = ["JOBID", "NAME", "STATE", "PARTITION", "USED", "LIMIT", "REMAINING",
            "NODES", "EST. START", "REASON/NODELIST"]

# srun --test-only prints "Job N to start at <ISO timestamp> using ..." on stderr.
_START_AT_RE = re.compile(r"to start at (\S+)")


def _scontrol_show_job(jobid):
    """Parse `scontrol show job <jobid>` into a flat dict of key=value tokens.

    scontrol prints space-separated `Key=Value` pairs; first occurrence wins.
    Values are returned as opaque strings -- callers extract what they need.
    Returns {} on error so callers can degrade silently.
    """
    try:
        out = slurm.run("scontrol", ["show", "job", jobid], check=False)
    except slurm.SlurmError:
        return {}
    fields = {}
    for line in out.splitlines():
        for tok in line.strip().split():
            k, sep, v = tok.partition("=")
            if sep and k not in fields:
                fields[k] = v
    return fields


def _test_only_estimate(jobid):
    """Best-effort upper-bound start time for a pending job via srun --test-only.

    SLURM's backfill scheduler only writes StartTime for jobs it evaluates
    within its per-cycle limits (bf_max_job_test, bf_max_job_user, bf_window);
    a freshly-submitted job often shows StartTime=Unknown for a few cycles
    even when a slot exists. We replay the job's specs through `srun
    --test-only`, which runs the simulator on demand and returns synchronously.

    The result is an UPPER BOUND: --test-only simulates a *fresh* submission,
    so it ignores the priority the real job has accrued. The real job can
    only start earlier, never later. Caller is expected to label it as such.
    Returns the ISO timestamp string or None.
    """
    f = _scontrol_show_job(jobid)
    account = f.get("Account")
    partition = f.get("Partition")
    timelimit = f.get("TimeLimit")
    if not (account and partition and timelimit):
        return None
    # NumNodes is rendered as "min-max"; take the minimum so we ask for the
    # same shape the user originally requested.
    nodes = f.get("NumNodes", "1").split("-")[0]
    args = [
        "--test-only",
        "--account=" + account,
        "--partition=" + partition,
        "--nodes=" + nodes,
        "--time=" + timelimit,
        "--cpus-per-task=" + f.get("CPUs/Task", "1"),
        "--ntasks=" + f.get("NumTasks", "1"),
    ]
    req_tres = f.get("ReqTRES", "")
    mem = re.search(r"(?:^|,)mem=([^,]+)", req_tres)
    if mem:
        args.append("--mem=" + mem.group(1))
    gpus = re.search(r"gres/gpu=(\d+)", req_tres)
    if gpus:
        args.append("--gpus=" + gpus.group(1))
    args.append("true")
    try:
        out = slurm.run_combined("srun", args)
    except slurm.SlurmError:
        return None
    m = _START_AT_RE.search(out)
    return m.group(1) if m else None


def _interactive_jobids(scope_args):
    """Return the set of job IDs whose BatchFlag is 0 (interactive).

    Uses a separate `squeue -O BatchFlag` call because the short `-o` format
    has no batch-flag code. Failures degrade to an empty set, so the main
    listing still renders.
    """
    args = ["-h", "-O", "JobID:|,BatchFlag:|"] + list(scope_args)
    try:
        rows = slurm.run_table(
            "squeue", args, ["jobid", "batchflag"], check=False,
        )
    except slurm.SlurmError:
        return set()
    return {r["jobid"] for r in rows if r["batchflag"] == "0"}


def add_parser(subparsers):
    p = subparsers.add_parser("jobs", help="show my (or another user's) jobs")
    p.add_argument("-u", "--user", help="show jobs for this user")
    p.add_argument(
        "-a", "--all", action="store_true", help="show all users' jobs"
    )
    p.set_defaults(func=run)


def run(args):
    squeue_args = ["-h", "-o", _FMT]
    scope_args = []
    if args.all:
        scope = "all users"
    else:
        user = args.user or slurm.current_user()
        scope_args = ["-u", user]
        squeue_args += scope_args
        scope = user
    if emit_raw(args, "squeue", squeue_args):
        return 0

    rows = slurm.run_table("squeue", squeue_args, _COLS)
    if not rows:
        print("No jobs in queue for {0}.".format(scope))
        return 0

    interactive = _interactive_jobids(scope_args)

    # Test-only fallback shells out to srun, which many sites (TACC) reject
    # from compute nodes. Skip the fallback in that case to avoid noisy
    # failures and wasted latency.
    can_estimate = not slurm.is_compute_node()
    have_upper_bound = False
    for r in rows:
        r["name"] = r["name"][:24]
        r["reason"] = r["reason"][:28]
        # An estimated start time is only meaningful for pending jobs; for
        # running/completing jobs %S is the actual (past) start time.
        if r["state"] == "PENDING":
            start = r["eta"]
            if not start or start.upper() in ("N/A", "(NULL)"):
                # Slurm has no backfill estimate yet; synthesize an upper
                # bound via srun --test-only (see _test_only_estimate).
                est = _test_only_estimate(r["jobid"]) if can_estimate else None
                if est:
                    r["eta"] = "~" + est
                    have_upper_bound = True
                else:
                    r["eta"] = "unknown"
        else:
            r["eta"] = "-"
        # Remaining time is most useful for interactive jobs you're actively
        # sitting in -- batch users can read USED/LIMIT. Hide it elsewhere to
        # keep the column quiet for the common case.
        if r["state"] == "RUNNING" and r["jobid"] in interactive:
            rem = r["remaining"]
            if not rem or rem.upper() in ("N/A", "(NULL)", "INFINITE", "UNLIMITED"):
                r["remaining"] = "-"
        else:
            r["remaining"] = "-"

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
    if n_pend:
        print(format.color(
            "Estimated start times are best-effort and shift as the queue "
            "changes.", "dim",
        ))
    if have_upper_bound:
        print(format.color(
            "Times prefixed with '~' are upper bounds from srun --test-only "
            "(SLURM had no estimate yet); the real start is no later.", "dim",
        ))
    return 0
