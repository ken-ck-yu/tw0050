# Taiwan Systematic Trading: Data Collection Plan

Handover brief for Claude Code. Phase 1 is **data collection only**: no modelling, no backtesting, no broker or order code.

## 1. Context

**Goal of the overall project:** test whether an ML-driven, multi-day (roughly 2 to 10 trading day) buy/sell strategy on Taiwan equities has a real edge after costs.

**Success measure:** out-of-sample Sharpe ratio above 1 after realistic costs, benchmarked against buy-and-hold 0050. The original aspiration was 3% a week; treat that as a hypothesis the data will most likely reject, not a design target.

**Decisions already made**

| Decision | Choice |
|---|---|
| Market | Taiwan: TWSE-listed and TPEx (OTC) common stocks |
| Universe | Top 200 by market cap, point-in-time, with a liquidity floor; extra names added case by case via a watchlist |
| Data tier | FinMind free tier first; report what a paid tier would unlock before spending |
| Storage | Local disk, gitignored |
| Sectors | All sectors, each stock tagged; tech is a flag, not a filter |
| History | From 2015-06-01 (the daily price limit widened from 7% to 10% that month) |
| Holding period | Multi-day, so full 0.3% sell tax applies (not the 0.15% day-trade rate) |
| Execution | Via a Taiwan brokerage account (later phase) |
| News, blogs, forums | Deferred to a later phase |

## 2. Universe rule

Rebuild on the last trading day of each month from 2015-06 onwards:

1. Start with all common stocks listed on TWSE or TPEx **on that date**, including names that were later delisted.
2. Exclude ETFs, ETNs, TDRs, preferred shares, warrants and stocks under full-delivery or disposition status.
3. Apply the liquidity floor: 60-day median daily turnover of at least NT$20M (keep this as a config parameter). Positions will be small, so the floor is set low to keep more mid and small caps.
4. Rank by market cap and keep the top 200.
5. Add any names on `config/watchlist.yaml`. Stocks outside the top 200 are added case by case on Ken's decision, each with a date and reason, and flagged as `watchlist` in the membership table so results can be reported with and without them.

Output: `universe_membership` with one row per (month_end, stock_id), plus rank, market cap and turnover.

**Collection set** = the union of every stock that was ever a member. Expect roughly 350 to 450 names. Collect prices and market cap for all stocks first (needed to build the universe), then collect the heavier datasets for the collection set only.

## 3. Data inventory

Primary source is FinMind (`pip install FinMind`, API v4). Cross-check against the TWSE OpenAPI (`https://openapi.twse.com.tw/v1`) and TPEx. **Dataset names below are from memory: verify each against the current FinMind docs before use, and record which ones need a paid tier.**

### P0: required before anything else

| Data | FinMind dataset (verify) | Frequency | Notes |
|---|---|---|---|
| Stock list, industry, market | `TaiwanStockInfo` | Snapshot | Gives sector tags and TWSE/TPEx flag |
| Delisted stocks | `TaiwanStockDelisting` | Event | Needed to avoid survivorship bias |
| Trading calendar | `TaiwanStockTradingDate` | Daily | Taiwan has typhoon closures and long Lunar New Year breaks |
| Daily OHLCV, raw | `TaiwanStockPrice` | Daily | Keep raw prices for limit-up/limit-down detection |
| Daily OHLCV, adjusted | `TaiwanStockPriceAdj` | Daily | For return calculation |
| Dividends and ex-dates | `TaiwanStockDividend`, `TaiwanStockDividendResult` | Event | Validate the adjusted series |
| Capital reductions, splits | `TaiwanStockCapitalReductionReferencePrice` | Event | Same purpose |
| Market cap | `TaiwanStockMarketValue` | Daily | May be paid tier; fallback is close times shares issued |
| Benchmark | 0050 and TAIEX total return (`TaiwanStockTotalReturnIndex`) | Daily | 0050 is the benchmark |

