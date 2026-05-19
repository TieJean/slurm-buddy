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
        cp = configparser.ConfigParser()
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
