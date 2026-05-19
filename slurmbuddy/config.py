"""Load slurm-buddy configuration.

Reads the shipped config/defaults.ini, then layers a user override from
~/.config/slurm-buddy/config.ini if present.

Cluster-scoped sections
-----------------------
A section named ``[<name>.<ClusterName>]`` applies ONLY when it matches the
running cluster's SLURM ClusterName (see ``slurm.cluster_name()``). A plain
``[<name>]`` section is cluster-neutral and applies everywhere. This lets one
config file safely carry settings for several clusters at once -- the values
for one cluster are never used on another. Matching fails closed: when the
cluster cannot be determined, cluster-scoped sections are simply ignored.
"""

import configparser
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULTS = os.path.join(_REPO_ROOT, "config", "defaults.ini")
_USER = os.path.expanduser("~/.config/slurm-buddy/config.ini")

_cache = None


def load():
    """Return a configparser.ConfigParser with defaults + user overrides."""
    global _cache
    if _cache is None:
        # delimiters=('=',) only: keys like 'A100:4' must keep their colon.
        cp = configparser.ConfigParser(delimiters=("=",))
        # read() silently skips files that do not exist.
        cp.read([_DEFAULTS, _USER])
        _cache = cp
    return _cache


def _cluster():
    """The running cluster's SLURM ClusterName, lowercased ("" if unknown)."""
    from . import slurm  # local import: avoids any import-order coupling
    return slurm.cluster_name()


def get(section, key, fallback=None):
    """Get a config string value, or `fallback` if missing/blank."""
    value = load().get(section, key, fallback=fallback)
    if value is None:
        return fallback
    value = value.strip()
    return value if value else fallback


def get_bool(section, key, fallback=False):
    """Get a config boolean value."""
    try:
        return load().getboolean(section, key, fallback=fallback)
    except ValueError:
        return fallback


def get_scoped(section, key, fallback=None):
    """Get a value, preferring the cluster-scoped [section.<cluster>] section.

    Looks in ``[section.<ClusterName>]`` first, then the neutral ``[section]``.
    So cluster-specific values (e.g. an interactive partition name) only ever
    take effect on the cluster they were written for.
    """
    cp = load()
    cluster = _cluster()
    sections = []
    if cluster:
        sections.append("{0}.{1}".format(section, cluster))
    sections.append(section)
    for sect in sections:
        if cp.has_section(sect):
            value = cp.get(sect, key, fallback=None)
            if value is not None and value.strip():
                return value.strip()
    return fallback


def gpu_memory_table():
    """Return the GPU->memory map for the running cluster, or {}.

    GPU memory is not reported by SLURM, so the table is hand-maintained per
    cluster in a cluster-scoped [gpu_memory.<ClusterName>] section. Only the
    section matching the running cluster is read, so one cluster's figures are
    never shown on another. Fails closed: an undeterminable cluster (or no
    matching section) yields an empty table.
    """
    cluster = _cluster()
    if not cluster:
        return {}
    section = "gpu_memory." + cluster
    cp = load()
    if not cp.has_section(section):
        return {}
    return {k.lower(): v.strip() for k, v in cp.items(section) if v.strip()}
