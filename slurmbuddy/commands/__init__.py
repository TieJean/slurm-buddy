"""slurm-buddy subcommands. Each module exposes add_parser() and run()."""

from . import (
    cancel,
    eta,
    history,
    idev,
    jobs,
    node,
    queues,
    resources,
    usage,
    whoami,
)

# Order here is the order shown in `sb --help`.
ALL = [
    queues,
    resources,
    eta,
    idev,
    jobs,
    cancel,
    node,
    usage,
    history,
    whoami,
]