### P1: core signals

| Data | FinMind dataset (verify) | Frequency | Notes |
|---|---|---|---|
| Monthly revenue | `TaiwanStockMonthRevenue` | Monthly | **Highest-priority signal. See point-in-time rules in section 4** |
| Institutional net buy/sell | `TaiwanStockInstitutionalInvestorsBuySell` | Daily | Foreign, investment trust, dealer |
| Foreign shareholding | `TaiwanStockShareholding` | Daily | Also gives shares issued |
| Margin and short balances | `TaiwanStockMarginPurchaseShortSale` | Daily | Retail leverage proxy |
| Securities lending | `TaiwanStockSecuritiesLending`, `TaiwanDailyShortSaleBalances` | Daily | Institutional short interest |
| Day-trading volume | `TaiwanStockDayTrading` | Daily | Speculation intensity |
| Valuation ratios | `TaiwanStockPER` | Daily | PER, PBR, dividend yield |
| US overnight prices | `USStockPrice` or another US source | Daily | NVDA, AMD, AVGO, AAPL, MU, TSM (ADR), SOXX, QQQ, SPY, VIX |

### P2: secondary

| Data | FinMind dataset (verify) | Frequency | Notes |
|---|---|---|---|
| Quarterly financials | `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`, `TaiwanStockCashFlowsStatement` | Quarterly | Need filing dates, not period-end dates |
| USD/TWD | `TaiwanExchangeRate` | Daily | Foreign flow driver |
| Rates and bond yields | `InterestRate`, `GovernmentBondsYield` | Daily | US 2Y and 10Y, Taiwan policy rate |
| TAIEX futures and options | `TaiwanFuturesDaily`, `TaiwanFuturesInstitutionalInvestors` | Daily | Index-level positioning |
| Disposition and attention stocks | TWSE/TPEx announcements | Event | Trading restrictions that block fills |

### Deferred (do not build now)

News, PTT and other forums, broker-branch data, tick and intraday data.

## 4. Point-in-time rules (non-negotiable)

Every table must carry two dates:

- `event_date`: the period the value describes.
- `available_at`: the earliest timestamp (Asia/Taipei) at which a trader could have known it.

Features may only ever be joined on `available_at`.

Specific cases:

- **Monthly revenue:** FinMind added a `create_time` column in June 2026; older rows are blank. For blank rows, set `available_at` to the 10th of the following month, rolled forward to the next trading day, 18:00 Taipei time. Where possible, recover true announcement dates from MOPS and record how often the fallback was used.
- **Quarterly financials:** use the actual filing date. If missing, use the statutory deadlines (Q1 by 15 May, Q2 by 14 Aug, Q3 by 14 Nov, annual by 31 Mar).
- **Institutional flows, margin, lending:** published after the close, so available for the **next** trading day.
- **US data:** the US close on calendar day D is available before the Taiwan open on D+1. Align on timestamps, not on matching calendar dates.
- **Restatements:** store the first-reported value. If the source overwrites history, note it in the data dictionary.

## 5. Storage and repo layout

```
data/
  raw/<source>/<dataset>/...        # untouched API responses, Parquet
  clean/<dataset>/year=YYYY/...     # typed, deduplicated, with available_at
  reference/                        # stock list, calendar, universe_membership
src/twdata/
  clients/                          # FinMind, TWSE, TPEx clients with rate limiting
  ingest/                           # one module per dataset
  universe/                         # universe construction
  validate/                         # QA checks
docs/
  DATA_DICTIONARY.md                # every table, column, unit, source, caveats
  COVERAGE_REPORT.md                # produced by QA
config/settings.yaml                # start date, liquidity floor, universe size
```

- Format: Parquet, queried with DuckDB. No database server.
- Ingestion must be idempotent and resumable: re-running fills gaps without duplicating rows.
- Respect API rate limits (check the current FinMind limits for free and registered tiers); cache every response in `raw/`.
- API token via `FINMIND_TOKEN` environment variable. Never commit secrets or data files.

