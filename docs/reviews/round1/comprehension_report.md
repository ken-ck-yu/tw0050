## Comprehension review: /home/ken/tw0050/docs/designs/data_platform.md, lines 1-299

Reviewer: `egm-comprehension` (fresh context, document read alone, no context files). Status: completed.

### What this proposes
The document proposes a local data layer for a research project. The project tests whether a machine-learning strategy that holds Taiwan stocks for 2 to 10 days beats costs. Phase 1 only collects and validates data. Prices, corporate actions, fundamentals, flows and macro series come from FinMind and free TWSE/TPEx endpoints. They are cached raw, then parsed into Parquet tables queried with DuckDB. Every clean table carries `event_date` and `available_at`, so a later model cannot use a value before it was knowable. Each month-end the design builds a 200-stock universe, with the top 200 chosen by market cap after a turnover floor, plus watchlist names. Adjusted prices are built in-house. Separate worker agents (A to F) own modules, and agent F runs acceptance checks that write a coverage report.

### How the existing system works, per this document
Little exists beyond research notes. Documents under `docs/` record which FinMind datasets and official endpoints were probed. A "plan" with numbered sections (2, 4, 6.6, 8) holds earlier requirements. The FinMind free tier lacks adjusted prices, market cap and filing dates, and caps requests at 600 per hour. The TWSE/TPEx endpoints are partly undocumented and return HTTP 200 with an HTML error page on bad requests. Several official lists are latest-snapshot only. Nothing is built or deployed. The document does not say how the existing `audit/` folder, agent definitions or `FINMIND_TOKEN` setup work.

### Findings

1. **Blocker**: "the plan" and "plan section N" (lines 49, 43, 122, 147, 154, 239, 56). The design repeatedly defers to "the plan" (sections 2, 4, 6.6, 8) but never says what it is, where it lives, or links it. Key rules are delegated to it: the universe rule, the institutional flows `available_at` rule ("plan section 4"), and the agent split ("plan section 6.6"). The agent-to-dataset split, and why flows get next-day 08:30, cannot be paraphrased without it. Line 56 says "the plan does not say" when a close becomes usable, which implies the plan is authoritative but unseen.

2. **Blocker**: Agents A to F and "Lead" (lines 96, 153-157, 161, 241-246). The roles are never defined. The document does not say whether they are people, AI agents or modules, who "the author" is relative to "Lead", or what "Agent F only" means for enforcement. Line 28 mentions "A separate QA agent" and line 96 says "agent F", but neither explains them. The ownership table and dependency order (line 161) cannot be followed without this.

3. **Major**: Acceptance checks 1 to 8 (lines 62, 260-261, 294). They are referenced ("check 2 requires delisted last trading days", "check 4", "check 6") but never listed. The Goals section is probably the source, but nothing maps goals to check numbers. A reader cannot tell what Agent F verifies or what "pass" means.

4. **Major**: Contradictory or unclear 08:30 rule (lines 54, 124, 126, 127, 132). The quarterly-financials rule picks the statutory deadline "then the next-trading-day 08:30 rule". It is unclear whether 08:30 is applied to the deadline date or to a found filing date. Line 126 says adjustment factors are hidden on their own ex-date. That conflicts with the stated "accepted trade-off" only if ex-rights are known pre-open, which the document does not establish. Line 54 says "Decided" and also "Open" for the same item, so the status is ambiguous.

5. **Major**: Goals vs universe definition (lines 34, 147, 251). "Exactly 200 stocks per month-end" is the top 200 "plus flagged watchlist names". The watchlist ships empty (line 225), but once populated the count exceeds 200. The universe step also excludes stocks under full-delivery or disposition status. It is unclear whether the 200 count holds when fewer than 200 pass the turnover floor. "Exactly 200" is not reconcilable with these rules.

6. **Major**: Tolerance and cross-check pass criteria are undefined (lines 35, 103, 106). "A stated tolerance" is never stated. The "500 random (stock, date) closes" check gives no agreement threshold, so a reader cannot tell what counts as a mismatch. Yahoo `Adj Close` is introduced with no definition of how it is accessed.

