import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a1_helpers import fixture_bytes, jb, make_ctx, parquet_files, query  # noqa: E402

from twdata.clients.base import DriftError  # noqa: E402
from twdata.common import paths, schema, state  # noqa: E402
from twdata.common.timeutil import TAIPEI  # noqa: E402
from twdata.ingest import snapshots  # noqa: E402

FIXTURE_FOR = {
    "twse_TWT85U": "snapshot/twse_TWT85U.json",
    "twse_t187ap25_L": "snapshot/twse_t187ap25_L.json",
    "tpex_spendi_today": "snapshot/tpex_spendi_today.json",
    "tpex_trading_warning_note": "snapshot/tpex_trading_warning_note.json",
}
GENERIC = jb([{"k": "v", "中文": 1}])


def live_routes(bodies=None):
    bodies = bodies or {}

    def make(name):
        def fn(params):
            b = bodies.get(name)
            if b is not None:
                return b() if callable(b) else b
            if name in FIXTURE_FOR:
                return fixture_bytes(FIXTURE_FOR[name])
            return GENERIC

        return fn

    return [(path, make(name)) for name, (_, path) in snapshots.SNAPSHOTS.items()]


def table(name):
    return f"default_snapshot_{name}"


def test_fifteen_tables_registered_and_dataset_names():
    assert len(snapshots.SNAPSHOTS) == 15
    for name in snapshots.SNAPSHOTS:
        t = schema.TABLES[f"snapshot_{name}"]
        assert t.key == ("payload_sha256", "snapshot_date", "row_seq")
        assert "row_json" in t.columns and t.klass == "joinable"
    assert sum(1 for n in snapshots.SNAPSHOTS if n.startswith("twse_")) == 11
    assert set(snapshots.DATASETS) == {"snapshots"}
    assert callable(snapshots.run)


