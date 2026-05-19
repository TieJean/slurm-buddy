"""sb history -- recent finished jobs, and a post-mortem for a single job."""

from __future__ import print_function

import os

from .. import config, format, slurm
from ._common import emit_raw

_FMT = "JobID,JobName,Partition,State,ExitCode,Elapsed,Start"
_COLS = ["jobid", "name", "partition", "state", "exitcode", "elapsed", "start"]
_HEADERS = ["JOBID", "NAME", "PARTITION", "STATE", "EXIT", "ELAPSED", "START"]

# Fields for the single-job post-mortem.
_DETAIL_FMT = ("JobID,JobName,State,ExitCode,DerivedExitCode,Elapsed,"
               "NodeList,WorkDir,SubmitLine,StdErr,StdOut")
_DETAIL_COLS = ["jobid", "name", "state", "exitcode", "derived", "elapsed",
                "nodelist", "workdir", "submitline", "stderr", "stdout"]

_SIGNALS = {
    2: "SIGINT", 6: "SIGABRT", 8: "SIGFPE",
    9: "SIGKILL -- often the OOM-killer or scancel",
    11: "SIGSEGV", 15: "SIGTERM",
}

_TAIL_LINES = 25
_TAIL_BYTES = 65536


def add_parser(subparsers):
    p = subparsers.add_parser(
        "history", help="recent finished jobs, or a post-mortem for one job"
    )
    p.add_argument(
        "jobid", nargs="?",
        help="show a post-mortem (status, exit code, error output) for a job",
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


def _decode_exit(code):
    """Render a SLURM 'exit:signal' code as a human-readable phrase."""
    if not code or ":" not in code:
        return code or "-"
    exit_s, _, sig_s = code.partition(":")
    try:
        exit_n, sig_n = int(exit_s), int(sig_s)
    except ValueError:
        return code
    if sig_n:
        return "{0}  (killed by {1})".format(
            code, _SIGNALS.get(sig_n, "signal {0}".format(sig_n)))
    if exit_n:
        return "{0}  (exited with status {1})".format(code, exit_n)
    return "{0}  (clean)".format(code)


def _tail(path):
    """Return the last lines of a file, reading only its tail (huge logs OK).

    Returns None if the path is empty, unresolved, or unreadable.
    """
    if not path or "%" in path:  # no file, or an unexpanded %j/%x pattern
        return None
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            read = min(size, _TAIL_BYTES)
            fh.seek(size - read)
            data = fh.read(read)
    except (IOError, OSError):
        return None
    lines = data.decode("utf-8", "replace").splitlines()
    if read < size and len(lines) > 1:
        lines = lines[1:]  # first line is likely truncated
    return lines[-_TAIL_LINES:]


def _detail(args):
    """Post-mortem for a single job: status, exit code, and error output."""
    sacct_args = ["-j", args.jobid, "-P", "-n", "-o", _DETAIL_FMT]
    if emit_raw(args, "sacct", sacct_args):
        return 0

    rows = slurm.run_table("sacct", sacct_args, _DETAIL_COLS)
    # sacct emits the job plus its steps (.batch/.extern/...); use the
    # top-level job row for job-wide fields.
    main = next((r for r in rows if r["jobid"] == args.jobid), None)
    if main is None and rows:
        main = rows[0]
    if main is None:
        print("No job {0} in the accounting records.".format(args.jobid))
        return 1

    pairs = [
        ("job", main["jobid"]),
        ("name", main["name"] or "-"),
        ("state", _state_color(main["state"])),
        ("exit code", _decode_exit(main["exitcode"])),
    ]
    if main["derived"] and main["derived"] not in (main["exitcode"], "0:0"):
        pairs.append(("derived exit", _decode_exit(main["derived"])))
    pairs += [
        ("elapsed", main["elapsed"] or "-"),
        ("nodes", main["nodelist"] or "-"),
        ("workdir", main["workdir"] or "-"),
        ("submitted", main["submitline"] or "-"),
        ("stderr file", main["stderr"] or "(none)"),
    ]
    if main["stdout"] and main["stdout"] != main["stderr"]:
        pairs.append(("stdout file", main["stdout"]))
    print(format.render_pairs(pairs))
    print()

    # Show the tail of the error output: stderr first, stdout as a fallback.
    lines, label = _tail(main["stderr"]), main["stderr"]
    if lines is None and main["stdout"] != main["stderr"]:
        lines, label = _tail(main["stdout"]), main["stdout"]
    if lines:
        print(format.color(
            "--- last {0} lines of {1} ---".format(len(lines), label), "bold"))
        for line in lines:
            print("  " + line)
    elif not main["stderr"] and not main["stdout"]:
        print(format.color(
            "No output file recorded -- typical for interactive srun/idev "
            "jobs, where output went straight to the terminal.", "dim"))
    else:
        print(format.color(
            "Could not read the output file (moved, deleted, still running, "
            "or no permission).", "dim"))
    return 0


def run(args):
    if args.jobid:
        return _detail(args)

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
    print()
    print(format.color(
        "Post-mortem for one job (incl. error output):  sb history <jobid>",
        "dim",
    ))
    return 0
