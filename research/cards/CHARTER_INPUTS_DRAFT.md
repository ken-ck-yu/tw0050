# Research charter inputs (draft, pre-charter)

**Status: draft, pre-charter.** Notes from the author's discussion on 2026-11-14 with the research lead (discussion only). Nothing here is approved, active or tested. It changes no rule in `CLAUDE.md`, `config/ownership.yaml` or any amendment. Sections marked **AUTHOR** record what the author said. Sections marked **LEAD** are the lead's proposals or objections and need the author's decision.

Context read for this session: `CLAUDE.md`, `docs/amendments/early_lane.md`, `docs/amendments/research_lane_DRAFT.md`, `research/cards/H1_revenue_drift.md`, `DATA_COLLECTION_PLAN.md` section 10 (and sections 2 to 4 for the dataset list). No data under `data/` was read. Collection status of any dataset is unknown to the lead.

---

## 1. AUTHOR: assumptions

**A1. Taiwan is a retail market.** The author believes the market has many individual investors and end customers, so the atmosphere differs from US or European markets.

**A2. Community data can shape signals.** The author believes community data (news, blogs, public internet, analysts, YouTube) can shape a lot of signals and indications, so this side should be researched.

**A3. The product is decision support.** The author trades by hand. The system finds a stock likely to go up or down and tells the author the target price. The author buys. The author waits roughly 1 to 14 days (an estimate).

**A4. Each call carries a full trade plan.** The author needs:
- a buy signal and buy price;
- a sell signal and sell price (the target);
- a cut-off if the target is reached;
- a stop price at which to sell if the stock does not go as expected;
- a daily update on each open call.

**A5. Trading window.** About 1 to 14 days.

## 2. AUTHOR: research approach (principles, "not strict")

1. Data-driven and scientific, aiming for statistically higher chances, not hunches.
2. Path: hypothesis, then experiment, then trial runs. If results are consistent, implement.
3. Question and research which data is optimal, not assume it.
4. Study how other companies do well and decide whether it makes sense for us to learn from it.
5. Consider multi-layer models against simple models.
6. Look for noise and bias.
7. Know when a model is not working, and quantify it.
8. Build a knowledge base and a findings base.
9. The author pasted a third-party text as an example of the kind of material to study. See section 6.

---

## 3. LEAD: problems found with the assumptions

### 3.1 Community data (A2)

- **Not in scope today.** The plan's "Deferred" list excludes news and forums, and Phase 1 is data collection only. Adding a source needs design approval (rule 6) and a plan amendment. The lead makes no network requests except web search.
- **Direction of causality.** People often post after the move. A card must test whether text precedes the price move.
- **Timestamps.** Posts are edited and deleted, and history is survivor-biased. YouTube upload times and transcripts have the same problem. Every text row needs a first-seen `available_at` that we capture ourselves. Backfilled history is not trusted blindly.
- **LLM scoring leakage.** A model that knows the outcome can score an old post with that knowledge. A scoring model and prompt must be frozen and tested for leakage.
- **Researcher degrees of freedom.** Many sources, scoring methods and lookbacks make false discoveries easy. Every variant spends test budget.
- **Terms of service and legal limits** on scraping.
- **Safer starting point:** official, timestamped sources (TWSE and MOPS material-information announcements; analyst target-price changes if a clean feed exists). Adding these needs the author's approval.

### 3.2 Decision-support workflow (A3, A4, A5)

- **Rule 3.** A daily signal service is not broker code but is arguably "trading code" outside research. It likely needs its own amendment and belongs to a later phase. No order or broker code is ever written.
- **Evaluator.** The frozen evaluator is built for portfolios. Target, stop and time exit are path-dependent (triple-barrier style). The evaluator would need to support them, and the author approves any evaluator change.
- **Same-day touch ambiguity.** A daily bar cannot show whether target or stop was hit first. The evaluator spec must state a conservative rule (stop first).
- **Cost hurdle.** Sell tax is 0.3% (plan). Commission is up to about 0.1425% each way before any broker discount, so round trip is about 0.58% before discount and slippage. The evaluator takes the discount as a parameter. A 1% target is hard to clear. A 3% to 5% target is plausible.
- **Stops can fail.** The daily limit is plus or minus 10%. A stock locked limit-down cannot be sold and one locked limit-up cannot be bought. The stop price is not a guarantee.
- **False precision.** A target price should come with the probability of hitting the target before the stop and an expected value, not a price alone.

