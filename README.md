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
| `sb idev` | Request an interactive compute node (the Delta replacement for TACC's `idev`). |
| `sb jobs` | Your running/pending jobs, with an estimated start time for pending ones. `-u <user>` for someone else, `-a` for everyone. |
| `sb cancel <jobid>... \| --all` | Cancel job(s); asks for confirmation unless `-y`. |
| `sb node <name>` | Detailed node info: state, CPUs, memory, GPUs, features, drain reason. |
| `sb usage` | Fairshare / allocation standing for your accounts. |
| `sb history [-d N]` | Finished jobs from the last N days with exit codes and elapsed time. |
| `sb history <jobid>` | Post-mortem of one job: decoded exit code, nodes, work dir, submit line, and a tail of its error output. |
| `sb whoami` | Your SLURM accounts, partitions, and association limits. |

Global flags: `--no-color`, and `--raw` to print the underlying SLURM command
instead of running it.

## Interactive nodes: `sb idev`

```bash
sb idev -p gpuA100x8-interactive         # 4 GPU + matched CPU (see below)
sb idev -p gpuA100x4-interactive -g 1     # 1 GPU + 16 matched cores
sb idev --dry-run                        # show command + estimated start, don't launch
sb idev --set-email you@example.edu       # save your notification address
```

`sb idev` builds an `srun --pty $SHELL` invocation (or `salloc` with `--salloc`)
and hands your terminal directly to it. The session **blocks the terminal**
until you exit it — that is expected. It warns if you target a non-interactive
partition or are already inside an allocation.

**GPU & CPU defaults.** On a GPU partition, `sb idev` defaults to 4 GPUs
(capped to one node) and *matches* the CPU count to them at the node's
cores-per-GPU ratio — the most CPUs you can take without raising the bill under
SLURM's `MAX_TRES` accounting. `-g` / `-c` override either. On a CPU partition
it just uses the `cpus` default.

**Email notification.** `sb idev` adds `--mail-type=BEGIN` so SLURM emails you
when the job starts. The address comes from `$SLURM_EMAIL`, else an `email` key
in `~/.config/slurm-buddy/config.ini` — never the repo. If neither is set it
prompts once and saves the answer; `--set-email ADDR` changes it, `--no-mail`
skips it for one run.

**Account resolution** (no `-A` needed in the common case):
`-A` flag → `account` in config → `$SLURM_ACCOUNT` / `$SALLOC_ACCOUNT` /
`$SBATCH_ACCOUNT` → your SLURM **default account** → a sole association.
`sb idev` always prints which account it chose and where it came from; if it
fell back to your default while you have others, it lists them so you can
`-A`-switch. It only errors when no account exists at all.

**`--dry-run`** prints the command *and* an estimated start time for that exact
config, obtained from `srun --test-only` (which validates and estimates without
submitting anything). A non-timestamp result — e.g. `allocation failure` — is
highlighted, so dry-run also doubles as a quick "will this config even run"
check.

## Configuration

Defaults live in [config/defaults.ini](config/defaults.ini). Override per-user
by copying it to `~/.config/slurm-buddy/config.ini` and editing.

**Cluster-scoped sections.** Anything cluster-specific lives in a section named
`[<name>.<ClusterName>]` and applies *only* on the cluster whose SLURM
`ClusterName` matches; plain `[<name>]` sections are cluster-neutral. So one
config file can hold settings for several clusters and never apply one
cluster's values on another. Matching fails closed — if the cluster cannot be
determined, cluster-scoped sections are ignored. (`ClusterName`:
`scontrol show config | grep ClusterName`.)

```ini
[idev]                    # cluster-neutral
time = 1:00:00
cpus = 4

[idev.delta]              # used only on cluster 'delta'
partition = cpu-interactive
account = bewg-delta-gpu

[idev.frontera]           # used only on cluster 'frontera'
partition = development
account = MY-ALLOC
```

The most useful thing to set is your default `idev` account, under the
`[idev.<yourcluster>]` section.

### GPU memory

SLURM does not report per-GPU memory anywhere, so the `GPU MEM` column in
`sb queues` comes from a static, cluster-scoped `[gpu_memory.<ClusterName>]`
table. Only the section matching the running cluster is read, so the bundled
NCSA Delta figures can never show as wrong data elsewhere — on any other
cluster the column shows `?` until you add a section for it. Key by GPU model;
append `:<gpus-per-node>` when one model ships in multiple memory sizes (e.g.
Delta's A100 is 40 GB on x4 nodes, 80 GB on x8 nodes):

```ini
[gpu_memory.delta]
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
