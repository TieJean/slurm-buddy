"""Shared helpers for subcommand modules."""

from __future__ import print_function

from .. import slurm


def emit_raw(args, cmd, slurm_args):
    """If --raw was passed, print the SLURM command and return True.

    Commands call this right before they would run a SLURM command::

        if emit_raw(args, "sinfo", sinfo_args):
            return 0
    """
    if getattr(args, "raw", False):
        print(slurm.render_command(cmd, slurm_args))
        return True
    return False


def confirm(prompt):
    """Ask a yes/no question on stdin. Returns True for yes."""
    try:
        reply = input("{0} [y/N] ".format(prompt))
    except EOFError:
        return False
    return reply.strip().lower() in ("y", "yes")
