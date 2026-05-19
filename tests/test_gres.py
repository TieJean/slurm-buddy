"""Unit tests for slurmbuddy.gres -- pure parsing, no cluster needed.

Runs under pytest, or standalone: `python3 tests/test_gres.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slurmbuddy import gres  # noqa: E402


def test_empty_and_null():
    assert gres.parse("") == []
    assert gres.parse("(null)") == []
    assert gres.parse("null") == []
    assert gres.parse("   ") == []


def test_simple_typed():
    assert gres.parse("gpu:a100:4") == [{"type": "A100", "count": 4}]


def test_vendor_prefixed_type():
    assert gres.parse("gpu:nvidia_a100:4(S:0-3)") == [
        {"type": "A100", "count": 4}
    ]


def test_socket_spec_ignored():
    assert gres.parse("gpu:h200:8(S:0-7)") == [{"type": "H200", "count": 8}]


def test_untyped_gpu():
    assert gres.parse("gpu:2") == [{"type": "GPU", "count": 2}]


def test_multi_type():
    parsed = gres.parse("gpu:mi100:8(S:1,3,5,7),gpu:mi210:1(S:5)")
    assert parsed == [
        {"type": "MI100", "count": 8},
        {"type": "MI210", "count": 1},
    ]


def test_same_type_merged():
    assert gres.parse("gpu:a40:2,gpu:a40:2") == [{"type": "A40", "count": 4}]


def test_non_gpu_resources_skipped():
    assert gres.parse("craynetwork:4") == []
    assert gres.parse("gpu:a100:4,craynetwork:1") == [
        {"type": "A100", "count": 4}
    ]


def test_summary():
    assert gres.summary("gpu:a100:4") == "4x A100"
    assert gres.summary("(null)") == "-"
    assert gres.summary("gpu:mi100:8,gpu:mi210:1") == "8x MI100, 1x MI210"


def test_total_count():
    assert gres.total_count("gpu:a100:4") == 4
    assert gres.total_count("gpu:mi100:8,gpu:mi210:1") == 9
    assert gres.total_count("(null)") == 0


def test_normalize_type():
    assert gres.normalize_type("nvidia_a100") == "A100"
    assert gres.normalize_type("MI100") == "MI100"
    assert gres.normalize_type("") == "GPU"
    assert gres.normalize_type("a40") == "A40"


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
