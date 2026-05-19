"""sb whoami -- show my SLURM accounts, partitions, and association limits."""

from __future__ import print_function

from .. import format, slurm
from ._common import emit_raw

_ASSOC_FMT = "Account,Partition,QOS,DefaultQOS,GrpTRES,MaxWall"
_ASSOC_COLS = ["account", "partition", "qos", "defaultqos", "grptres", "maxwall"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "whoami", help="show my accounts, partitions, and limits"
    )
    p.set_defaults(func=run)


def _assoc_args(user):
    return [
        "-nP", "show", "assoc",
        "user=" + user,
        "format=" + _ASSOC_FMT,
    ]


def associations(user=None):
    """Return the current user's SLURM associations as a list of dicts."""
    user = user or slurm.current_user()
    return slurm.run_table("sacctmgr", _assoc_args(user), _ASSOC_COLS)


def user_accounts(user=None):
    """Return the sorted unique account names the user can submit under."""
    accts = {r["account"] for r in associations(user) if r["account"]}
    return sorted(accts)


def run(args):
    user = slurm.current_user()
    if emit_raw(args, "sacctmgr", _assoc_args(user)):
        return 0

    rows = associations(user)
    print(format.color("user: ", "bold") + user)
    print()

    if not rows:
        print("No SLURM associations found for {0}.".format(user))
        return 0

    display = []
    for r in rows:
        display.append(
            {
                "account": r["account"],
                "partition": r["partition"] or "(any)",
                "qos": r["qos"] or "-",
                "maxwall": format.humanize_time(r["maxwall"]),
                "limits": r["grptres"] or "-",
            }
        )
    cols = ["account", "partition", "qos", "maxwall", "limits"]
    print(format.render_table(display, cols))

    accts = sorted({r["account"] for r in rows if r["account"]})
    print()
    print(format.color("accounts: ", "bold") + ", ".join(accts))
    return 0
