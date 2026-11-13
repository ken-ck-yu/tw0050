# Run report: spike-tpex / TPEx spikes S2, S3, S4, S8, S9

- **Task and agent name:** TPEx research spikes S2, S3, S4, S8, S9 (research agent, no ingestion code).
- **Files created or changed:** `/tmp/claude-1000/-home-ken-tw0050/3508f076-53cf-4bb0-948d-cedb62426aaa/scratchpad/research/spikes_tpex_findings.md`, this run report. Also scratch helper scripts (`s2.py`, `s4.py`, `sp_fetch.sh`, `bis.sh`), a request log and raw responses under `research/spikes_tpex/` in the scratchpad (outside the repo). No repo file other than this report; no git run.
- **Result:** 18 live requests to www.tpex.org.tw (limit 45), no failures. Answers: next-day limits shift to the next trading day (D+1 close inside D limits in 100% of rows in 3 pairs); revivt 2016 to 2021 has 27, 25, 29, 26, 25, 21 rows; exDailyQ 2025 has 1250 rows and no capital-reduction text; common-stock rule has no leaks on 11 dates; otc 2015 files have the 15-field layout; first 17-field date is 20200430; `(張數)` starts 20250110.
- **Problems hit and how each was resolved:** The suggested pair 20250529/20250530 failed because 20250530 was a holiday (0 rows); used 20250529 to 20250602 and 20250108 to 20250110. My first S4 keyword scan gave false positives (大甲, 特 in names); re-ran with narrower patterns. 9999.95/0.01 limits (no-limit ETFs) broke the first ratio test and were excluded.
- **What in my instructions was missing, ambiguous or wrong:**
  - The example pair 20250529/20250530 was wrong (holiday).
  - "First and last dates" for revivt did not say the field is a 7-digit ROC string.
  - No instruction on the no-limit sentinel 9999.95/0.01 for ETFs.
  - The instruction listed `bulletin/revivt` params with empty `startDate=` and did not say how a one-year range is returned; it worked as stated.
  - The 17-field era is really two eras (千股 then 張數); the prompt implied only one boundary per field count.
  - S4 asked for the "-DR" test but no 4-digit -DR codes exist on these dates, so that part of the rule was untested.
- **What I would do differently next time:** Check the holiday calendar from the saved files before choosing pairs, and bisect with the weekday-only dates listed in advance.