## 6. Agent framework

Three patterns are combined, each doing a different job.

| Pattern | Job in this project | How it runs in Claude Code |
|---|---|---|
| Elephant-Goldfish (design review) | Catch gaps and unstated assumptions in the spec before any code exists | Google's EGM plugin. The lead session is the Elephant; fresh-context subagents are the Goldfish |
| Swarm (orchestrator and workers) | Collect independent datasets in parallel | The lead spawns subagents A to E, each owning its own files |
| Evaluator-optimizer loop | Improve iteratively until the data passes QA | Agent F's validation suite is the objective evaluator; failures go back to the owning agent |

### 6.1 One-off setup

1. Update Claude Code, then install the EGM plugin and start a new session:
   ```
   claude plugin marketplace add google/elephant-goldfish-model
   claude plugin install egm@egm
   ```
2. Create the repo (Ken's `claude-template` starter is a suitable base) and put this file at the root.
3. Add a `CLAUDE.md` with the standing rules: point-in-time rules from section 4, no secrets or data in git, no modelling or trading code in this phase, each agent edits only its own files.
4. Add subagent definitions in `.claude/agents/` (Markdown with YAML frontmatter: `name`, `description`, `tools`, `model`):
   - `ingest-worker`: read, write, edit, bash. Used for agents A to E.
   - `qa-goldfish`: read, grep, glob, bash only. No write access to `src/`. Used for agent F.
5. Set `FINMIND_TOKEN` in the environment.
6. Optional: agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). Not needed for collection, where workers only report results back. Consider it later for research debates, where agents need to challenge each other. It is experimental, needs an interactive session and costs more tokens.

### 6.2 Workflow

**Step 1. Design (Elephant).** The lead reads this brief and runs `/egm:egm-draft` to turn it into `docs/designs/data_platform.md`: schemas, module boundaries, rate-limit strategy, per-dataset `available_at` logic.

**Step 2. Review (Goldfish).** Run `/egm:egm-review docs/designs/data_platform.md`. Fresh reviewers see only the document and referenced material, not this conversation. Work through findings with the resolve step. **Ken approves the design before any ingestion code is written.**

**Step 3. Swarm.** The lead spawns A first, then B to E in parallel. Every spawn prompt states: the objective, the files that agent owns, the output format, what is explicitly another agent's job, and the stopping condition. The lead coordinates and does not write ingestion code itself.

**Step 4. Independent QA (Goldfish again).** Agent F starts in a fresh context with only `DATA_DICTIONARY.md`, section 7 of this brief and read access to the data. It must not be given the workers' conversations or reasoning.

**Step 5. Improve loop.** F's failures are written to `docs/QA_FINDINGS.md`, each tagged with the owning agent. The lead re-spawns that worker with the finding, the worker fixes it, and F re-runs the full suite. Log every round in `docs/ITERATION_LOG.md` (what failed, what changed, result).

**Step 6. Drift check.** At the end, run `/egm:egm-drift-report docs/designs/` to confirm the code still matches the approved design.

### 6.3 Loop guardrails

- **The builder never grades its own work.** F writes no ingestion code and workers never edit the validation suite.
- **Checks are computed, not judged.** Row counts, cross-source price matches and date comparisons decide pass or fail, not an agent's opinion. Fresh reviewers share the same model's blind spots, so numeric checks against official TWSE data are the real safety net.
- **Cap the loop at three rounds.** Anything still failing goes to Ken with the evidence.
- **Human gates:** design approval, any paid data tier, anything that deletes or overwrites collected data.
- **Keep parallelism to three to five workers** and give each a disjoint set of files.

### 6.4 Warning for the later research phase

A self-improving loop is safe here because data quality has an objective answer. In the modelling phase the same loop becomes dangerous: agents that iterate until a backtest looks good are an automated overfitting machine. Section 10 sets out the research loop. Its core rules:

