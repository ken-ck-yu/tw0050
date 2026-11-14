import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

from twdata import cli
from twdata.common.errors import exit_code_for

REPO = Path(__file__).resolve().parents[2]


def _load_audit():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ownership_audit", REPO / "scripts" / "ownership_audit.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exit_code_mapping():
    from twdata.clients.base import AuthError, BlockedError, DriftError, RetryExhausted
    from twdata.common.cleanstore import KeyUniquenessError, PointInTimeError
    from twdata.common.config import ConfigError
    from twdata.common.parsing import ParseError
    from twdata.common.sanity import SanityError
    from twdata.common.tradingcal import CalendarRangeError

    for exc, code in [
        (BlockedError(), 3),
        (AuthError(), 3),
        (RetryExhausted(), 3),
        (DriftError(), 4),
        (SanityError(), 4),
        (ParseError(), 4),
        (ConfigError(), 5),
        (CalendarRangeError(), 5),
        (KeyUniquenessError(), 5),
        (PointInTimeError(), 5),
        (RuntimeError(), 5),
    ]:
        assert exit_code_for(exc) == code


def test_discover_good_broken_and_duplicate(tmp_path, monkeypatch):
    pkg = tmp_path / "fakepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("IMPORT_ERRORS = {}\n")
    (pkg / "good.py").write_text("DATASETS = {'a': lambda ctx, s, e: None}\n")
    (pkg / "broken.py").write_text("raise RuntimeError('boom')\n")
    (pkg / "dup.py").write_text(
        "DATASETS = {'a': lambda ctx, s, e: None, 'b': lambda c, s, e: None}\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found, errors = cli.discover("fakepkg")
    assert "a" in found and "broken" in errors
    assert any("duplicate dataset name" in v for v in errors.values())
    assert "boom" in errors["broken"]


def test_cli_usage_and_missing_modules(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TWDATA_DATA_DIR", str(tmp_path))
    assert (
        cli.main(["fetch", "--dataset", "nope", "--start", "2025-01-01", "--end", "2025-01-02"])
        == 2
    )
    assert cli.main(["snapshot"]) in (0, 5)  # 5 until agent A builds it, 0 afterwards
    assert cli.main(["status"]) == 0
    with pytest.raises(SystemExit):
        cli.main(["bogus"])


def test_ownership_glob_and_audit(tmp_path):
    audit = _load_audit()
    g = ["src/twdata/ingest/a.py", "tests/agent_a/**", "docs/data_dictionary/a_*.md"]
    assert audit.allowed("src/twdata/ingest/a.py", g)
    assert audit.allowed("tests/agent_a/sub/test_x.py", g)
    assert audit.allowed("docs/data_dictionary/a_prices.md", g)
    assert not audit.allowed("docs/data_dictionary/sub/a_x.md", g)  # * stays inside a segment
    assert not audit.allowed("src/twdata/ingest/b.py", g)
    assert not audit.allowed("tests/validate/test_x.py", g)

    def run(*args, cwd):
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            env={
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
                "PATH": "/usr/bin:/bin",
            },
        )

    repo = tmp_path / "r"
    repo.mkdir()
    run("init", "-q", "-b", "main", cwd=repo)
    (repo / "config").mkdir()
    (repo / "config" / "ownership.yaml").write_text(yaml.safe_dump({"A": ["a/**"], "B": ["b/**"]}))
    (repo / "a").mkdir()
    (repo / "a" / "f.txt").write_text("1")
    run("add", "-A", cwd=repo)
    run("commit", "-q", "-m", "base", cwd=repo)
    run("checkout", "-q", "-b", "feature", cwd=repo)
    (repo / "a" / "g.txt").write_text("2")
    (repo / "b").mkdir()
    (repo / "b" / "h.txt").write_text("3")
    # a branch cannot grant itself paths: editing ownership.yaml does not widen the base rules
    (repo / "config" / "ownership.yaml").write_text(yaml.safe_dump({"A": ["**"], "B": ["b/**"]}))
    run("add", "-A", cwd=repo)
    run("commit", "-q", "-m", "change", cwd=repo)
    bad = audit.audit("A", "main", "feature", cwd=str(repo))
    assert sorted(bad) == ["b/h.txt", "config/ownership.yaml"]
    assert audit.audit("B", "main", "feature", cwd=str(repo)) == [
        "a/g.txt",
        "config/ownership.yaml",
    ]
    _ = (sys, types)
