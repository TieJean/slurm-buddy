"""sb usage -- fairshare / allocation usage for the user's accounts."""

from __future__ import print_function

from .. import format, slurm
from ._common import emit_raw

_FMT = "Account,User,RawShares,NormShares,EffectvUsage,FairShare"
_COLS = ["account", "user", "rawshares", "normshares", "usage", "fairshare"]
_HEADERS = ["ACCOUNT", "USER", "RAWSHARES", "NORMSHARES", "EFF.USAGE", "FAIRSHARE"]


def add_parser(subparsers):
    p = subparsers.add_parser(
        "usage", help="fairshare / allocation usage for my accounts"
    )
    p.add_argument("-a", "--account", help="restrict to one account")
    p.set_defaults(func=run)


def run(args):
    user = slurm.current_user()
    sshare_args = ["-U", "-P", "-n", "-o", _FMT]
    if args.account:
        sshare_args += ["-A", args.account]
    if emit_raw(args, "sshare", sshare_args):
        return 0

    rows = slurm.run_table("sshare", sshare_args, _COLS)
    # Keep this user's own per-account rows.
    rows = [r for r in rows if r["user"] in (user, "")]
    rows = [r for r in rows if r["user"] == user] or rows

    if not rows:
        print("No fairshare data found for {0}.".format(user))
        return 1

    print(format.color("fairshare for ", "bold") + user)
    print()
    print(format.render_table(rows, _COLS, _HEADERS))
    print()
    print(format.color(
        "FairShare nearer 1.0 = under-served (higher scheduling priority); "
        "nearer 0 = over-served.",
        "dim",
    ))
    return 0
