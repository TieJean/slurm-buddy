# slurm-buddy

Everyday SLURM helpers, wrapped in one small command: `sb`.

Built for HPC clusters (developed on **NCSA Delta**, SLURM 25.11). Pure Python 3
standard library — no `pip`, no virtualenv, no modules to load. It runs anywhere
`python3` and the SLURM client commands are present, including inside jobs.

## Install

```bash
bash install.sh        # symlinks ~/bin/sb -> bin/sb (idempotent)
sb --help
```

If `~/bin` is not on your `PATH`, the installer prints the exact line to add to
`~/.bashrc`. No-install alternative:

```bash
alias sb='python3 /path/to/slurm-buddy/bin/sb'
```

## Commands

| Command | What it does |
|---|---|
| `sb queues` | List every partition with node count, time limit, CPUs/mem per node, GPU type/count, and per-GPU memory. `-g` for GPU partitions only. |
| `sb resources [partition]` | Live idle-vs-total CPU and GPU counts per partition — "can I get a node right now". |
| `sb eta <jobid>...` | Estimated start time for pending job(s). |
| `sb idev` | Request an interactive compute node (the Delta replacement for TACC's `idev`). |
| `sb jobs` | Your running/pending jobs. `-u <user>` for someone else, `-a` for everyone. |
| `sb cancel <jobid>... \| --all` | Cancel job(s); asks for confirmation unless `-y`. |
| `sb node <name>` | Detailed node info: state, CPUs, memory, GPUs, features, drain reason. |
| `sb usage` | Fairshare / allocation standing for your accounts. |
| `sb history [-d N]` | Finished jobs from the last N days with exit codes and elapsed time. |
| `sb whoami` | Your SLURM accounts, partitions, and association limits. |

Global flags: `--no-color`, and `--raw` to print the underlying SLURM command
instead of running it.

## Interactive nodes: `sb idev`

```bash
sb idev -A my-account                          # cpu-interactive, 1 core, 1h
sb idev -A my-account -p gpuA100x4-interactive -g 1 -t 2:00:00
sb idev -A my-account --dry-run                # print the command, don't launch
```

`sb idev` builds an `srun --pty $SHELL` invocation (or `salloc` with `--salloc`)
and hands your terminal directly to it. The session **blocks the terminal**
until you exit it — that is expected. It warns if you target a non-interactive
partition or are already inside an allocation.

Account resolution: `--account` flag, then `[idev] account` in config, then your
sole SLURM association. If you belong to several accounts and set none, it
errors and asks you to pick one.

## Configuration

Defaults live in [config/defaults.ini](config/defaults.ini). Override any of
them per-user by copying that file to `~/.config/slurm-buddy/config.ini` and
editing it — most usefully, set your default `idev` account:

```ini
[idev]
account = my-account
partition = cpu-interactive
time = 1:00:00
cpus = 4
```

### GPU memory

SLURM does not report per-GPU memory anywhere, so the `GPU MEM` column in
`sb queues` comes from the static `[gpu_memory]` table in the config.

The table is **guarded by cluster identity**: the `cluster` key must equal the
running cluster's SLURM `ClusterName`, or the table is ignored entirely and the
column shows `?`. This means the bundled NCSA Delta figures can never be shown
as wrong data on a different cluster — the guard fails closed (an
undeterminable cluster also yields `?`).

To use it on another cluster, set `cluster` to your `ClusterName` (find it with
`scontrol show config | grep ClusterName`) and replace the entries. Key by GPU
model; append `:<gpus-per-node>` when one model ships in multiple memory sizes
(e.g. Delta's A100 is 40 GB on x4 nodes, 80 GB on x8 nodes):

```ini
[gpu_memory]
cluster = delta
A100:4 = 40G
A100:8 = 80G
A40 = 48G
```

## Layout

```
bin/sb              entry-point stub (exec python3 -m slurmbuddy)
slurmbuddy/         the package
  slurm.py          single chokepoint for running SLURM commands
  gres.py           GPU/GRES string parsing
  partitions.py     partition discovery + resource model
  format.py         table rendering, color, humanizers
  config.py         INI config loading
  commands/         one module per subcommand
tests/              unit tests for gres.py and format.py
```

## Tests

The parser/formatter tests are pure and need no cluster:

```bash
python3 tests/test_gres.py
python3 tests/test_format.py
# or, if pytest is installed:  python3 -m pytest tests/
```
