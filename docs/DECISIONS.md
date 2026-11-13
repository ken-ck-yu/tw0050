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
