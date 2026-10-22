# Validation ledger

All results are local development evidence, not live deployment claims.

## T01
- RED: storage test collection failed because mysoul.domain was absent.
- GREEN: 8 tests passed with SQLite restart and conflict assertions.
- Environment: uv-managed CPython 3.12.12; exact dependencies in uv.lock.
- Baseline: planning-only repository, no pre-existing application tests.
- Workflow adaptation: PowerShell maintains the same task ledger as the Bash skill helpers; task headings in the existing plan remain authoritative.

## T02
- RED: life module absent. GREEN: 7 tests passed, including 1,000 quiet rest ticks and a bounded 1,000-event burst.
- Fatigue calibration is configurable; paired deterministic traces will be recorded in T10.

## T03
- RED: effects/executor modules absent. GREEN: 7 executor/checkpoint tests passed.
- Tested actual AsyncSqliteSaver persistence (langgraph 1.2.16, checkpoint-sqlite 3.1.2).
- Unknown effects are retained; cancellation and owner interruption do not erase remote receipts.

## T04
- RED: context and MemPalace adapter modules absent. GREEN: 10 tests passed; 1 real-engine test skipped for missing explicit process/index configuration.
- Inspected upstream commit f41e8e75ddaadf5588d5127715fa531d79eadb45, MCP schemas and get-drawer response in source. This is an inspected revision, not a live-tested engine.
- No summary cache is used, so every model admission reads the current Recap revision.

## T05
- RED: phone/service modules absent. GREEN: 6 end-to-end replay tests passed.
- Two independent runs of the same trace produced silent/draft choices; owner interruption retained the goal; restart deduplicated events.
- Replay has no network client and never instantiates NapCat.

## T06
- RED: provider and NapCat modules absent. GREEN: 8 fixture-backed contract tests passed.
- Covered malformed output, refusal, timeout, bounded retry, raw model ID, forged owner names, duplicate events, allowlist/send denial and lost acknowledgment.
- Real provider and QQ deployment/smoke remain deferred. OneBot mapping checked against https://napneko.github.io/onebot/api and the OneBot 11 public API.
