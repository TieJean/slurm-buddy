"""sb resources -- live idle-vs-allocated CPU/GPU availability per partition."""

from __future__ import print_function

from .. import format, gres, partitions
from ._common import emit_raw

_COLUMNS = ["partition", "nodes", "cpus", "gpus"]
_HEADERS = ["PARTITION", "NODES idle/total", "CPUS idle/total", "GPUS idle/total*"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "resources", help="live idle/allocated CPU & GPU per partition"
    )
    p.add_argument(
        "partition", nargs="?", help="restrict to a single partition"
    )
    p.set_defaults(func=run)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def run(args):
    sinfo_args = ["-h", "-o", "%P|%D|%c|%m|%G|%t|%C"]
    if args.partition:
        sinfo_args += ["-p", args.partition]
    if emit_raw(args, "sinfo", sinfo_args):
        return 0

    rows = partitions.state_rows()
    if args.partition:
        rows = [r for r in rows if r["partition"] == args.partition]

    # Aggregate per partition across its node-state groups.
    agg = {}
    for r in rows:
        name = r["partition"]
        a = agg.setdefault(
            name,
            {"n_total": 0, "n_idle": 0, "c_idle": 0, "c_total": 0,
             "g_total": 0, "g_idle": 0},
        )
        n = _int(r["nodes"])
        state = r["state"].lower().rstrip("*~#$@+")
        is_idle = state == "idle"

        a["n_total"] += n
        if is_idle:
            a["n_idle"] += n

        # %C = allocated/idle/other/total CPUs for this node group.
        cpu_parts = r["cpu_aiot"].split("/")
        if len(cpu_parts) == 4:
            a["c_idle"] += _int(cpu_parts[1])
            a["c_total"] += _int(cpu_parts[3])

        gpus_per_node = gres.total_count(r["gres"])
        a["g_total"] += gpus_per_node * n
        if is_idle:
            a["g_idle"] += gpus_per_node * n

    if not agg:
        print("No matching partitions.")
        return 0

    out = []
    for name in sorted(agg):
        a = agg[name]
        out.append(
            {
                "partition": name,
                "nodes": "{0}/{1}".format(a["n_idle"], a["n_total"]),
                "cpus": "{0}/{1}".format(a["c_idle"], a["c_total"]),
                "gpus": (
                    "{0}/{1}".format(a["g_idle"], a["g_total"])
                    if a["g_total"]
                    else "-"
                ),
            }
        )

    print(format.render_table(out, _COLUMNS, _HEADERS))
    print()
    print(
        format.color(
            "* GPU idle counts whole idle nodes only; 'mix' nodes may have "
            "free GPUs not shown here.",
            "dim",
        )
    )
    return 0
