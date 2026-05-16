"""Persistent proof number counter — increments on each print."""

import json
from pathlib import Path

from config import CONFIG_PATH

_PATH = CONFIG_PATH.parent / "counter.json"


def next_proof_number() -> int:
    """Increment counter, persist to disk, return new value."""
    n = _read() + 1
    _write(n)
    return n


def peek() -> int:
    """Return current count without incrementing (used by mockup)."""
    return _read()


def _read() -> int:
    if _PATH.exists():
        try:
            return int(json.loads(_PATH.read_text()).get("n", 0))
        except (ValueError, json.JSONDecodeError):
            return 0
    return 0


def _write(n: int) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps({"n": n}))
