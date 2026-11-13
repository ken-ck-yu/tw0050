# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-194`, everything above `## Detailed Implementation Plan`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

Severity totals after deduplication: 1 Blocker, 17 Major, 12 Nit.

The design reviewer did not call the missing Risks & Mitigations section a Blocker. It said several Majors would become Blockers if left unresolved at approval (M1, M5, M6, M7 in its numbering). The structural reviewer rated the missing section a Blocker against the standard, and this report keeps that rating.

## Prioritized Findings (Blockers -> Major -> Nits)

### No Risks & Mitigations section - Severity: Blocker
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** whole document (between Alternatives, line 163, and NFR, line 189)
* **Discrepancy Description**: The standard requires a Risks & Mitigations section covering failure modes, security, scalability limits and mitigations. Risk content is scattered. Failure handling is at 134-139, security is at 191, and throttling is a one-line open question at 64. Risks with no stated mitigation:
  * IP block of the home IP, and the lack of a User-Agent or terms-of-use position for scraping undocumented endpoints.
  * FinMind quota exhaustion.
  * Drift in undocumented endpoints.
  * Missed daily snapshots.
  * Loss of the raw cache.
  * Historical schema variation.
  * Dependence on FinMind for TWSE shares issued.
  * Reliance on scrape-grade `rwd`/`www` endpoints, which the decision log accepted as a risk.
* **Rationale & Recommendation**: Add an `## Risks & Mitigations` table with risk, likelihood, impact, mitigation and owner. Move the throttling, endpoint-drift and market-cap single-source items out of Open Questions into it.

### Alternatives rationale contradicts the document's own numbers - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** lines 139, 168-169
* **Discrepancy Description**: Alternative A is rejected because official bulk files "need far fewer requests". The chosen official route needs about 5,600 requests and about 8 hours (line 139), and FinMind prices are said to take about 7.5 hours (line 168). The official route is not faster. 5,600 requests at 600/hour is about 9.3 hours, not 7.5. Neither figure is derived.
* **Rationale & Recommendation**: Derive both costs on the same basis (requests, rate, hours). Restate the rejection on the real grounds: free-tier gaps, independence for the cross-check, official reference prices, delisted coverage, and the absence of FinMind adjusted prices. Note that the FinMind cross-check still costs FinMind requests.

### "Rejected by author" is unlinked and gives no technical reason; Alternatives are incomplete and mislabelled - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** lines 72-74, 163-187
* **Discrepancy Description**:
  * Rejections at 169, 175, 181 and 187 cite the author with no linked decision and no concrete trade-off.
  * `docs/DECISIONS.md` has no entries for the two decisions at lines 72-73 (official primary source, 08:30 rule).
  * Labels are A, C, then unlabelled alternatives. "Option B" (lines 72, 175) and "option A" (line 74) are never defined. The letters mix the source decision and the time-rule decision.
  * The chosen design is never described as a baseline.
  * Missing alternatives: a paid FinMind tier (rejected in DECISIONS.md, absent here), building adjusted prices in-house versus buying `TaiwanStockPriceAdj`, and the storage choice (line 45 forbids a database without comparing).
* **Rationale & Recommendation**: Add the two DECISIONS.md entries and link them. State the technical trade-off for each rejection, for example double storage and an undefined conflict rule. Add a "Chosen approach" subsection. Use one heading scheme such as "Alternative 1: ...", grouped by decision. Say "rejected by author" once, in the section intro. Add the missing alternatives or point to DECISIONS.md.

### Universe and market cap can silently reintroduce survivorship bias - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 57, 60, 106, 129, 147
* **Discrepancy Description**:
  * TWSE market cap depends on FinMind `NumberOfSharesIssued`. Nothing shows it covers delisted names or deep history. A null market cap drops a delisted stock from the universe, which is the bias the design aims to remove.
  * Market flag and common-stock filter come from `TaiwanStockInfo`, a current snapshot, so market migrations and industry changes are not point-in-time.
  * The common-stock rule is only an open question (line 57) although it feeds the universe.
* **Rationale & Recommendation**: Define null-market-cap handling and report its count. Extend acceptance check 2 to universe membership of delisted names. Derive "listed on date" and market from the daily price files. Consider reconstructing shares issued from TWT49U/TWTAUU events. Fix the common-stock rule before approval.

### No request budget beyond prices; free-tier coverage unproven - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** lines 38, 60-63, 139
* **Discrepancy Description**: Only the price files are costed. About 400 collection-set names across roughly 15-20 per-stock FinMind datasets is about 6,000 or more requests, or 10 or more hours at 600/hour. `TaiwanStockShareholding` for the full candidate universe (about 1,800 or more names including delisted) is needed before the collection set exists. The 500-close cross-check, the `BWIBBU_d` cross-check and the event ranges add more. The design does not say whether FinMind accepts all-stocks-per-date calls on the free tier.
* **Rationale & Recommendation**: Add a per-dataset table of request count and hours, for FinMind and for the official endpoints, and state the request granularity verified.

