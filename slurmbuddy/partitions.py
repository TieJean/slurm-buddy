"""Shared partition discovery and resource model.

Used by `queues`, `resources`, and `idev` so partition parsing lives in one
place.
"""

from . import gres, slurm

# sinfo format: one line per (partition, distinct node group).
_QUEUE_FMT = "%P|%D|%l|%c|%m|%G"
_QUEUE_COLS = ["partition", "nodes", "timelimit", "cpus", "mem", "gres"]

# sinfo format with live state for `resources`.
_STATE_FMT = "%P|%D|%c|%m|%G|%t|%C"
_STATE_COLS = ["partition", "nodes", "cpus", "mem", "gres", "state", "cpu_aiot"]


class Partition(object):
    """One node group within a partition (heterogeneous partitions yield several)."""

    def __init__(self, name, is_default, nodes, timelimit, cpus, mem, gres_str):
        self.name = name
        self.is_default = is_default
        self.nodes = nodes
        self.timelimit = timelimit
        self.cpus = cpus
        self.mem = mem
        self.gres_str = gres_str

    @property
    def gpus(self):
        """List of {'type','count'} dicts for this node group."""
        return gres.parse(self.gres_str)

    @property
    def is_interactive(self):
        return self.name.endswith("-interactive") or "interactive" in self.name


def _clean_name(raw):
    """Strip the trailing '*' sinfo uses to mark the default partition."""
    is_default = raw.endswith("*")
    return raw.rstrip("*"), is_default


def list_partitions():
    """Return all partition node groups as Partition objects."""
    rows = slurm.run_table("sinfo", ["-h", "-e", "-o", _QUEUE_FMT], _QUEUE_COLS)
    out = []
    for r in rows:
        name, is_default = _clean_name(r["partition"])
        out.append(
            Partition(
                name=name,
                is_default=is_default,
                nodes=r["nodes"],
                timelimit=r["timelimit"],
                cpus=r["cpus"],
                mem=r["mem"],
                gres_str=r["gres"],
            )
        )
    return out


def partition_names():
    """Sorted unique partition names."""
    return sorted({p.name for p in list_partitions()})


def interactive_partitions():
    """Sorted unique names of partitions usable for interactive jobs."""
    return sorted({p.name for p in list_partitions() if p.is_interactive})


def suggest_interactive(name):
    """Given a (non-interactive) partition name, suggest an interactive variant."""
    candidates = interactive_partitions()
    guess = name + "-interactive"
    if guess in candidates:
        return guess
    for c in candidates:
        if c.startswith(name):
            return c
    return None


def state_rows():
    """Raw sinfo rows with live state, for `sb resources`.

    Returns dicts with keys from _STATE_COLS plus a cleaned 'partition'.
    """
    rows = slurm.run_table("sinfo", ["-h", "-o", _STATE_FMT], _STATE_COLS)
    for r in rows:
        r["partition"], r["is_default"] = _clean_name(r["partition"])
    return rows
