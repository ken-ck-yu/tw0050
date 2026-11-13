# Consolidated Review Report

**Target:** `docs/designs/data_platform.md` (299 lines, status Draft)
**Mode:** uninterrupted full flow, five stages
**Verdict:** not ready for approval. The design is a sound outline, but an implementer would still make schema, algorithm, rule and ownership decisions, and several inputs that feed the universe are unresolved.

## Reviewer status

| Stage | Report | Reviewers | Status |
| --- | --- | --- | --- |
| 5 Zoom out | `zoom_out_report.md` | `egm-zoom-out`, `egm-inventive-catalyst` | completed |
| 6 Comprehension | `comprehension_report.md` | `egm-comprehension` | completed |
| 7 Critic | `critic_report.md` | `egm-design`, `egm-structural`, `egm-style` | completed |
| 8 Intermediate zoom out | `intermediate_zoom_out_report.md` | `egm-zoom-out` | completed |
| 9 Implementation readiness | `implementation_readiness_report.md` | `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` | completed after one retry |

Stage 9's first run through the synthesizer returned without waiting for its reviewers and wrote nothing. It was recorded as failed and re-dispatched directly. `egm-codebase-details` reports 17 Majors in its summary but numbers 22 in its list. All five stage reports are raw reviewer output, so counts below are by theme, not a sum.

Stage totals as reported: Stage 5 (0 Blocker, 11 Major, 8 Nit), Stage 6 (2 Blocker, 9 Major, 6 Nit), Stage 7 (1 Blocker, 17 Major, 12 Nit), Stage 8 (0 Blocker, 11 Major, 10 Nit), Stage 9 (9 Blocker, 44 Major, 21 Nit across the three reviewers, with overlap).

## Limits of this review

Fresh reviewers share the same model's blind spots. None of them ran a probe, so claims about endpoints are checked only against the saved notes. The reviewers could not see `CLAUDE.md`. Two corrections to the design that the lead already knew about were not applied (see Blocker 9).

## Blockers

1. **No Risks & Mitigations section.** Failure modes, IP blocking, quota exhaustion, endpoint drift, missed snapshots, raw-cache loss and single-source market cap are scattered or unstated. (S7 structural)
2. **Circular ownership across Agents A, B and D, and nobody owns the all-stock first pass.** The universe needs prices and shares issued before the collection set exists. (S5, S8, S9 all three reviewers)
3. **Unresolved inputs feed the build.** TWSE shares-issued history, delisted names' last trading days, TPEx capital reductions, four unlocated endpoints, the common-stock rule, the FinMind benchmark `data_id`. These should be probed before approval or have a stated fallback. (S5, S7, S9)
4. **Adjusted prices: algorithm unspecified, and one stored `available_at` per row cannot be point-in-time.** Specify the factor method and store raw prices plus a factor table with an as-of view, plus a computed test. (S5, S7, S8, S9)
5. **`available_at` rules incomplete or contradictory.** Missing rows for delistings, PER, shareholding, benchmark, FX, rates, futures, lending, derived tables. Ex-date visibility, MOPS, weekend and holiday edge cases, US DST, and beyond-calendar behaviour are unspecified. (S5, S7, S9)
6. **Per-table schemas and the file list are not enumerable.** Twelve tables have no key. Key columns are not mapped to `event_date`. (S6, S9)
7. **Agent F cannot create the validation suite.** `.claude/agents/qa-goldfish.md` grants only `Read, Grep, Glob, Bash` and forbids edits under `src/` (verified). `.claude/settings.json` has no deny rule protecting `src/twdata/validate/**`. Fixing this means editing `.claude/`, which needs your decision. (S9 codebase-details)
8. **The universe cannot be built for 2015-06 to about 2015-09.** A 60-day median turnover needs about 3 months of earlier prices. (S9, S7)
9. **Two statements in the design are wrong or stale.** Line 26 says disposition and attention lists "publish only a latest snapshot", but `docs/OFFICIAL_SOURCES.md` shows TWSE has history (the lead flagged this earlier and did not fix it). Line 111 presents the `MI_INDEX` total return table as fact with one day of evidence. (S7)
10. **The document is not self-contained.** It cites "the plan", Agents A to F, "Lead" and acceptance checks 1 to 8 without defining or linking them. (S6 Blockers, S7)

## Major (by theme)

**Decisions resting on weak evidence**
* The Alternative A rejection contradicts the design's own numbers: about 5,600 official requests (about 8 hours) against "7.5 hours" for FinMind, neither derived. FinMind prices are queried per stock over a date range, so the real count is likely much lower. Reopen or restate the rationale. (S5, S7, S8)
* "No paid tier needed" outruns the evidence: TPEx capital reductions, shares-issued history, delisted last trading days and US tickers are unproven on the free tier. (S7)
* "Rejected by author" is unlinked; the two author decisions (official primary, 08:30 rule) are not yet in `docs/DECISIONS.md`; labels A, C skip B; missing alternatives (paid tier, in-house adjusted prices, storage). (S5, S6, S7)

