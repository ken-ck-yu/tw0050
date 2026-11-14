import os
from pathlib import Path

import pytest

from twdata.common import config, paths


def test_settings_load_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("TWDATA_DATA_DIR", raising=False)
    s = config.load_settings()
    assert s.data_dir == config.repo_root() / "data"
    assert s.spacing_s.twse == 5 and s.finmind.target_fraction == 0.85
    assert s.backup_dir is None
    monkeypatch.setenv("TWDATA_DATA_DIR", str(tmp_path / "env"))
    assert config.load_settings().data_dir == tmp_path / "env"
    assert (
        config.load_settings(data_dir_override=str(tmp_path / "cli")).data_dir == tmp_path / "cli"
    )


def test_missing_and_unknown_keys(tmp_path):
    text = (config.repo_root() / "config" / "settings.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "s.yaml"
    bad.write_text(text.replace("backup_dir: null\n", ""), encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load_settings(bad)
    bad.write_text(text + "extra: 1\n", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load_settings(bad)


def test_env_loader_formats_and_no_override(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# c\nA_KEY=abc\nexport B_KEY='quoted value'\nC_KEY=\"dq\"\n\nEXISTING=new\n",
        encoding="utf-8",
    )
    for k in ("A_KEY", "B_KEY", "C_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EXISTING", "keep")
    loaded = config.load_env(env)
    assert sorted(loaded) == ["A_KEY", "B_KEY", "C_KEY"]
    assert os.environ["B_KEY"] == "quoted value" and os.environ["C_KEY"] == "dq"
    assert os.environ["EXISTING"] == "keep"
    for k in ("A_KEY", "B_KEY", "C_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_paths_under_data_dir(tmp_path):
    s = config.load_settings(data_dir_override=str(tmp_path))
    assert paths.raw_dir(s, "twse", "mi_index") == tmp_path / "raw" / "twse" / "mi_index"
    assert (
        paths.raw_dir(s, "twse", "mi_index", "qa") == tmp_path / "raw" / "qa" / "twse" / "mi_index"
    )
    assert paths.state_file(s, "x") == tmp_path / "state" / "x.json"
    assert paths.clean_dir(s, "t", 2) == tmp_path / "clean" / "t" / "v2"
    assert paths.current_file(s, "t") == tmp_path / "clean" / "t" / "CURRENT"
    assert isinstance(paths.host_lock_file(s, "twse"), Path)
    with pytest.raises(ValueError):
        paths.raw_dir(s, "a", "b", "bogus")


def test_research_settings():
    from datetime import date

    s = config.load_settings()
    assert s.research.dev_end == date(2024, 6, 30)
    assert s.research.train_end == date(2021, 12, 31)
    assert s.research.max_runs_per_cycle == 10