---

## 4. LEAD: proposed guidelines (need AUTHOR decision)

### 4.1 Card template additions
Each card gets an **exit block**: entry rule, target, stop, time stop, and the cost hurdle the target must clear. The 10.3 template stays otherwise.

### 4.2 Call log
Every live call is logged before the outcome as an append-only record: stock, entry, target, stop, time stop, probability, rationale, timestamp. Never edited. This forward log is the cleanest out-of-sample evidence.

### 4.3 Gates
1. Card committed.
2. Backtest on train, one look at validation, with the card's falsification rule.
3. Forward paper log with no money.
4. The author trades small by hand.

Pass criteria are written on the card beforehand: net Sharpe, deflated Sharpe, cost drag, and consistency across sub-periods and sectors (the sign holds in most years, not only pooled).

### 4.4 Model complexity ladder
Default to the simplest model that works:
1. Baselines: equal-weight universe and 0050.
2. A single rank signal.
3. Regularised linear model.
4. Gradient-boosted trees.
5. Ensemble or meta-label layer.

A step up is allowed only if it beats the step below after costs on validation by a margin fixed in advance. A second layer, if ever used, decides when not to trade and position size, not direction.

### 4.5 Bias and noise checklist (every card is reviewed against it)
- Lookahead and wrong `available_at`.
- Survivorship (delisted names).
- Multiple testing and trial counts (deflated Sharpe, cumulative over the lane).
- Overlapping labels with 1 to 14 day holds: use purged, embargoed walk-forward splits.
- Limit-lock states and first-touch order inside a daily bar.
- Cost model realism.
- Regime dependence.
- Data defects (missing splits, bad `available_at`, universe gaps): stop and report, never patch inside a strategy.
- LLM leakage if a model scores text.
- Crowding.

### 4.6 Data exploration counts as trials
- Outcome-blind work (distributions, missingness, correlations) is free.
- Outcome-aware exploration is allowed on the train window only, and is logged and counted against the budget.

### 4.7 Data earns its place by ablation
A dataset stays only if it adds out-of-sample value over the cheaper baseline, weighed against collection cost, rate limits and paid-tier gates (paid tier is a human gate).

### 4.8 When a model is not working: monitors fixed before go-live
- Rolling rank information coefficient and its t-statistic.
- Calibration of stated probabilities (Brier score or reliability curve).
- Net return against the backtest's expected range.
- Drawdown beyond a simulated percentile.
- Feature drift.
- Turnover and cost drift.

Kill rules are pre-registered (for example a sequential test that stops after enough adverse evidence).

### 4.9 Sample-size reality
Detecting a 55% hit rate against 50% (5% one-sided, 80% power) needs roughly 600 independent trades. One call a day with a 14-day hold is too slow for this. The forward log is confirmation. Backtest consistency and sub-period checks carry most of the weight.

### 4.10 Learning from other firms
Each outside claim is graded: peer-reviewed or replicated, working paper, practitioner claim, anecdote. Each note says whether it applies to us (scale, market, frequency) and which card tests it. Outside ideas are adopted as hypotheses, never as conclusions.

### 4.11 Knowledge base and findings base (proposal, not created)
```
research/knowledge/
  INDEX.md
  sources/    one note per paper or claim: claim, source, evidence grade, applies to us?
  biases.md   the 4.5 checklist with a worked example per bias
  findings/   one note per experiment: card id, run id, window, result, verdict
```
Null and failed results are full entries. Each finding links to its card and to its `research/experiment_log.jsonl` run id. Creating this tree needs the author's approval and ownership entries.

---