### Snapshot-only sources have no collection mechanism - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** lines 26, 48, 107-108, 129, 147
* **Discrepancy Description**:
  * Line 26 calls snapshot-only sources valuable and line 48 says collection starts at approval. The plan has no dataset list, module owner, schedule or catch-up rule. A WSL2 machine that sleeps loses that day permanently.
  * Line 26 says disposition and attention lists "publish only a latest snapshot". `OFFICIAL_SOURCES.md` shows TWSE `punish` and `notice` return history for 2015 and 2024 windows. Only the TPEx swagger equivalents are unprobed snapshots.
  * Line 107 names TPEx swagger endpoints as primary with no history caveat, while the universe rule (line 147) needs history back to 2015.
  * Full-delivery exclusion has no identified source (`TWT85U` is unlocated).
* **Rationale & Recommendation**: Correct line 26 (TWSE has history, TPEx history is unprobed). Scope the snapshot jobs (dataset, owner, schedule, missed-day detection). State that TPEx disposition history before approval is unavailable and how the universe treats it.

### Raw cache is the only irreplaceable asset and is unprotected - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 143, 192-193
* **Discrepancy Description**: Everything is "rebuilt from data/raw/". Losing raw costs 8 or more hours of throttled refetch, and snapshot-only history is permanently lost. There is no backup, manifest or checksum. `data/state/` and raw can disagree (state says done, file missing). `raw_ref` (line 115) depends on layout stability.
* **Rationale & Recommendation**: Add a second-copy rule for `data/raw/`, a hashed manifest, a state-versus-raw reconcile step, and a content hash in `raw_ref`.

### Schema validation and stop rule rest on one 2015 sample - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 103, 111, 137-138
* **Discrepancy Description**:
  * The validator requires an exact field list, but only the saved 2015-06-01 `MI_INDEX` response was checked, and the `otc` file on that one day. Column sets and sign encoding likely differ across 11 years. A strict match could stop the 8-hour run on false drift, or silently mis-map columns.
  * "3 consecutive bad responses" can be tripped by legitimate empty days (a 9-day Lunar New Year gap) or a calendar error. The holiday cross-check may only cover the current year.
  * The 5-second spacing and the stop count have no stated basis.
* **Rationale & Recommendation**: Probe one date per year per endpoint. Version the schema per era and add value sanity checks (high >= low, close within the limit band). Separate "legitimately empty" from "malformed". State that 5 s and 3 are chosen defaults.

### `available_at` rules are missing, or leak the future, for several datasets - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 32, 117-130
* **Discrepancy Description**:
  * Goal line 32 promises a rule for every dataset. Missing: delisting events, PER/PBR, shareholding and shares issued, benchmark index, FX, rates, bond yields, futures and futures institutional data, securities lending and short-sale balances.
  * Backward-adjusted prices are restated at every future ex-date. A stored adjusted close with `available_at` equal to the trade date leaks the future.
  * Reference tables (calendar, stock info) get `available_at` equal to retrieval time (2026), so a join on `available_at` hides them for all history.
  * US prices: `Adj_Close` is retroactively restated, early-close days are unhandled, and the VIX +30 minute offset is unverified (VIX settles at 16:15 ET).
* **Rationale & Recommendation**: Store adjustment factors as events with `available_at` and derive adjusted prices as of a timestamp. State whether adjustment is price-only or total return. Exempt reference tables explicitly, or derive them from price files. Use raw US Close. Add rows for every dataset.

### Restatement rule contradicts upsert rule - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** lines 130, 143
* **Discrepancy Description**: Line 130 keeps the first-reported value. Line 143 upserts on the primary key, which overwrites, and says overwriting collected data needs approval. It is not stated which wins or whether `fetched_at` is in the key. FinMind returns only current values, so pre-approval history cannot be first-reported, and using filing deadlines with restated values is a lookahead leak the document does not acknowledge.
* **Rationale & Recommendation**: Make restatement-prone clean tables insert-only for the first observation, with later differing values in a revisions table. State the historical limitation in the dictionary and Goals.

### Financials and revenue `available_at` depend on mechanisms with no home in the design - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** lines 15, 99-109, 123-124, 153
* **Discrepancy Description**:
  * MOPS lookup ("actual filing date when found in MOPS") appears in neither the source list, the policy table, the diagram, nor the clients module. Availability is unprobed.
  * `create_time` only began in June 2026 (plan section 4), so the revenue fallback is effectively the primary rule and "fallback share reported" is not a meaningful guardrail.
  * `create_time` may be FinMind ingestion time rather than publication time.