7. **Major**: Undefined project-specific terms and artifacts (lines 15, 85-97, 111, 115, 130, 136, 235, 283-285):
   - `collection_set` (lines 93, 147): defined only as "the union of all members". It does not say where it is used, or whether it is a table.
   - `data/state/` completion record format (line 143): no key or format given.
   - `docs/FINMIND_DATASETS.md`, `docs/OFFICIAL_SOURCES.md`, `docs/DATA_DICTIONARY.md`: referenced but not described or linked, and `DATA_DICTIONARY.md` is listed as to be created.
   - `audit/events.jsonl`, `audit/RUN_REPORT_TEMPLATE.md`: never explained.
   - "P0 and P1 datasets" (line 37): the priority tiers are not defined or listed.
   - "option A" and "option B" (lines 72, 73): the options are not stated in this document.
   - "Disposition-restricted" and "full-delivery" (lines 22, 147): Taiwan-specific status regimes with no definition.
   - "MOPS" (line 124): the filing system is never expanded.
   - "swagger files" and "OpenAPI" (lines 53, 78, 108): the swagger/OpenAPI spec files are not identified or linked.

8. **Major**: Alternatives are labelled A and C with no B (lines 165, 171). The chosen design is "option B" (line 72) but has no "Alternative B" section. Alternatives lack a statement of what B is, so the comparison cannot be followed.

9. **Major**: Time arithmetic inconsistencies (lines 139, 168). About 5,600 requests at 5 seconds is about 7.8 hours. Alternative A claims "about 7.5 hours at the limit" for FinMind prices, which is not derivable, since FinMind per-day-per-market requests are not specified. The comparison that rejected Alternative A therefore rests on an unexplained figure.

10. **Major**: Market-cap source for TWSE (lines 60, 106). The market-cap definition for TWSE depends on `TaiwanStockShareholding` `NumberOfSharesIssued`, but `t187ap03_L` is a snapshot only. The document notes this as open. The universe ranking (line 147) therefore depends on an unresolved input, which makes the design's central "top 200 by market cap" output not yet specifiable.

11. **Major**: Agent B's `prices_adjusted` (lines 205, 242, 161). Its primary key is (`stock_id`, `event_date`), with no `market`, but `prices_raw` includes `market`. Whether a stock can move between markets is not addressed. The dependency order says B needs A's stock list but not which tables B reads. How adjustment is computed (factor method, capital-reduction handling) is never described, though it is a stated goal.

12. **Nit**: Key mismatches (lines 207-210). Several tables use different date key names (`announce_date`, `revenue_month`, `period_end`, `month_end`) rather than `event_date`, while line 115 says every clean table has `event_date`. It is not stated how these map to `event_date`.

13. **Nit**: Undefined or inconsistent names (lines 136, 138, 192). `raw_ref` is "path and row of the raw response", but raw files are Parquet with one row per request, so "row" is unclear. "Wall-clock time" and "improve rounds" (line 294) are used without definition; "improve rounds" and "QA round" appear only in the iteration-log reference.

14. **Nit**: Line 15 says the official endpoints "replace the three FinMind datasets that need a paid tier" but the three are never named.

15. **Nit**: Endpoint abbreviations (lines 53, 58, 104, 108, 235) such as `MI_INDEX`, `TWT49U`, `t187ap*`, `exDailyQ` and `rwd` are used as if known. Line 111 partly describes `MI_INDEX` only. A one-line glossary of what each returns would help.

16. **Nit**: Line 57: "(industry category and code pattern)" and line 251's "rule documented and tested" refer to a classification rule that is "not yet specified". The Universe section (line 147) and the `classify` module description (line 251) depend on it, yet the design treats it as a deliverable rather than an open dependency for the Goals.

17. **Nit**: Date: "from 2015-06-01" appears as both the data start and universe rebuild start ("from 2015-06"); the first rebuild would be the last trading day of June 2015, so the first month-end differs from the collection start. This is minor but undocumented.