- A final holdout period the agents cannot read at all.
- Every experiment logged, so the number of attempts is known and results can be discounted for multiple testing.
- The evaluator is fixed code written before any strategy, including costs, and no strategy agent may edit it.
- Ken approves any change to the evaluation method.

### 6.5 References

- Google EGM plugin: https://github.com/google/elephant-goldfish-model
- Anthropic, multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- Claude Code agent teams and subagents: https://code.claude.com/docs/en/agent-teams
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- Google Co-Scientist and AlphaEvolve: https://docs.cloud.google.com/gemini/enterprise/docs/co-scientist-and-alphaevolve

### 6.6 Agent split

Run the lead first, then A, then B to E in parallel, then F.

| Agent | Scope | Depends on |
|---|---|---|
| Lead | Repo scaffold, config, shared API clients with rate limiting and caching, dataset-name verification against FinMind docs | None |
| A: Reference and universe | Stock list, delistings, calendar, market cap, point-in-time universe, collection set | Lead |
| B: Prices and corporate actions | Raw and adjusted OHLCV, dividends, capital changes, benchmark series | A (stock list) |
| C: Fundamentals | Monthly revenue with `available_at`, quarterly financials, valuation ratios | A (collection set) |
| D: Flows and positioning | Institutional flows, shareholding, margin, lending, day trading | A (collection set) |
| E: Macro and US overnight | US equities, FX, rates, index futures, timestamp alignment | Lead |
| F: QA (independent) | Validation suite and coverage report; must not have written any ingestion code | B to E |

Each agent writes its section of `DATA_DICTIONARY.md` and returns a short summary: rows collected, date range, gaps, anything that needs a paid tier.

## 7. Acceptance checks (agent F)

1. **Coverage:** for every universe member-month, daily prices exist for at least 99% of trading days; list all gaps.
2. **Survivorship:** the collection set contains delisted names, and at least one known delisting is present with prices up to its last trading day.
3. **Adjusted prices:** returns from the adjusted series match raw prices plus dividend and capital-change events within tolerance on a sample of 20 stocks.
4. **Cross-source:** sample 500 random (stock, date) closes and compare FinMind to the TWSE/TPEx official figures.
5. **Price limits:** no raw daily move beyond 10% except on ex-dates, first listing days or documented exceptions.
6. **Point-in-time:** no row has `available_at` earlier than `event_date`; monthly revenue fallback usage is reported.
7. **Duplicates and types:** primary keys unique, no mixed units (revenue in NT$ thousands, volume in shares versus lots stated explicitly).
8. **Universe sanity:** 200 members each month, monthly turnover in membership looks plausible, TSMC (2330) always present.

## 8. Out of scope for this phase

- Feature engineering, modelling, backtesting.
- Any broker API, order placement or live trading code.
- News and social media scraping.

## 9. Open questions for Ken

Answered on 2026-11-13 (copy these into `docs/DECISIONS.md`):

- **FinMind tier:** free first. Use fallbacks (for example, market cap as close times shares issued), and list what a paid tier would unlock. Do not subscribe without Ken's approval.
- **Storage:** local disk under `data/`, gitignored.
- **Liquidity floor:** NT$20M median daily turnover, since individual positions will be small.
- **Universe size:** 200, with case-by-case additions through the watchlist.

Still open:

- Employer personal-account dealing rules: confirm before any live trading phase.

### FinMind token setup

1. Register at finmindtrade.com and verify the email address.
2. Log in; the API token is shown on the account page.
3. Store it outside the repo, for example in the shell profile:
   ```bash
   export FINMIND_TOKEN="paste-token-here"
   ```
   or in a gitignored `.env` file. Never paste it into a prompt, a commit or a log.
4. Code reads it from the environment and sends it as an `Authorization: Bearer` header.
5. The lead checks the hourly quota through FinMind's user-info endpoint at start-up and sets the rate limiter from the returned limit, not from a hard-coded number.
6. On a token or permission error, stop and report. FinMind temporarily blocks IPs that send many failing requests.