## 5. Conflicts and stale items in the repository

- `research_lane_DRAFT.md` rule 6 still says validation 2022-01 to 2024-06 and holdout from 2024-07-01. `early_lane.md` (author decision) says validation to 2025-12-31 and holdout from 2026-01-01.
- The committed H1 card's falsification window is 2022-01 to 2024-06. A change would need a new card. The author decides.
- `early_lane.md` point 2 says one hypothesis at a time, starting with H1. Cards H2 to H5 cannot be tested until the charter or the lane changes.
- The research lane draft is not approved and not active. These notes feed that approval.

## 6. Third-party text pasted by the author (kept as an unverified reference)

Two pasted passages from an AI chat. Citation markers pointed to nothing. None of it has been verified.

**Passage 1, multi-day multi-layer ML.** Claims that multi-layer models can work live, citing:
- Numerai: a crowd of models combined by a meta-model, with reported 2024 net return 25.45% and Sharpe 2.75, and an asset-manager capacity commitment.
- Man AHL: an ensemble of classifiers feeding a volatility-targeted risk engine.
- Meta-labeling studies: a primary signal plus a secondary filter, with reported Sharpe around 1.25 after fees.

Counter-evidence claimed: a veteran quant's Reddit report of little consistent alpha; a 1,800-strategy comparison where simple regularised models beat deep ones; an SSRN study where regime shifts pushed ensemble AUC to about 0.51. Winning rules claimed: keep the primary signal simple, use layer two for risk and sizing, favour orthogonal data over depth.

**Passage 2, Taiwan specifics.** Claims about retail share (50% to 60%), supply-chain lead-lag, chip data (institutional flows and broker-branch data), crowding by global quant funds, the plus or minus 10% limit distorting features, tax friction, and fast theme rotation.

**Lead's handling:** filed as practitioner claims or anecdote (grade low), not evidence. Specific doubts:
- Numerai and Man AHL are selected successes at a scale and structure unlike a single trader's long-only 1 to 14 day calls.
- The round-trip cost quoted (0.35% to 0.45%) is lower than the plan's rates imply (about 0.58% before discount).
- Broker-branch data is deferred in the plan and its availability and cost are unclear.
- Order-book features need intraday data, which the plan defers.
- The retail-share figure needs checking against TWSE investor-type turnover statistics.

Lessons kept: simple primary signal, second layer for filtering and sizing only, orthogonal data over depth, regime-shift risk, limit-lock handling in features.

## 7. Open decisions for the author

1. Is community data a Phase 1 charter addition, or a research-only idea for now? Is the official-sources start (MOPS announcements, analyst target-price feed) approved?
2. Is a decision-support (daily call) tool a later phase needing its own amendment, and is the evaluator to be extended for target, stop and time-exit?
3. Approve the card template exit block and the call log (4.1 and 4.2)?
4. Approve the knowledge base location (`research/knowledge/`) and ownership entries?
5. Should the lead verify the pasted claims by web search (Numerai, Man AHL, the 1,800-strategy study, the SSRN regime paper)?
6. Resolve the validation and holdout dates conflict in section 5.
7. Should foreign-investor flow get its own card or stay out of H2?
8. Should the dividend and quarterly-financials cards be drafted once announcement-date fields are checked?

## 8. Card index (draft, pre-charter)

| Card | Idea | Status |
|---|---|---|
| H1 | Drift after monthly revenue surprises | Committed earlier, not tested |
| H2 | Investment-trust net-buying persistence | Draft, pre-charter |
| H3 | US semis overnight move and Taiwan open-to-close | Draft, pre-charter |
| H4 | Reversal after extreme day-trading share | Draft, pre-charter |
| H5 | Avoid lottery-like stocks (low MAX) | Draft, pre-charter |

Ideas not yet written as cards: supply-chain lead-lag (needs a customer-supplier map the plan lacks), margin balance extremes (likely H4 variant), dividend run-up, quarterly financials drift, disposition and attention stocks, index inclusion, a 1-month reversal or momentum baseline (a control, not a strategy).
