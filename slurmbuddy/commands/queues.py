"""sb queues -- list all partitions with their per-node resources."""

from __future__ import print_function

from .. import format, gres, partitions
from ._common import emit_raw

_COLUMNS = ["partition", "nodes", "timelimit", "cpus", "mem", "gpus"]
_HEADERS = ["PARTITION", "NODES", "TIMELIMIT", "CPUS/NODE", "MEM/NODE", "GPUS/NODE"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "queues", help="list partitions with CPU/GPU resources"
    )
    p.add_argument(
        "-g", "--gpu-only", action="store_true", help="only show GPU partitions"
    )
    p.set_defaults(func=run)


def run(args):
    if emit_raw(args, "sinfo", ["-h", "-e", "-o", "%P|%D|%l|%c|%m|%G"]):
        return 0

    parts = partitions.list_partitions()
    rows = []
    for p in parts:
        if args.gpu_only and not p.gpus:
            continue
        name = p.name + ("*" if p.is_default else "")
        rows.append(
            {
                "partition": name,
                "nodes": p.nodes,
                "timelimit": format.humanize_time(p.timelimit),
                "cpus": p.cpus,
                "mem": format.humanize_mem(p.mem),
                "gpus": gres.summary(p.gres_str),
            }
        )

    if not rows:
        print("No matching partitions.")
        return 0

    rows.sort(key=lambda r: r["partition"])
    print(format.render_table(rows, _COLUMNS, _HEADERS))
    print()
    print(format.color("* = default partition", "dim"))
    return 0
