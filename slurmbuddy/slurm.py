"""The single chokepoint for all SLURM interaction.

Every subcommand goes through here so command construction, error handling,
and text-table parsing live in one place.
"""

import getpass
import os
import re
import shutil
import subprocess

# A token safe to print unquoted in a shell command line.
_SHELL_SAFE = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


class SlurmError(Exception):
    """A SLURM command failed, or SLURM is unavailable."""


def ensure_available(cmd):
    """Raise SlurmError with a friendly message if `cmd` is not on PATH."""
    if shutil.which(cmd) is None:
        raise SlurmError(
            "'{0}' not found. slurm-buddy must run on a cluster with SLURM "
            "installed (login or compute node).".format(cmd)
        )


def run(cmd, args, check=True):
    """Run a SLURM command and return its stdout as a string.

    `args` is a list of arguments. On nonzero exit (when check=True), raises
    SlurmError carrying stderr.
    """
    ensure_available(cmd)
    argv = [cmd] + list(args)
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise SlurmError("failed to run {0}: {1}".format(" ".join(argv), exc))
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise SlurmError(
            "{0} exited {1}{2}".format(
                " ".join(argv),
                proc.returncode,
                ": " + detail if detail else "",
            )
        )
    return proc.stdout


def run_table(cmd, args, columns, sep="|", check=True):
    """Run a command whose output is `sep`-delimited rows.

    Returns a list of dicts keyed by `columns`. Blank lines are skipped. Rows
    are zipped to `columns`; extra trailing fields are dropped, short rows are
    padded with "" so callers can index every column safely.

    With check=False a nonzero exit is tolerated and whatever rows were
    printed are still parsed (e.g. squeue with a mix of valid/invalid IDs).
    """
    out = run(cmd, args, check=check)
    rows = []
    n = len(columns)
    for line in out.splitlines():
        if not line.strip():
            continue
        fields = line.split(sep)
        if len(fields) < n:
            fields = fields + [""] * (n - len(fields))
        rows.append({col: fields[i].strip() for i, col in enumerate(columns)})
    return rows


def render_command(cmd, args):
    """Return a copy-pasteable, shell-safe string for the command (--raw)."""
    parts = [cmd]
    for a in args:
        if _SHELL_SAFE.match(a):
            parts.append(a)
        else:
            parts.append("'" + a.replace("'", "'\\''") + "'")
    return " ".join(parts)


def exec_replace(argv):
    """Replace the current process with `argv` (for interactive sessions).

    Used by `sb idev` so the terminal is handed directly to srun/salloc.
    Does not return on success.
    """
    ensure_available(argv[0])
    os.execvp(argv[0], argv)


def current_user():
    """The current username."""
    return os.environ.get("USER") or getpass.getuser()


def is_compute_node():
    """True if we appear to be inside a SLURM allocation already."""
    return "SLURM_JOB_ID" in os.environ or "SLURM_JOBID" in os.environ
