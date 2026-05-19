"""Unit tests for slurmbuddy.config.set_user_value.

Runs under pytest, or standalone: `python3 tests/test_config.py`.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slurmbuddy import config  # noqa: E402


def _with_temp_user_file(initial=None):
    """Point config._USER at a fresh temp file; return its path."""
    fd, path = tempfile.mkstemp(suffix=".ini")
    os.close(fd)
    if initial is None:
        os.remove(path)  # exercise the missing-file path
    else:
        with open(path, "w") as fh:
            fh.write(initial)
    config._USER = path
    config._cache = None
    return path


def _read(path):
    with open(path) as fh:
        return fh.read()


def test_creates_file_and_section():
    path = _with_temp_user_file(None)
    try:
        config.set_user_value("idev", "email", "a@b.edu")
        text = _read(path)
        assert "[idev]" in text
        assert "email = a@b.edu" in text
    finally:
        os.remove(path)


def test_appends_section_preserving_existing():
    initial = "[idev.delta]\n# keep me\naccount = bger-delta-gpu\n"
    path = _with_temp_user_file(initial)
    try:
        config.set_user_value("idev", "email", "a@b.edu")
        text = _read(path)
        assert "# keep me" in text                 # comment preserved
        assert "account = bger-delta-gpu" in text   # other key preserved
        assert "[idev]" in text and "email = a@b.edu" in text
    finally:
        os.remove(path)


def test_replaces_existing_key_in_place():
    initial = "[idev]\nemail = old@x.edu\nnodes = 1\n"
    path = _with_temp_user_file(initial)
    try:
        config.set_user_value("idev", "email", "new@y.edu")
        text = _read(path)
        assert "new@y.edu" in text
        assert "old@x.edu" not in text
        assert "nodes = 1" in text  # sibling key untouched
        assert text.count("email") == 1  # not duplicated
    finally:
        os.remove(path)


def test_inserts_key_into_existing_section():
    initial = "[idev]\nnodes = 1\n"
    path = _with_temp_user_file(initial)
    try:
        config.set_user_value("idev", "email", "a@b.edu")
        text = _read(path)
        assert "nodes = 1" in text
        assert "email = a@b.edu" in text
    finally:
        os.remove(path)


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
