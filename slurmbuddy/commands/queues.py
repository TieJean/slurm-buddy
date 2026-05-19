"""sb queues -- list all partitions with their per-node resources."""

from __future__ import print_function

from .. import config, format, gres, partitions
from ._common import emit_raw

_COLUMNS = ["partition", "nodes", "timelimit", "cpus", "mem", "gpus", "vram"]
_HEADERS = ["PARTITION", "NODES", "TIMELIMIT", "CPUS/NODE", "MEM/NODE",
            "GPUS/NODE", "GPU MEM"]


def _gpu_memory(gres_str, table):
    """Per-GPU memory for a GRES string, via the [gpu_memory] config table.

    Tries '<model>:<count>' first (to disambiguate e.g. 40GB vs 80GB A100),
    then '<model>'. Unknown models show '?'. Returns '-' when there are no GPUs.
    """
    gpus = gres.parse(gres_str)
    if not gpus:
        return "-"
    out = []
    for g in gpus:
        keyed = "{0}:{1}".format(g["type"], g["count"]).lower()
        mem = table.get(keyed) or table.get(g["type"].lower()) or "?"
        out.append(mem)
    return " / ".join(out)


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
    mem_table = config.gpu_memory_table()
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
                "vram": _gpu_memory(p.gres_str, mem_table),
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
