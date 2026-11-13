# Decision log

Newest last. Each entry: what was decided, why, and what was rejected.

## 2026-11-13: answers to the plan's open questions (Ken)

- **FinMind tier:** free first. Use fallbacks (for example market cap as close times shares issued) and list what a paid tier would unlock. No subscription without Ken's approval. Rejected: subscribing up front.
- **Storage:** local disk under `data/`, gitignored.
- **Liquidity floor:** NT$20M median daily turnover, because positions will be small.
- **Universe size:** 200, with case-by-case additions through `config/watchlist.yaml`.
- **Still open:** employer personal-account dealing rules, to be confirmed before any live trading phase.

## 2026-11-13: token handling (Ken)

- Token lives in a gitignored `.env`, loaded at runtime. `.claude/settings.json` denies agent reads and edits of `.env*`. Gitleaks runs as a pre-commit hook. Rejected: token in the shell profile.

## 2026-11-13: audit hook uses python3 instead of jq (Lead)

- `jq` is not installed and installing it needs sudo. `.claude/hooks/audit.sh` writes the same metadata-only fields using `python3`. Rejected: waiting for sudo access.

## 2026-11-13: FinMind tier findings (Lead)

- Free account: 600 requests/hour. Three datasets need a paid tier: `TaiwanStockPriceAdj`, `TaiwanStockCapitalReductionReferencePrice`, `TaiwanStockMarketValue`. Fallbacks are in `docs/FINMIND_DATASETS.md`.

## 2026-11-13: free official sources replace the three paid FinMind datasets (Lead)

- TWSE and TPEx publish ex-rights, capital-reduction and quarterly-share data free back to 2015-06 (see `docs/OFFICIAL_SOURCES.md`). No paid tier is needed for the P0 set. Disposition and attention stock lists are now sourced from TWSE `punish` and `notice`. Rejected: paid FinMind tier. Risk accepted: the `rwd` / `www` endpoints are undocumented and scrape-grade, so every response is cached raw.

## 2026-11-13: research findings and decisions made by the Lead (not yet reviewed by Ken)

Evidence is in `docs/OFFICIAL_SOURCES.md` and `docs/research/`. Each item below is reversible and open to review.

- **TWSE market cap** comes from `MI_QFIIS` issued shares times close. FinMind `TaiwanStockShareholding` becomes the cross-check. Rejected: FinMind as the only source.
- **Last trading day and survivorship** come from the daily files of both markets. Delisting lists are a cross-check only, because the last trade is 3 to 13 days before the listed delisting date in all six stocks checked, codes are reused, and the TPEx list may miss transfers to TWSE.
- **TPEx suspension and trading-restriction history** uses the per-day `chtm` report as a proxy, with daily snapshots of `bulletin/warning` and `bulletin/sprc` starting at approval. Rejected: waiting for a better source.
- **Revenue `available_at`**: FinMind `create_time` is the load date and exists only from 2026-04-21, so the 10th-of-next-month fallback is the primary rule, not a fallback.
- **Open, needs Ken:** a live FinMind probe (maximum years per call, US ticker coverage, `create_time` and shares-issued blanks), and whether to accept the TWSE full-delivery gap.
- **Correction:** the FinMind docs list the Free limit as 300 requests per hour and Register as 600. The live user-info endpoint reported 600 for this account on 2026-11-13, and that value wins.

## 2026-11-13: TWSE full-delivery gap accepted (Ken, on the Lead's assessment)

- No TWSE source for full-delivery status was found, and the daily files carry no marker. TPEx folds it into `chtm`. Impact is low: a stock must also rank in the top 200 by market cap and clear the NT$20M turnover floor, so only a handful of stock-months could slip in. QA reports how many. A daily `TWT85U` snapshot starts at approval. Rejected: further blind path searching.
