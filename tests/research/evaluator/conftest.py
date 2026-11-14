"""Make sibling helper modules importable under --import-mode=importlib; shared fixtures."""

import sys
from pathlib import Path

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from twdata.research.evaluator import log  # noqa: E402


@pytest.fixture
def logpath(tmp_path, monkeypatch):
    p = tmp_path / "research" / "experiment_log.jsonl"
    monkeypatch.setattr(log, "LOG_PATH", p)
    return p
