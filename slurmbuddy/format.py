"""Terminal table rendering, color, and human-readable value helpers."""

import re
import sys

# Matches ANSI SGR escape sequences so width math ignores invisible bytes.
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}

# Set by __main__ from --no-color / config / isatty.
_color_enabled = True


def set_color(enabled):
    """Globally enable/disable ANSI color output."""
    global _color_enabled
    _color_enabled = bool(enabled)


def should_color(stream=None):
    """True if color should be used for `stream` (default stdout)."""
    stream = stream or sys.stdout
    return _color_enabled and hasattr(stream, "isatty") and stream.isatty()


def color(text, name):
    """Wrap `text` in an ANSI color if color is enabled for stdout."""
    if not should_color():
        return text
    code = _COLORS.get(name, "")
    return "{0}{1}{2}".format(code, text, _COLORS["reset"]) if code else text


def humanize_mem(mb):
    """Convert a memory value in MB to a short string, e.g. 257637 -> '251G'."""
    try:
        mb = float(mb)
    except (TypeError, ValueError):
        return str(mb)
    if mb >= 1024 * 1024:
        return "{0:.1f}T".format(mb / (1024 * 1024)).replace(".0T", "T")
    if mb >= 1024:
        return "{0:.0f}G".format(mb / 1024)
    return "{0:.0f}M".format(mb)


def humanize_time(value):
    """Tidy a SLURM duration/time-limit string. Passes through unknowns."""
    if not value:
        return "-"
    v = value.strip()
    low = v.lower()
    if low in ("infinite", "unlimited"):
        return "unlimited"
    if low in ("n/a", "not_set", "(null)"):
        return "-"
    return v


def visible_len(text):
    """Length of `text` ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def _pad(text, width):
    """Left-justify `text` to `width` visible columns (ANSI-aware)."""
    return text + " " * max(0, width - visible_len(text))


def duration_seconds(value):
    """Parse a SLURM time/duration string to a number of seconds.

    Accepts every SLURM `--time` form: "minutes", "minutes:seconds",
    "hours:minutes:seconds", "days-hours", "days-hours:minutes" and
    "days-hours:minutes:seconds". Returns None for infinite/unlimited or
    anything unparseable, so callers can simply skip the check.
    """
    if not value:
        return None
    v = value.strip().lower()
    if v in ("infinite", "unlimited", "n/a", "not_set", "(null)", "-", ""):
        return None

    days = 0
    had_dash = "-" in v
    if had_dash:
        head, _, v = v.partition("-")
        try:
            days = int(head)
        except ValueError:
            return None
    try:
        nums = [int(p) for p in v.split(":")] if v else [0]
    except ValueError:
        return None

    if had_dash:  # days-hours[:minutes[:seconds]]
        if len(nums) > 3:
            return None
        nums = nums + [0] * (3 - len(nums))
        h, m, s = nums
    elif len(nums) == 1:  # minutes
        h, m, s = 0, nums[0], 0
    elif len(nums) == 2:  # minutes:seconds
        h, m, s = 0, nums[0], nums[1]
    elif len(nums) == 3:  # hours:minutes:seconds
        h, m, s = nums
    else:
        return None
    return days * 86400 + h * 3600 + m * 60 + s


def render_table(rows, columns, headers=None):
    """Render `rows` (list of dicts) as an aligned text table.

    `columns` is a list of dict keys; `headers` overrides the displayed header
    labels (defaults to the column keys, upper-cased). Cell values may contain
    ANSI color codes -- width math ignores them. Returns a string.
    """
    headers = headers or [c.upper() for c in columns]
    widths = [visible_len(h) for h in headers]
    cells = []
    for row in rows:
        line = [str(row.get(c, "")) for c in columns]
        cells.append(line)
        for i, val in enumerate(line):
            widths[i] = max(widths[i], visible_len(val))

    out = []
    header = "  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))
    out.append(color(header, "bold"))
    for line in cells:
        out.append("  ".join(_pad(val, widths[i]) for i, val in enumerate(line)))
    return "\n".join(out)


def render_pairs(pairs):
    """Render a list of (label, value) pairs as an aligned key/value block."""
    if not pairs:
        return ""
    width = max(len(str(k)) for k, _ in pairs)
    return "\n".join(
        "{0}  {1}".format(color(str(k).ljust(width), "cyan"), v)
        for k, v in pairs
    )