## 10. Phase 2 preview: market research loop (Co-Scientist pattern)

**Not to be started until phase 1 data has passed QA and Ken has approved it.** This section records the design so the data layer is built to support it.

Google's Co-Scientist runs a supervisor over specialised agents that generate, critique, rank and refine hypotheses. The product itself is aimed at scientific research inside Gemini Enterprise, so the plan is to reproduce the pattern in Claude Code, wired to our own data and backtester. It can still be used separately as an idea source if Ken has access.

### 10.1 Roles

| Co-Scientist role | Role in this project | Output |
|---|---|---|
| Supervisor | Lead. Manages the queue, the test budget and the experiment log | `RESEARCH_ROADMAP.md` |
| Generation | Proposes signal hypotheses from academic literature and Taiwan market structure | One hypothesis card each |
| Reflection | Fresh-context reviewer (Goldfish). Checks for lookahead, unrealistic costs, crowding, weak economic logic | Review attached to the card |
| Proximity | Clusters and deduplicates. Highly correlated signals count as one idea | Cluster map |
| Ranking | Pairwise debates between hypotheses, Elo-scored, to choose which few get tested | Ranked shortlist |
| Evaluator (added) | Fixed backtest harness with costs. Not an agent's judgement | Result record |
| Evolution | Refines or combines survivors, within a capped number of attempts | Revised cards |
| Meta-review | Summarises what failed and why, and updates the generation guidance | Cycle report |

### 10.2 The key adaptation

In Co-Scientist the tournament ranks ideas by argument. Here that is deliberate: **ranking happens before testing and decides which hypotheses spend the limited test budget.** Backtest results must never feed the tournament directly, or the loop turns into a search for whatever fits the past.

### 10.3 Hypothesis card (written before any test)

- Claim, in one sentence.
- Mechanism: who is on the other side of the trade and why they keep losing.
- Data required and its `available_at` logic.
- Holding period and expected turnover.
- Predicted effect size and what result would falsify it.
- Known prior evidence (papers, or none).

Cards are committed to git before testing, so the prediction cannot be rewritten afterwards.

### 10.4 Research guardrails

- **Test budget:** a fixed number of backtests per cycle (start with ten). Every run is logged, including failures.
- **Three data splits:** train, validation, and a final holdout the agents cannot read. Only Ken unlocks the holdout, once, for a shortlisted strategy.
- **Evaluator is frozen code** written before the first cycle, with full costs (0.3% sell tax, commission, slippage, limit-lock fills). No research agent may edit it.
- **Results are discounted for the number of attempts** (deflated Sharpe ratio or equivalent).
- **Evolution is capped** at two refinements per hypothesis.
- **Ken approves** which hypotheses move to paper trading.

### 10.5 Seed hypotheses for the first cycle

- Drift after monthly revenue surprises.
- Supply-chain lead-lag from US customers to Taiwan suppliers.
- Overnight US semiconductor moves versus the Taiwan open-to-close return.
- Persistence in foreign and investment-trust net buying.
- Reversal after extremes in margin balances or day-trading share.

### 10.6 Tooling note

The ranking debates are the one place agent teams fit better than subagents, because the agents need to challenge each other directly. Everything else runs as subagents.

## 11. Audit trail and continuous improvement

The aim is to improve the agent process itself, not only the data. That needs a record that agents cannot forget to write or quietly edit, plus a regular review that turns the record into changes.

### 11.1 Five records

| Record | Location | Written by | Answers |
|---|---|---|---|
| Event log | `audit/events.jsonl` | Hooks, automatically | Which agent ran which tool, when, and what failed |
| Run reports | `audit/runs/<date>_<agent>.md` | Each agent at the end of its task | What was done, what went wrong, what was unclear |
| Decision log | `docs/DECISIONS.md` | Lead, when Ken decides something | What was decided, why, and what was rejected |
| Iteration log | `docs/ITERATION_LOG.md` | Lead, each QA round | What failed, what changed, did it pass |
| Retrospectives | `audit/retros/<milestone>.md` | Fresh-context process reviewer | What to change in the process next |