* **Rationale & Recommendation**: Either scope MOPS (owner, method, cross-check row) or drop it. Say which revenue rule is primary. Use official `t187ap05_L` going forward as ground truth. Verify `create_time` semantics.

### Open Questions mixes decided items, stale items, risks and has no gating - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`, `egm-style`
* **Affected Scope:** lines 51-64
* **Discrepancy Description**:
  * Line 53 (endpoint change) is already decided at 137-138 (stop, no silent fallback).
  * Line 54 holds a decision plus a question, and mixes three topics.
  * Line 58 lists `MFI94U` as unlocated while line 111 sources the benchmark from `MI_INDEX`.
  * Line 64 (throttling) is a risk.
  * Thirteen items have no owner, no blocking tag, no default, and no resolution path. Several block P0 deliverables: TPEx capital reductions (FinMind alternative is paid), delisted last trading days, the benchmark.
* **Rationale & Recommendation**: Remove resolved items. Tag each remaining item blocking or non-blocking, with the blocked deliverable, a default, and an owner. Probe the cheap blockers before approval. Move risks to the new section. Consider placing the section after the architecture it references.

### Unsupported verification claim for `MI_INDEX` total return index - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 58-59, 103, 111
* **Discrepancy Description**: Line 111 states as fact that `MI_INDEX` has a total return table including TAIEX and Taiwan 50. `OFFICIAL_SOURCES.md` (line 28) says `MFI94U` was not found and FinMind's benchmark `data_id` is unprobed. The only evidence is an uncited saved 2015-06-01 response, yet it supports the source choice for about 2,800 days.
* **Rationale & Recommendation**: Name the saved file and state "verified on one day (2015-06-01)" next to the source policy table. Move the "0050 is an ordinary row" remark out of this paragraph.

### Goal 3 count is inconsistent - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`, `egm-style`
* **Affected Scope:** line 34
* **Discrepancy Description**: "Exactly 200 stocks per month-end ... plus flagged watchlist names" yields more than 200 rows with watchlist names. It is also undefined when fewer than 200 pass the floor. The 60-day turnover needs about 3 months of prior prices before 2015-06.
* **Rationale & Recommendation**: Define the check as exactly 200 ranked members plus N flagged watchlist rows. Say what happens below 200. Collect prices from about 2015-03 or start the universe later.

### Acceptance and goal metrics are weak or unmeasurable - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 32-35
* **Discrepancy Description**:
  * "Within a stated tolerance" (line 35) is never stated, and Yahoo has known Taiwan adjustment errors.
  * "No row has `available_at` earlier than `event_date`" is nearly vacuous for revenue, whose `event_date` is the first of the month. Line 180 admits it would not catch real lookahead.
  * The 99% price-coverage denominator is undefined for suspended days and IPO months.
* **Rationale & Recommendation**: State the tolerance. Add `available_at` > period end and revenue `available_at` > the 1st of the following month, plus comparison with observed retrieval times going forward. Define the coverage denominator.

### Claim that no paid tier is needed outruns the evidence - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 15, 37, 58-63
* **Discrepancy Description**: The Free tier is not shown to cover TPEx capital reductions (61), shares-issued history (60), delisted last trading days (62) or US tickers (63). Line 15 says official endpoints "replace the three FinMind datasets" without that qualifier. DECISIONS.md line 27 makes the same claim.
* **Rationale & Recommendation**: Rewrite as "No paid tier is known to be needed; items X, Y, Z are unresolved."

### Document is not self-contained - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 15, 43, 62, 96, 121, 144, 154
* **Discrepancy Description**: It cites "plan section 8", "plan section 6.6", "plan section 4", "acceptance check 2", "agent F" and "Agents A to E" without naming or linking the plan or defining the roles and checks. Paths are in backticks, not links.
* **Rationale & Recommendation**: Add a References subsection linking `DATA_COLLECTION_PLAN.md`, `docs/FINMIND_DATASETS.md`, `docs/OFFICIAL_SOURCES.md` and `docs/DECISIONS.md`. Inline the acceptance checks or say they live in the plan.

### 08:30 rule caveat placed in Open Questions while the document treats it as settled - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 54, 126-127, 132, 180-181
* **Discrepancy Description**: Line 54 says "Decided" and "Open: whether that is too late". Lines 132 and 180-181 treat it as settled and call it "conservative". Line 126 says adjustment factors are not visible on their own ex-date, a concrete consequence that belongs with the rule. The design reviewer notes the question is largely answerable, since measures take effect the next trading day and 08:30 precedes the 09:00 open.
* **Rationale & Recommendation**: Close the question or give it a measurable form (how many disposition announcements precede 08:30). Put the caveat at the disposition row. State the effect instead of "conservative".

