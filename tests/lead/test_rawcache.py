import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

import pyarrow.parquet as pq
import pytest

from twdata.clients.rawcache import RawCache, request_key
from twdata.common import config, paths

T0 = datetime(2026, 1, 5, 3, 0, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def _put(cache, i, body=None, key=None, t=None):
    key = key or request_key("GET", "https://x/y", {"i": i})
    cache.put(
        "twse",
        "ds",
        key,
        "https://x/y",
        {"i": i},
        200,
        body if body is not None else f"body{i}".encode(),
        t or T0 + timedelta(seconds=i),
    )
    return key


def _shards(settings, area="raw"):
    d = paths.raw_dir(settings, "twse", "ds", area)
    return sorted(d.glob("shard-*.parquet")) if d.exists() else []


def _manifest(settings, ds="ds"):
    p = paths.manifest_file(settings, "twse", ds)
    return p.read_text().splitlines() if p.exists() else []


def test_request_key_definition():
    expected = hashlib.sha256(b'GET\nhttp://a\n{"a":1,"b":2}').hexdigest()
    assert request_key("GET", "http://a", {"b": 2, "a": 1}) == expected


def test_shard_written_exactly_at_limit(settings):
    cache = RawCache(settings)
    for i in range(24):
        _put(cache, i)
    assert _shards(settings) == []
    _put(cache, 24)
    shards = _shards(settings)
    assert len(shards) == 1
    t = pq.read_table(shards[0])
    assert t.num_rows == 25
    assert t.column_names == [
        "request_key",
        "url",
        "params",
        "fetched_at",
        "status",
        "body",
        "body_sha256",
    ]
    assert str(t.schema.field("fetched_at").type) == "timestamp[us, tz=UTC]"
    row = t.to_pylist()[3]
    assert json.loads(row["params"]) == {"i": 3}
    assert row["body_sha256"] == hashlib.sha256(row["body"]).hexdigest()
    lines = _manifest(settings)
    assert len(lines) == 1
    m = json.loads(lines[0])
    assert m["file"] == shards[0].name and m["rows"] == 25
    assert m["sha256"] == hashlib.sha256(shards[0].read_bytes()).hexdigest()
    assert m["first_fetched_at"] < m["last_fetched_at"]
    assert shards[0].name.startswith("shard-") and shards[0].name.endswith(".parquet")
    assert cache.verify("twse", "ds") == []


def test_flush_writes_partial_shard_and_empty_flush_writes_nothing(settings):
    cache = RawCache(settings)
    cache.flush()
    assert _shards(settings) == []
    _put(cache, 1)
    cache.flush()
    cache.flush()
    assert len(_shards(settings)) == 1 and len(_manifest(settings)) == 1


def test_interrupted_write_leaves_no_shard_and_no_manifest(settings, monkeypatch):
    cache = RawCache(settings)
    _put(cache, 1)

    def boom(*a, **k):
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        cache.flush()
    monkeypatch.undo()
    d = paths.raw_dir(settings, "twse", "ds")
    assert list(d.iterdir()) == []  # no shard and no temporary file
    assert _manifest(settings) == []
    cache.flush()  # the buffer survived, a retry works
    assert len(_shards(settings)) == 1


def test_verify_reports_mismatch_missing_and_unlisted(settings):
    cache = RawCache(settings)
    for i in range(50):
        _put(cache, i)
    for i in range(50, 60):
        _put(cache, i)
    cache.flush()
    a, b, c = _shards(settings)
    with open(a, "ab") as f:
        f.write(b"x")
    b.unlink()
    (
        paths.raw_dir(settings, "twse", "ds") / "shard-20200101T000000000000-deadbeef.parquet"
    ).write_bytes(b"zz")
    got = {(p.kind, p.file) for p in cache.verify("twse", "ds")}
    assert ("sha256_mismatch", a.name) in got
    assert ("missing", b.name) in got
    assert ("unlisted", "shard-20200101T000000000000-deadbeef.parquet") in got
    assert not any(f == c.name for _, f in got)


def test_no_token_in_shard_bytes(settings):
    fake_token = "FAKE-TOKEN-0123456789abcdef"  # decoy, never passed to the cache
    headers = {"Authorization": f"Bearer {fake_token}"}
    assert headers
    cache = RawCache(settings)
    for i in range(25):
        _put(cache, i)
    data = _shards(settings)[0].read_bytes() + _manifest(settings)[0].encode()
    assert fake_token.encode() not in data
    assert b"Authorization" not in data


def test_qa_area_paths(settings):
    cache = RawCache(settings, area="qa")
    _put(cache, 1)
    cache.flush()
    assert len(_shards(settings, "qa")) == 1
    assert (settings.data_dir / "raw" / "qa" / "twse" / "ds").is_dir()
    assert _shards(settings, "raw") == []
    assert _manifest(settings, "ds") == []  # raw manifest untouched
    assert cache.verify("twse", "ds") == []
    with pytest.raises(ValueError):
        RawCache(settings, area="nope")


def test_get_reads_buffer_before_flush_and_returns_latest(settings):
    cache = RawCache(settings)
    key = request_key("GET", "https://x/y", {"i": 1})
    assert cache.get("twse", "ds", key) is None
    _put(cache, 1, body=b"old", key=key, t=T0)
    hit = cache.get("twse", "ds", key)
    assert hit.body == b"old" and hit.shard is None and hit.status == 200
    _put(cache, 1, body=b"new", key=key, t=T0 + timedelta(minutes=1))
    assert cache.get("twse", "ds", key).body == b"new"
    cache.flush()
    hit = cache.get("twse", "ds", key)
    assert hit.body == b"new" and hit.shard == _shards(settings)[0].name
    assert hit.fetched_at == T0 + timedelta(minutes=1)
    _put(cache, 1, body=b"newest", key=key, t=T0 + timedelta(minutes=2))
    assert cache.get("twse", "ds", key).body == b"newest"  # buffer beats shard
    cache.flush()
    assert cache.get("twse", "ds", key).body == b"newest"
    # A fresh instance (another process) reads through the manifest.
    assert RawCache(settings).get("twse", "ds", key).body == b"newest"
    assert RawCache(settings).get("twse", "other", key) is None


def test_naive_timestamp_rejected(settings):
    cache = RawCache(settings)
    with pytest.raises(ValueError):
        cache.put("twse", "ds", "k", "u", {}, 200, b"", datetime(2026, 1, 1))


def test_put_quarantine_writes_one_individual_file(settings):
    cache = RawCache(settings)
    p = cache.put_quarantine("twse", "ds", "k", "https://x", {"a": 1}, 302, b"<html>", T0)
    q = paths.quarantine_dir(settings, "twse", "ds")
    assert p.parent == q and [f.name for f in q.iterdir()] == [p.name]
    row = pq.read_table(p).to_pylist()[0]
    assert row["status"] == 302 and row["body"] == b"<html>"
    assert _shards(settings) == [] and _manifest(settings) == []
