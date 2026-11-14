# Standing rules

Phase 1 is data collection only. Read `DATA_COLLECTION_PLAN.md` first.

1. **Point-in-time:** every table carries `event_date` and `available_at` (Asia/Taipei). Join features only on `available_at`. Rules per dataset are in plan section 4.
2. **No secrets or data in git.** The token is `FINMIND_TOKEN`, loaded from the environment or a gitignored `.env`. Never read, print, log or commit it. `data/` is gitignored.
3. **No modelling, backtesting, broker or trading code** in this phase, except the early research lane in `docs/amendments/early_lane.md` (approved by the author on 2026-11-14). Broker, order and live-trading code stay forbidden.
4. **Each agent edits only the files it owns.** The lead assigns ownership in every spawn prompt. Nobody edits `audit/events.jsonl`, `.claude/hooks/` or the validation suite except its owner.
5. **The builder never grades its own work.** QA writes no ingestion code. Workers never edit the validation suite.
6. **Human gates:** design approval, any paid FinMind tier, anything that deletes or overwrites collected data.
7. **Rate limits:** read the hourly quota from FinMind's user-info endpoint and set the limiter from it. On a token or permission error, stop and report. Repeated failing requests get the IP blocked.
8. **Every agent ends with a run report** in `audit/runs/` (template: `audit/RUN_REPORT_TEMPLATE.md`). Include what in the instructions was missing, ambiguous or wrong.
9. **One commit per agent task**, message naming the agent and task.
10. **Every change reaches `main` through a pull request that the author reviews and merges.** (Author decision, 2026-11-14.) Agents work on a branch or worktree, push it and open a PR with `gh pr create`. Nobody pushes to `main`, merges a PR, or force-pushes. The author is the only merger. The PR description follows `.github/pull_request_template.md` and must give both levels:
    - **Business and functional level:** the problem, why it is worth solving now, the goal in plain words, and acceptance criteria the author can check without reading code.
    - **Technical level:** what changed and where, the alternatives considered, why this is the best option, the trade-offs and risks accepted, how it was verified (tests, QA report), and what is not done.
    A PR missing any of these sections is not ready for review. Data changes under `data/` never appear in a PR (rule 2); describe them in the PR instead.