def test_snapshot_rows_mapping():
    body = fixture_bytes("snapshot/twse_t187ap25_L.json")
    # 2026-11-13 23:30 UTC is 2026-11-14 07:30 in Taipei
    at = datetime(2026, 11, 13, 23, 30, tzinfo=UTC)
    rows = snapshots.snapshot_rows("twse_t187ap25_L", body, at)
    src = json.loads(body)
    assert len(rows) == len(src) and len(rows) > 0
    first = rows[0]
    assert first["snapshot_date"] == date(2026, 11, 14) == first["event_date"]
    assert first["first_seen_at"] == at == first["available_at"] == first["fetched_at"]
    assert first["payload_sha256"] == hashlib.sha256(body).hexdigest()
    assert [r["row_seq"] for r in rows] == list(range(len(src)))
    assert first["row_json"] == json.dumps(src[0], ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize(
    "body", [b'{"a": 1}', b"[1, 2]", b"<html>no</html>", b'"text"', b'[{"a":1}, 3]']
)
def test_payload_not_a_list_of_objects_is_drift(body):
    with pytest.raises(DriftError):
        snapshots.snapshot_rows("twse_TWT85U", body, datetime.now(UTC))


def stopgap(tmp_path, entries):
    """Write a stopgap folder: entries are (name, stamp, body). Returns the settings' manifest."""
    ctx, transport, cache = make_ctx(tmp_path, live_routes(), [date(2026, 11, 13)])
    root = paths.snapshot_dir(ctx.settings)
    lines = []
    for name, stamp, body in entries:
        f = root / name / f"{stamp}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
        lines.append(
            json.dumps(
                {
                    "name": name,
                    "file": f"{name}/{stamp}.json",
                    "fetched_at": stamp,
                    "status": 200,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
        )
    (root / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ctx, transport


def test_import_stopgap_and_idempotence(tmp_path):
    a = fixture_bytes("snapshot/twse_TWT85U.json")
    b = fixture_bytes("snapshot/tpex_spendi_today.json")
    ctx, _ = stopgap(
        tmp_path,
        [
            ("twse_TWT85U", "2026-11-14T083955", a),
            ("twse_TWT85U", "2026-11-14T153000", a),  # same payload, same day
            ("tpex_spendi_today", "2026-11-13T230500", b),
            ("tpex_trading_warning_note", "2026-11-14T084121", b"[]"),  # empty list
        ],
    )
    counts = snapshots.import_stopgap(ctx)
    assert counts == {
        "twse_TWT85U": 2,
        "tpex_spendi_today": 1,
        "tpex_trading_warning_note": 1,
    }
    n = len(json.loads(a))
    rows = query(
        ctx,
        f"SELECT snapshot_date, first_seen_at, available_at, min(row_seq), count(*) "
        f"FROM {table('twse_TWT85U')} GROUP BY ALL",
        [],
    )
    # the two same-day captures of one payload collapse to one set of rows, first fetch wins
    assert len(rows) == 1 and rows[0][4] == n
    assert rows[0][0] == date(2026, 11, 14)
    assert rows[0][1] == datetime(2026, 11, 14, 8, 39, 55, tzinfo=TAIPEI) == rows[0][2]
    r = query(ctx, f"SELECT DISTINCT snapshot_date FROM {table('tpex_spendi_today')}", [])
    assert r == [(date(2026, 11, 13),)]  # 23:05 Taipei on the 13th, not the next UTC day
    # the empty payload wrote nothing but is recorded in state
    assert not (ctx.settings.data_dir / "clean" / "snapshot_tpex_trading_warning_note").exists()
    assert state.is_done(ctx.settings, "snapshot_tpex_trading_warning_note", date(2026, 11, 14))
    # rerun: nothing new
    before = parquet_files(ctx.settings, "snapshot_twse_TWT85U")
    assert snapshots.import_stopgap(ctx) == {}
    # even with the import state wiped, identical rows are skipped by the writer
    paths.state_file(ctx.settings, snapshots.STOPGAP_STATE).unlink()
    snapshots.import_stopgap(ctx)
    assert parquet_files(ctx.settings, "snapshot_twse_TWT85U") == before


def test_import_stopgap_missing_manifest_and_unknown_name(tmp_path):
    ctx, _ = stopgap(tmp_path, [("not_a_snapshot", "2026-11-14T083955", b"[]")])
    assert snapshots.import_stopgap(ctx) == {}
    paths.snapshot_dir(ctx.settings).joinpath("manifest.jsonl").unlink()
    assert snapshots.import_stopgap(ctx) == {}


def test_import_stopgap_checks_sha_and_payload(tmp_path):
    ctx, _ = stopgap(tmp_path, [("twse_TWT85U", "2026-11-14T083955", b'{"a": 1}')])
    with pytest.raises(DriftError):  # payload is a dict, not a list
        snapshots.import_stopgap(ctx)
    f = paths.snapshot_dir(ctx.settings) / "twse_TWT85U" / "2026-11-14T083955.json"
    f.write_bytes(b"[]")  # now the manifest sha256 no longer matches
    with pytest.raises(DriftError):
        snapshots.import_stopgap(ctx)
    assert not (ctx.settings.data_dir / "clean" / "snapshot_twse_TWT85U").exists()


def test_run_fetches_fifteen_endpoints_without_cache(tmp_path):
    ctx, transport, cache = make_ctx(tmp_path, live_routes(), [date(2026, 11, 13)])
    snapshots.run(ctx)
    assert len(transport.calls) == 15
    assert cache.flushes == 1
    r = query(
        ctx, f"SELECT count(*), count(DISTINCT payload_sha256) FROM {table('twse_TWT85U')}", []
    )
    assert r[0][0] == len(json.loads(fixture_bytes("snapshot/twse_TWT85U.json")))
    assert query(ctx, f"SELECT count(*) FROM {table('twse_TWTB4U')}", []) == [(1,)]
    # a second run the same day with an unchanged payload hits the live endpoint again, and
    # the identical rows are skipped
    before = parquet_files(ctx.settings, "snapshot_twse_TWTB4U")
    snapshots.run(ctx)
    assert len(transport.calls) == 30
    assert parquet_files(ctx.settings, "snapshot_twse_TWTB4U") == before
    # a changed payload adds a new set of rows (new sha256)
    ctx2, transport2, _ = make_ctx(
        tmp_path, live_routes({"twse_TWTB4U": jb([{"k": "changed"}])}), [date(2026, 11, 13)]
    )
    snapshots.run(ctx2)
    r = query(ctx, f"SELECT count(DISTINCT payload_sha256) FROM {table('twse_TWTB4U')}", [])
    assert r == [(2,)]


def test_run_with_stopgap_import_then_live(tmp_path):
    a = fixture_bytes("snapshot/twse_TWT85U.json")
    ctx, transport = stopgap(tmp_path, [("twse_TWT85U", "2026-11-14T083955", a)])
    snapshots.run(ctx)
    r = query(ctx, f"SELECT min(first_seen_at) FROM {table('twse_TWT85U')}", [])
    assert r[0][0] == datetime(2026, 11, 14, 8, 39, 55, tzinfo=TAIPEI)


def test_live_non_list_payload_writes_nothing_and_raises(tmp_path):
    routes = live_routes({"twse_TWT85U": jb({"stat": "x"})})
    ctx, _, _ = make_ctx(tmp_path, routes, [date(2026, 11, 13)])
    with pytest.raises(DriftError):
        snapshots.run(ctx)
    assert not (ctx.settings.data_dir / "clean" / "snapshot_twse_TWT85U").exists()


def test_live_empty_list_is_recorded_in_state_only(tmp_path):
    routes = live_routes({"twse_TWT85U": b"[]"})
    ctx, _, _ = make_ctx(tmp_path, routes, [date(2026, 11, 13)])
    snapshots.fetch_live(ctx, "twse_TWT85U")
    assert not (ctx.settings.data_dir / "clean" / "snapshot_twse_TWT85U").exists()
    today = datetime.now(TAIPEI).date()
    doc = state.load(ctx.settings, "snapshot_twse_TWT85U")
    assert doc is not None and doc["completed"][0][0] <= today.isoformat() <= doc["completed"][0][1]


def test_two_runs_with_different_bodies_write_two_sets_of_rows(tmp_path):
    state_body = {"n": 1}

    def body():
        return jb([{"day": state_body["n"], "x": "a"}, {"day": state_body["n"], "x": "b"}])

    ctx, transport, _ = make_ctx(
        tmp_path, live_routes({"tpex_spendi_today": body}), [date(2026, 11, 13)]
    )
    snapshots.fetch_live(ctx, "tpex_spendi_today")
    state_body["n"] = 2
    snapshots.fetch_live(ctx, "tpex_spendi_today")
    assert len(transport.calls) == 2  # the second run is not served from the cache
    r = query(
        ctx,
        "SELECT count(*), count(DISTINCT payload_sha256) FROM default_snapshot_tpex_spendi_today",
        [],
    )
    assert r == [(4, 2)]
