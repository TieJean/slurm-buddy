"""slurm-buddy subcommands. Each module exposes add_parser() and run()."""

from . import (
    attach,
    cancel,
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
    idev,
    attach,
    jobs,
    cancel,
    node,
    usage,
    history,
    whoami,
]
