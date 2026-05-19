"""sb node -- detailed information about a single node."""

from __future__ import print_function

import re

from .. import format, gres, slurm
from ._common import emit_raw

# Fields to surface, in display order: (scontrol key, label).
_FIELDS = [
    ("State", "state"),
    ("Partitions", "partitions"),
    ("CPUTot", "cpus total"),
    ("CPUAlloc", "cpus allocated"),
    ("CPULoad", "cpu load"),
    ("RealMemory", "memory total (MB)"),
    ("AllocMem", "memory allocated (MB)"),
    ("FreeMem", "memory free (MB)"),
    ("ActiveFeatures", "features"),
    ("Reason", "drain reason"),
]

# Split scontrol output on whitespace that precedes a "Key=" token.
_KV_SPLIT = re.compile(r"\s+(?=[A-Za-z][\w]*=)")


def add_parser(subparsers):
    p = subparsers.add_parser("node", help="detailed info for one node")
    p.add_argument("nodename", help="node name, e.g. gpub001")
    p.set_defaults(func=run)


def _parse(text):
    """Parse `scontrol show node` output into a key->value dict."""
    fields = {}
    for token in _KV_SPLIT.split(text.strip()):
        if "=" in token:
            key, _, value = token.partition("=")
            fields[key] = value
    return fields


def run(args):
    scontrol_args = ["show", "node", args.nodename]
    if emit_raw(args, "scontrol", scontrol_args):
        return 0

    text = slurm.run("scontrol", scontrol_args)
    fields = _parse(text)
    if not fields:
        print("No data for node '{0}'.".format(args.nodename))
        return 1

    print(format.color("node: ", "bold") + args.nodename)
    print()

    pairs = []
    for key, label in _FIELDS:
        if key in fields:
            pairs.append((label, fields[key]))

    gres_str = fields.get("Gres", "")
    gres_used = fields.get("GresUsed", "")
    if gres.parse(gres_str):
        pairs.append(("gpus total", gres.summary(gres_str)))
        if gres_used:
            pairs.append(("gpus in use", gres.summary(gres_used)))

    print(format.render_pairs(pairs))
    return 0
