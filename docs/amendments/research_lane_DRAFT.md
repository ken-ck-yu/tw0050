# DRAFT amendment: research lane (agents in `research/`)

**Status: draft, not approved, not active.** Nothing here changes `CLAUDE.md`, `config/ownership.yaml` or any hook until the author approves it. Drafted 2026-11-14 by the lead.

## Why

`docs/amendments/early_lane.md` covers one hypothesis (H1) and one strategy agent. The author wants a separate session with several agents that investigate strategies and test hypotheses, apart from the data and QA work. Plan section 10 describes the Co-Scientist pattern for this. This amendment sets the rules for it. It widens the early lane, so the author must approve it.

## When it opens

1. H1 has run once on train and once on validation, and the result is reviewed by the author. This shows the pipeline and evaluator give sensible numbers. Until then the research session is not started.
2. The research session runs in its own git worktree and its own Claude Code window. The data lead keeps the data window.

## Wording change to rule 3 in `CLAUDE.md` (proposed)

> 3. **No modelling, backtesting, broker or trading code in this phase, except the research lane in `docs/amendments/early_lane.md` and `docs/amendments/research_lane.md`.** Broker, order and live-trading code stay forbidden.

## Roles

| Role | Does | Edits only | Never |
|---|---|---|---|
| Supervisor (research lead) | Keeps the queue, the run budget and the log; writes the cycle report | `research/ROADMAP.md`, `research/cycles/**`, `research/experiment_log.jsonl` (append) | Edit the evaluator or data code |
| Generator | Proposes hypotheses from literature and Taiwan market structure; one card each | `research/cards/**` (its own new cards) | Run a backtest |
| Reviewer (fresh context, one per card) | Checks lookahead, `available_at` logic, cost realism, crowding, economic story | `research/reviews/**` | Review a card it wrote |
| Ranker | Pairwise debate and Elo ranking of reviewed cards, before any test | `research/rankings/**` | Read any backtest result |
| Implementer | Writes the strategy code for a ranked card | `src/twdata/research/strategies/**`, `tests/research/strategies/**` | Grade its own result |
| Evaluator owner | Owns the frozen evaluator (already exists) | evaluator paths as in `ownership.yaml` | Write strategies |
| Result reviewer (fresh context) | Reads each result record, checks the card's falsification rule, flags suspicious results | `research/result_reviews/**` | Write strategy code |
| Meta-reviewer | Summarises failures and updates generation guidance | `research/GUIDANCE.md` | Select a strategy for the holdout |

## Rules

1. **Card first.** A card (plan 10.3 template) is committed before any test of it. Its prediction can't be edited after the commit; a change is a new card.
2. **Ranking before testing, blind to results.** The ranker sees cards and reviews only. Backtest results never feed ranking (plan 10.2).
3. **Run budget.** At most 10 backtests per cycle across all agents. Every run is logged, including failures and crashes. Deflated Sharpe uses the cumulative trial count for the whole research lane, not just the cycle.
4. **Evolution cap.** At most 2 refinements per hypothesis. A refinement is a new card linked to its parent, and its runs count toward the budget.
5. **Frozen evaluator.** No research agent edits it. Any change needs the author's approval and a new `EVALUATOR_SHA256`.
6. **Windows.** Train 2015-06 to 2021-12, validation 2022-01 to 2024-06. A strategy is developed on train and checked once on validation. Repeated validation looks count as trials. The holdout from 2024-07-01 stays sealed: not loaded, no code path to it. Only the author unlocks it, once, for one shortlisted strategy.
7. **Point-in-time only.** Features join on `available_at`. Adjusted prices are used for labels, not features.
8. **Economic story required.** A result with no mechanism on its card is rejected, whatever its Sharpe.
9. **Provisional until QA passes.** Results stay labelled provisional until the full Phase 1 QA has passed. A provisional result may guide the next card but can't select a strategy for the holdout.
10. **Read-only data.** Research agents read `data/research/` only. They never read `data/clean/`, `data/raw/` or `.env`, and make no network requests.
11. **No self-grading.** The implementer, the evaluator owner and the result reviewer are different agents for any one strategy.
12. **Stop conditions.** An agent stops and reports when it finds a data defect (a missing split, a wrong `available_at`, a gap in the universe). It does not patch the data or work around the defect inside a strategy. The data lead decides.
13. **Run report.** Every agent ends with a run report in `audit/runs/` (rule 8 of `CLAUDE.md`), including what in its instructions was missing, ambiguous or wrong. One commit per agent task.
14. **Unchanged:** no broker, order or live-trading code; no secrets or data in git; the data lead keeps the collection and QA.

## Per-run record the author sees

Hypothesis card id, window, Sharpe after costs, 0050 over the same window, turnover and cost drag, maximum drawdown, trials so far (cycle and cumulative), deflated Sharpe, and whether the falsification rule triggered. The result reviewer's note is attached.

## Proposed changes to `config/ownership.yaml` (not applied)

Replace the single `strategy` entry with these. Existing `evaluator` stays as it is.

```yaml
research_lead:
  - research/ROADMAP.md
  - research/cycles/**
  - research/experiment_log.jsonl
  - audit/runs/*_research_lead_*.md
generator:
  - research/cards/**
  - audit/runs/*_generator_*.md
reviewer:
  - research/reviews/**
  - audit/runs/*_reviewer_*.md
ranker:
  - research/rankings/**
  - audit/runs/*_ranker_*.md
implementer:
  - src/twdata/research/strategies/**
  - tests/research/strategies/**
  - research/runs/**
  - audit/runs/*_implementer_*.md
result_reviewer:
  - research/result_reviews/**
  - audit/runs/*_result_reviewer_*.md
meta_reviewer:
  - research/GUIDANCE.md
  - audit/runs/*_meta_reviewer_*.md
```

Open points for the author:
- `research/experiment_log.jsonl` is append-only; the evaluator, not an agent, should write run entries. Needs a check in the evaluator spec that it already does.
- The existing `strategy` owner (H1) maps to `implementer`; the H1 card and runs already committed keep their history.
- The ownership audit script must accept the new owner names before the session starts.

## Decisions for the author

1. Approve the rules and the role split as drafted, or edit them.
2. Approve the `CLAUDE.md` rule 3 wording.
3. Approve the new ownership entries (the lead then edits `config/ownership.yaml` and updates the audit script, as one commit).
4. Confirm the start condition: after the first H1 result, not before.
