"""Parse SLURM GRES strings into structured GPU info.

Pure functions, no I/O -- unit-tested without a cluster.

GRES strings look like::

    gpu:nvidia_a100:4(S:0-3)
    gpu:a100:8
    gpu:mi100:8(S:1,3,5,7),gpu:mi210:1(S:5)
    (null)

We only care about the `gpu` resource: its type label and count.
"""

import re

# Map raw SLURM type tokens to tidy display names.
_TYPE_ALIASES = {
    "nvidia_a100": "A100",
    "nvidia_a40": "A40",
    "nvidia_h200": "H200",
    "nvidia_h100": "H100",
    "a100": "A100",
    "a40": "A40",
    "h200": "H200",
    "h100": "H100",
    "mi100": "MI100",
    "mi210": "MI210",
    "mi300a": "MI300A",
}

# One GRES entry: name[:type]:count[(extra)]
_ENTRY = re.compile(
    r"""
    (?P<name>[A-Za-z][\w]*)        # resource name, e.g. gpu
    (?::(?P<type>[A-Za-z][\w]*))?  # optional type, e.g. nvidia_a100
    :(?P<count>\d+)                # count
    (?:\([^)]*\))?                 # optional (S:...) socket spec
    """,
    re.VERBOSE,
)


def normalize_type(raw):
    """Return a tidy display name for a GRES type token."""
    if not raw:
        return "GPU"
    key = raw.lower()
    if key in _TYPE_ALIASES:
        return _TYPE_ALIASES[key]
    return raw.upper() if len(raw) <= 5 else raw


def parse(gres):
    """Parse a GRES string, returning a list of {'type', 'count'} GPU dicts.

    Non-gpu resources and empty/`(null)` strings yield an empty list. Multiple
    entries of the same type are merged.
    """
    if not gres or gres.strip().lower() in ("(null)", "null", ""):
        return []
    merged = {}
    order = []
    for m in _ENTRY.finditer(gres):
        if m.group("name").lower() != "gpu":
            continue
        gtype = normalize_type(m.group("type"))
        count = int(m.group("count"))
        if gtype not in merged:
            merged[gtype] = 0
            order.append(gtype)
        merged[gtype] += count
    return [{"type": t, "count": merged[t]} for t in order]


def summary(gres):
    """Return a short human string for a GRES string, e.g. '4x A100' or '-'."""
    gpus = parse(gres)
    if not gpus:
        return "-"
    return ", ".join("{0}x {1}".format(g["count"], g["type"]) for g in gpus)


def total_count(gres):
    """Total number of GPUs across all types in a GRES string."""
    return sum(g["count"] for g in parse(gres))