**Survivorship and point-in-time**
* Null market caps and the current-snapshot `TaiwanStockInfo` can silently drop delisted names. (S7)
* The restatement rule (first-reported kept) contradicts the upsert rule, and FinMind returns only current values, so pre-approval history cannot be first-reported. (S7, S9)
* The 08:30 rule discards pre-announced ex-date information and may be late for status lists. Largely settled by your decision, with one open sub-question. (S5, S8)
* Revenue `create_time` began only in June 2026, so the fallback is effectively the primary rule. (S7)

**Reliability and operations**
* The failure breaker can false-trip on legitimate empty days. The strict schema check rests on one 2015 sample across 11 years. Classify responses (ok, valid-empty, transient, drift) and version schemas per era. (S5, S7, S8)
* The raw cache is the only irreplaceable asset and has no backup, manifest or checksum. (S7)
* Snapshot-only sources have no collector, schedule, owner or `first_seen_at`, although history is lost daily. (S5, S7, S8, S9)
* No cross-process limiter although agents B to E run in parallel against shared hosts. No atomic-write rule. (S9)
* Request budget covers only prices. FinMind datasets for about 400 names are uncosted. (S7, S9)

**Structure and scope**
* Per-dataset modules where one table-driven FinMind ingestor would do; row-level provenance columns on every table; no stated choice among standard limiter, retry and cache libraries. (S5, S8)
* Upsert on year-partitioned Parquet has no named mechanism. Partitioning conflicts between `reference/` and `clean/year=YYYY/`. (S5, S9)
* No phases with exit gates. Test plan is a category list. Client contracts, CLI grammar, packaging, lock-file command undefined. (S9)
* Multiple agents write one `DATA_DICTIONARY.md`; Lead-owned `schema.py` and `cli.py` that workers must extend; fixtures saved as `*.parquet` or `*.csv` would be ignored by `.gitignore`. (S9)
* Goal 3 ("exactly 200 plus watchlist") is inconsistent. Tolerance for adjusted prices is never stated. (S6, S7, S9)
* Open Questions contains decided items, stale items and risks, with no owner or blocking tag. (S7)

## Nits (by theme)

Overstated or unsourced claims in the Overview; the 18:00 price assumption repeated three times; US price timestamp and DST; unlisted checks (sign parsing, 200-member count); survivor-skewed Yahoo sample; module-name collision (`calendar.py`); abbreviations not expanded; diagram gaps; duplicated statements; vague qualifiers; template-style labels.

## Recommended order before approval

1. Probe the cheap blockers: one date per year per endpoint for schema variants, delisted names' last trading days, TWSE shares issued, the four unlocated endpoints, TPEx capital reductions, and the benchmark `data_id`.
2. Add Risks & Mitigations. Fix lines 26 and 111. Fix the Alternative A rationale with derived request counts.
3. Define the all-stock fetch stage and ownership, and break the A/B/D cycle.
4. Specify the adjusted-price algorithm, the as-of view, per-table schemas, the complete `available_at` table, and the upsert mechanism.
5. Decide the `.claude/` changes for Agent F (your call).
6. Add the snapshot collector and start it early, since its history cannot be recovered.

## Traceability matrix

| Consolidated item | Source findings |
| --- | --- |
| Blocker 1 | S7 structural Blocker |
| Blocker 2 | S5 raw-fetch ownership; S8 same; S9 readiness M6/M7, codebase-details #2, style M1 |
| Blocker 3 | S5 survivorship; S7 survivorship and Open Questions; S9 readiness B2/B6/M5, codebase-details #17 |
| Blocker 4 | S5 adjusted prices; S7 `available_at` leak; S8 same; S9 readiness B3, codebase-details #12 |
| Blocker 5 | S5 derived tables, US timestamp; S7 `available_at` gaps; S9 readiness B4 |
| Blocker 6 | S6 findings 11-12; S9 readiness B1/B5, codebase-details #5/#8/#9 |
| Blocker 7 | S9 codebase-details #1, #7 (lead verified #1) |
| Blocker 8 | S9 codebase-details #3; S7 Goal 3 |
| Blocker 9 | S7 snapshot-only; S7 MI_INDEX claim |
| Blocker 10 | S6 Blockers 1-2; S7 not self-contained |
| Major: Alternative A | S5, S7, S8 |
| Major: paid-tier claim, rationale labels | S7 |
| Major: failure breaker, schema drift | S5, S7, S8, S9 #18 |
| Major: raw cache, snapshots, cross-process | S7, S9 |
| Major: ingestor shape, provenance, libraries | S5, S8 |
| Major: phasing, tests, client contracts, packaging | S9 all three reviewers |
