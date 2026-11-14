import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a1_helpers import (  # noqa: E402
    daily_routes,
    make_ctx,
    parquet_files,
    qfiis_body,
    query,
)

from twdata.common import schema  # noqa: E402
from twdata.common.timeutil import TAIPEI  # noqa: E402
from twdata.ingest import daily_official, market_cap  # noqa: E402

D1, D2 = date(2016, 6, 1), date(2016, 6, 2)


@pytest.fixture(autouse=True)
def clean_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def build(tmp_path):
    # day 2 has no shares row for 0050, so there must be no market cap for it (no carry-forward)
    routes = daily_routes(
        qfiis=lambda p: qfiis_body(drop_ids=("0050",)) if p["date"] == "20160602" else qfiis_body()
    )
    ctx, _, _ = make_ctx(tmp_path, routes, [D1, D2])
    daily_official.run(ctx, D1, D2)
    return ctx


def test_market_cap_rows(tmp_path):
    ctx = build(tmp_path)
    market_cap.run(ctx, D1, D2)
    rows = query(
        ctx,
        "SELECT close, shares_issued, market_cap_ntd, available_at FROM default_market_cap "
        "WHERE stock_id = ? AND event_date = ?",
        ["0050", D1],
    )
    assert rows == [
        (63.7, 1745500000, 63.7 * 1745500000, datetime(2016, 6, 1, 18, 0, tzinfo=TAIPEI))
    ]
    # no shares row on day 2: no market cap row, no carry-forward
    assert (
        query(ctx, "SELECT * FROM default_market_cap WHERE stock_id='0050' AND event_date=?", [D2])
        == []
    )
    # a no-trade row has no close: no market cap
    assert query(ctx, "SELECT * FROM default_market_cap WHERE stock_id='0059'", []) == []
    # a priced stock missing from the shares file has no market cap either
    assert query(ctx, "SELECT * FROM default_market_cap WHERE stock_id='1312A'", []) == []
    # TPEx stock: close times shares
    r = query(
        ctx,
        "SELECT market_cap_ntd FROM default_market_cap WHERE stock_id='1258' AND event_date=?",
        [D1],
    )
    assert r == [(37.6 * 35463884,)]


def test_market_cap_rerun_writes_nothing(tmp_path):
    ctx = build(tmp_path)
    market_cap.run(ctx, D1, D2)
    before = parquet_files(ctx.settings, "market_cap")
    assert before
    market_cap.run(ctx, D1, D2)
    assert parquet_files(ctx.settings, "market_cap") == before


def test_market_cap_without_inputs_is_a_noop(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(), [D1])
    market_cap.run(ctx, D1, D1)
    assert not (ctx.settings.data_dir / "clean" / "market_cap").exists()


def test_months_split():
    got = list(market_cap._months(date(2016, 11, 15), date(2017, 2, 3)))
    assert got == [
        (date(2016, 11, 15), date(2016, 11, 30)),
        (date(2016, 12, 1), date(2016, 12, 31)),
        (date(2017, 1, 1), date(2017, 1, 31)),
        (date(2017, 2, 1), date(2017, 2, 3)),
    ]


def test_registry():
    assert set(market_cap.DATASETS) == {"market_cap"}


def test_stock_on_two_markets_same_day_raises():
    from datetime import UTC

    from twdata.common.cleanstore import KeyUniquenessError

    base = {
        "stock_id": "9999",
        "event_date": D1,
        "close": 1.0,
        "shares_issued": 1,
        "price_available_at": datetime(2016, 6, 1, 10, tzinfo=UTC),
        "shares_available_at": datetime(2016, 6, 1, 10, tzinfo=UTC),
    }
    recs = [{**base, "market": "TWSE"}, {**base, "market": "TPEx"}]
    with pytest.raises(KeyUniquenessError):
        market_cap.market_cap_rows(recs, datetime.now(UTC))
