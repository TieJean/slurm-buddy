"""slurm-buddy CLI entry point: argparse setup and subcommand dispatch."""

import argparse
import sys

from . import commands, config, format
from . import __version__
from .slurm import SlurmError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sb",
        description="slurm-buddy: everyday SLURM helpers.",
    )
    parser.add_argument(
        "--version", action="version", version="slurm-buddy " + __version__
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disable colored output"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the underlying SLURM command instead of running it",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    for module in commands.ALL:
        module.add_parser(subparsers)
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)

    # Color: --no-color flag overrides config; both gate the isatty() check.
    if args.no_color or not config.get_bool("ui", "color", True):
        format.set_color(False)

    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args) or 0
    except SlurmError as exc:
        sys.stderr.write("error: {0}\n".format(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        sys.stderr.write("\naborted\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
