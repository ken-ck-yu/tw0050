"""Adjusted prices built from raw prices and the corporate-action table (Agent B).

``adjusted_close(t) = close(t) * product of factors of events with event_date > t`` and, when
``as_of`` is given, ``available_at <= as_of``. Nothing is stored. The factor of one event is
``reference_price / prev_close`` (``prev_close`` falls back to ``halt_close``), or ``1 / ratio``
when ``reference_price`` is null. For ``split`` and ``par_value_change`` the factor is exactly
``1 / ratio`` and ``reference_price`` is never used. An event whose factor cannot be computed
gets factor 1.0 and is counted in ``UNCOMPUTABLE_EVENTS`` (the run report quotes it).
Two events on one date multiply.

The connection must have the views of ``twdata.common.views.register_views`` (this module reads
``default_prices_raw`` and ``default_corporate_actions``).
"""

from __future__ import annotations

from datetime import datetime

import pyarrow as pa

from twdata.common.views import register_view

FACTOR_TYPES = ("ex_dividend", "ex_rights", "capital_reduction", "split", "par_value_change")
LABEL = "validation and labels only, not a feature input"

_FACTOR_SQL = """CASE
      WHEN action_type IN ('split', 'par_value_change')
        THEN CASE WHEN ratio IS NOT NULL AND ratio > 0 THEN 1.0 / ratio ELSE 1.0 END
      WHEN reference_price IS NOT NULL AND coalesce(prev_close, halt_close) > 0
        THEN reference_price / coalesce(prev_close, halt_close)
      WHEN ratio IS NOT NULL AND ratio > 0 THEN 1.0 / ratio
      ELSE 1.0
    END"""

_UNCOMPUTABLE = """(CASE
      WHEN action_type IN ('split', 'par_value_change')
        THEN NOT coalesce(ratio IS NOT NULL AND ratio > 0, FALSE)
      ELSE NOT coalesce(reference_price IS NOT NULL
             AND coalesce(prev_close, halt_close) > 0, FALSE)
           AND NOT coalesce(ratio IS NOT NULL AND ratio > 0, FALSE)
    END)"""

# Events whose factor could not be computed (null prev_close, or null reference_price with no
# ratio) get factor 1.0 and are counted here; adjusted_series adds to it on every call.
UNCOMPUTABLE_EVENTS = 0


def adjusted_sql(
    *, with_as_of: bool, with_stocks: bool, only_available_prices: bool = False
) -> str:
    """The SQL of the adjusted series. Parameters are `$asof` and `$sids` when used."""
    types = ", ".join(f"'{t}'" for t in FACTOR_TYPES)
    ev_where = [f"action_type IN ({types})"]
    p_where = ["TRUE"]
    if with_as_of:
        ev_where.append("available_at <= $asof")
        if only_available_prices:
            p_where.append("available_at <= $asof")
    if with_stocks:
        ev_where.append("list_contains($sids, stock_id)")
        p_where.append("list_contains($sids, stock_id)")
    if with_as_of:
        window = (
            "SELECT DISTINCT market, stock_id, event_date AS wd FROM default_corporate_actions "
            "WHERE (available_at IS NULL OR available_at > $asof)"
            + (" AND list_contains($sids, stock_id)" if with_stocks else "")
        )
    else:
        window = (
            "SELECT NULL::VARCHAR AS market, NULL::VARCHAR AS stock_id, NULL::DATE AS wd "
            "WHERE FALSE"
        )
    return f"""
WITH ev AS (
  SELECT market, stock_id, event_date AS ed, {_FACTOR_SQL} AS f
  FROM default_corporate_actions
  WHERE {" AND ".join(ev_where)}
),
evd AS (
  SELECT market, stock_id, ed, product(f) AS f FROM ev GROUP BY market, stock_id, ed
),
p AS (
  SELECT market, stock_id, event_date, close
  FROM default_prices_raw
  WHERE {" AND ".join(p_where)}
),
j AS (
  SELECT p.market, p.stock_id, p.event_date, p.close, coalesce(product(evd.f), 1.0) AS factor
  FROM p LEFT JOIN evd
    ON p.market = evd.market AND p.stock_id = evd.stock_id AND evd.ed > p.event_date
  GROUP BY p.market, p.stock_id, p.event_date, p.close
),
w AS ({window})
SELECT j.market, j.stock_id, j.event_date, j.close, j.factor,
  j.close * j.factor AS adjusted_close,
  (w.wd IS NOT NULL) AS is_ex_date_window
FROM j LEFT JOIN w
  ON j.market = w.market AND j.stock_id = w.stock_id AND j.event_date = w.wd
ORDER BY j.market, j.stock_id, j.event_date
"""


def adjusted_series(
    con,
    as_of: datetime | None = None,
    stock_ids=None,
    *,
    only_available_prices: bool = False,
) -> pa.Table:
    """Return (market, stock_id, event_date, close, factor, adjusted_close, is_ex_date_window).

    ``as_of`` (timezone-aware) keeps only events with ``available_at <= as_of``; an event with a
    null or later ``available_at`` leaves ``is_ex_date_window`` true on its event date. With
    ``as_of=None`` every event counts (full adjustment, validation only) and the flag is false.
    Raw price rows are not filtered by ``available_at`` unless ``only_available_prices`` is set.
    """
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    sql = adjusted_sql(
        with_as_of=as_of is not None,
        with_stocks=stock_ids is not None,
        only_available_prices=only_available_prices,
    )
    params: dict = {}
    if as_of is not None:
        params["asof"] = as_of
    if stock_ids is not None:
        params["sids"] = [str(s) for s in stock_ids]
    global UNCOMPUTABLE_EVENTS
    types = ", ".join(f"'{t}'" for t in FACTOR_TYPES)
    count_sql = (
        f"SELECT count(*) FROM default_corporate_actions WHERE action_type IN ({types}) "
        f"AND {_UNCOMPUTABLE}"
        + (" AND available_at <= $asof" if as_of is not None else "")
        + (" AND list_contains($sids, stock_id)" if stock_ids is not None else "")
    )
    UNCOMPUTABLE_EVENTS += con.execute(count_sql, params).fetchall()[0][0]
    return con.sql(sql, params=params or None).to_arrow_table()


# Full adjustment, labelled for validation and labels only. Features use adjusted_series(as_of=).
register_view("adjusted_close", adjusted_sql(with_as_of=False, with_stocks=False))

DATASETS: dict = {}