### 18:00 price assumption stated in three places - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-design`, `egm-structural`
* **Affected Scope:** lines 33, 56, 121-122
* **Discrepancy Description**: The assumption is repeated, and line 121 says "the plan does not set this", pointing at a document the reader has not seen.
* **Rationale & Recommendation**: State it once, with a reference to the open-question number and a plan to record real publication times going forward. TWSE publishes closes after about 13:30, so 18:00 is later than needed.

### Source independence of the 500-close check is overstated - Severity: Nit
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 28, 55
* **Discrepancy Description**: FinMind prices derive from TWSE/TPEx, so the check detects FinMind or ingestion errors, not exchange errors. "A separate QA agent checks the result against official figures" is only as strong as the 500-sample check.
* **Rationale & Recommendation**: Say what the check does and does not detect.

### Overstated or unsourced claims in Overview and Problem - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 11, 13, 19, 22, 28
* **Discrepancy Description**: "earns a real edge after costs" is a hypothesis stated as the aim. "so later research cannot see the future" is an absolute guarantee. "commonly make Taiwan backtests look better" and "tend to have done badly" are unsourced. Line 28 ("one storage layout, one table convention...") is a contents sentence, and "one point-in-time rule per dataset" conflicts with lines 177-181.
* **Rationale & Recommendation**: Use the plan's measurable criterion or mark it out of scope. Soften to "can join on the time a value was available" and "can inflate backtest returns". Drop the contents sentence.

### Problem list terms are mixed; line 54 is overloaded - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 20-24, 54
* **Discrepancy Description**: "Untradable prices" lists wrong adjusted prices (an adjustment error) next to limit-locked prices (tradability). Line 54 packs three topics, a decision and a question into one bullet.
* **Rationale & Recommendation**: Retitle as "Price errors and untradable prices". Split line 54.

### Heading names, alternative label style and ordering - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 51, 68, 163-187
* **Discrepancy Description**: "Technical Plan (Architecture)" does not match the standard's "Proposed Architecture". Alternative headings mix "Alternative A", "Alternative C" and "Alternative: ...".
* **Rationale & Recommendation**: Rename the section and use one heading scheme (see the Alternatives finding).

### Diagram gaps and misalignment - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 77-97, 143
* **Discrepancy Description**: `data/state/` and `config/` are missing from the diagram, MOPS is missing, and annotations at lines 90-91 are misaligned.
* **Rationale & Recommendation**: Update the diagram.

### Duplicated statements; exceptions to the single time rule not acknowledged - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 60, 70-73, 106, 132, 141-143, 181, 192
* **Discrepancy Description**: The decisions block repeats in line 54 and line 132. The shares-issued uncertainty appears three times (55, 60, 106). The approval-for-overwrite rule appears twice (141-143, 192). The "one conservative rule" claim at 181 is weakened by exceptions at 123-124 and 128-129.
* **Rationale & Recommendation**: Keep one canonical statement of each and link to it. Add a sentence noting the exceptions.

### Rate-limit and footprint statements need basis - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 64, 137-139, 193
* **Discrepancy Description**: The throttle assumption (5 s, one in flight) has no evidence, and the count of probe requests (about 16) is not given. "To avoid an IP block" overstates; OFFICIAL_SOURCES.md reports no blocking. "A few GB" lacks its arithmetic (about 0.8 GB uncompressed for prices, and the compression assumption is unstated). "Report if disk becomes a constraint" has no threshold.
* **Rationale & Recommendation**: State the basis and the sample size. Say "to limit the risk of an IP block". Show the footprint arithmetic and give a threshold or drop the sentence. Consider an adaptive limiter.

### Security and absolute claims at line 191 - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 191
* **Discrepancy Description**: "never printed, logged, cached or committed" is absolute. The Gitleaks claim is backed by DECISIONS.md line 15.
* **Rationale & Recommendation**: Name the controls, for example headers stripped before cache write.

### "When present" rules lack expected coverage; fallback share promised but not reported consistently - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 32, 123, 125
* **Discrepancy Description**: Several rules say "when present" without the expected share of rows. Line 123 reports the fallback share, but 125 and other rows do not, despite the goal at line 32.
* **Rationale & Recommendation**: Make the table consistent.

### Undefined abbreviations - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** first uses of TPEx, MOPS, ROC, PER
* **Discrepancy Description**: These appear without expansion.
* **Rationale & Recommendation**: Expand on first use or add a short glossary.

### Paid-tier promise has no content above the header - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 37-38
* **Discrepancy Description**: The design says it lists what a paid tier would add, but nothing in lines 1-194 does. It may sit below the header.
* **Rationale & Recommendation**: Add a short table or remove the claim.

### Calendar and holiday cross-check coverage unverified - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 108
* **Discrepancy Description**: The TWSE `holidaySchedule` cross-check may only cover the current year.
* **Rationale & Recommendation**: Verify coverage or state the limit.