Git is the sixth record: one commit per agent task, with the agent's name and task ID in the message.

### 11.2 Automatic event log (hooks)

Add to `.claude/settings.json`. Verify event names and input fields against the current hooks documentation before relying on them.

```json
{
  "hooks": {
    "SubagentStart":      [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "SubagentStop":       [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "PostToolUse":        [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "PostToolUseFailure": [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "PermissionRequest":  [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "TaskCompleted":      [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }],
    "SessionEnd":         [{ "hooks": [{ "type": "command", "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/audit.sh" }] }]
  }
}
```

`.claude/hooks/audit.sh` (needs `jq`):

```bash
#!/usr/bin/env bash
mkdir -p "$CLAUDE_PROJECT_DIR/audit"
jq -c '{ts: (now | todate), event: .hook_event_name, session_id, agent_id, agent_type,
        tool_name, tool_use_id, transcript_path}' \
  >> "$CLAUDE_PROJECT_DIR/audit/events.jsonl"
```

It records metadata only, not tool inputs, so tokens and file contents never land in the log. Full detail remains in the session transcript at `transcript_path`.

**Protection:** add a `PreToolUse` hook (or a permission deny rule) that blocks agents from editing `audit/`, `.claude/hooks/` and the validation suite.

### 11.3 Run report template

Every agent ends its task by writing:

- Task and agent name.
- Files created or changed.
- Result: rows, date range, gaps.
- Problems hit and how each was resolved.
- **What in my instructions was missing, ambiguous or wrong.**
- What I would do differently next time.

The fifth item is the main input to process improvement.

### 11.4 Process metrics

Computed from the records at each milestone and tracked over time in `audit/METRICS.md`:

- QA first-pass rate per agent, and rounds needed to pass.
- Tool failures and retries per agent.
- Rework: files rewritten after first completion.
- Human interventions: how often Ken had to correct or unblock.
- Defects by how they were found (design review, numeric check, cross-source check, Ken).
- Wall-clock time and token cost per agent.

### 11.5 Retrospective loop

Run at each milestone: design approved, collection done, QA passed, and after each research cycle.

1. A process reviewer starts in a fresh context with only the `audit/` folder, the logs in `docs/` and the current process files (`CLAUDE.md`, `.claude/agents/`, this brief). It has no stake in the work.
2. It writes `audit/retros/<milestone>.md`: metrics, the three biggest sources of waste or error with evidence from the logs, and at most three proposed changes, each as a specific edit to a named file.
3. Ken accepts or rejects each proposal. Decisions go in `docs/DECISIONS.md`.
4. Accepted changes are committed as their own commit referencing the retro.
5. The next retro checks whether each earlier change improved its target metric, and proposes reverting any that did not.

Limit changes to three per retro so their effects can be told apart.

## 12. Starter prompt for Claude Code

> Read DATA_COLLECTION_PLAN.md and follow the workflow in section 6.2. You are the Lead (Elephant). Before anything else, set up the audit trail in section 11 (hooks, folders, templates) and confirm events are being written. Then verify every FinMind dataset name and tier against the current docs, then draft the design with /egm:egm-draft and review it with /egm:egm-review. Stop and wait for my approval of the design. After approval, scaffold the repo and shared clients, spawn agent A, then agents B to E in parallel as subagents, then agent F in a fresh context for QA. Run the improve loop for at most three rounds. Do not write any modelling or trading code. Every agent writes a run report (section 11.3). At each milestone, run the retrospective in section 11.5 and wait for my decision on its proposals. Finish with COVERAGE_REPORT.md, ITERATION_LOG.md and a list of anything that blocked you.
