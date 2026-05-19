"""Unit tests for slurmbuddy.format.

Runs under pytest, or standalone: `python3 tests/test_format.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slurmbuddy import format  # noqa: E402


def test_humanize_mem():
    assert format.humanize_mem(257637) == "252G"
    assert format.humanize_mem(2048) == "2G"
    assert format.humanize_mem(512) == "512M"
    assert format.humanize_mem(0) == "0M"
    assert format.humanize_mem("bogus") == "bogus"


def test_humanize_mem_terabytes():
    assert format.humanize_mem(2 * 1024 * 1024) == "2T"


def test_humanize_time():
    assert format.humanize_time("2-00:00:00") == "2-00:00:00"
    assert format.humanize_time("infinite") == "unlimited"
    assert format.humanize_time("n/a") == "-"
    assert format.humanize_time("") == "-"


def test_visible_len_ignores_ansi():
    colored = "\033[31mRED\033[0m"
    assert format.visible_len(colored) == 3
    assert format.visible_len("plain") == 5


def test_render_table_alignment():
    format.set_color(False)
    rows = [
        {"a": "x", "b": "longvalue"},
        {"a": "yy", "b": "z"},
    ]
    out = format.render_table(rows, ["a", "b"], ["A", "B"])
    lines = out.splitlines()
    assert lines[0].startswith("A ")
    # Every rendered line is the same visible width.
    widths = {format.visible_len(ln) for ln in lines}
    assert len(widths) == 1


def test_render_table_with_colored_cell_stays_aligned():
    format.set_color(False)
    rows = [
        {"s": "\033[32mCOMPLETED\033[0m", "n": "1"},
        {"s": "FAILED", "n": "2"},
    ]
    out = format.render_table(rows, ["s", "n"], ["STATE", "N"])
    lines = out.splitlines()
    widths = {format.visible_len(ln) for ln in lines}
    assert len(widths) == 1


def test_render_pairs():
    format.set_color(False)
    out = format.render_pairs([("key", "val"), ("longerkey", "v2")])
    assert "key" in out and "val" in out
    assert len(out.splitlines()) == 2


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   " + name)
            except AssertionError as exc:
                failed += 1
                print("FAIL " + name + ": " + str(exc))
    sys.exit(1 if failed else 0)
