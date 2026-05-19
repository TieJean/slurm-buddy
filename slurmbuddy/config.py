"""Load slurm-buddy configuration.

Reads the shipped config/defaults.ini, then layers a user override from
~/.config/slurm-buddy/config.ini if present.
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


def gpu_memory_table():
    """Return the [gpu_memory] GPU->memory map, or {} if it does not apply.

    GPU memory is not reported by SLURM, so the table is hand-maintained and
    cluster-specific. If the section sets a 'cluster' key, the table is used
    ONLY when it matches the running cluster's SLURM ClusterName -- so a table
    written for one cluster never shows wrong memory figures on another. The
    match fails closed: an undeterminable cluster yields an empty table.
    """
    cp = load()
    if not cp.has_section("gpu_memory"):
        return {}
    items = {
        k.lower(): v.strip() for k, v in cp.items("gpu_memory") if v.strip()
    }
    table_cluster = items.pop("cluster", "").lower()
    if table_cluster:
        from . import slurm  # local import: avoids any import-order coupling
        if slurm.cluster_name() != table_cluster:
            return {}
    return items
