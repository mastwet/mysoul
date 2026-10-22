# Validation ledger

Current result after UI redesign and fixes (2026-10-22): **130 passed, 8 skipped**, plus **7 Node UI tests**.
Ruff and JavaScript syntax checks pass. This is a Windows offline milestone;
real integrations remain pending. See [review disposition](review.md) and [runbook](runbook.md).

All results are local development evidence, not live deployment claims.

## Conversation UI redesign

The chat-first layout, top-right fatigue card, grouped settings, light/dark themes,
responsive navigation and retained application actions were exercised in the actual
loopback browser at desktop and 390×844. The independent reviewer found a composer
focus issue; two failing DOM regressions reproduced it before the fix. Success/error
focus recovery and navigation-without-focus-theft now pass. See `ui-redesign.md`
for commands, screenshot references, third-party notice and review boundaries.

## Autonomous closure follow-up

- Three missing links are now connected: life decisions dispatch bounded activities;
  source-backed feedback/Recap consolidation runs as explicit reflection; candidate
  regressions accept selected models and objective artifact cases with base/candidate
  comparisons. See `closure-plan.md` and the follow-up in `review.md`.
- RED: six activity-routing tests, four auto-Recap tests and four candidate-model tests
  failed before implementation. GREEN: those workflows pass.
- A fresh reviewer reproduced six Important gaps; seven regression tests initially
  failed in the fix pass, including the regraded missing-case-record finding. Further
  decision-admission and quiet deadline tests also failed before their fixes. Other
  concurrency, fatigue-recovery and unknown-outcome probes pass.
- Full suite: **129 passed, 8 skipped**. Ruff, JavaScript syntax and wheel build pass.
- Actual browser walkthrough: owner input automatically published sourced Recap v1;
  a reflection proposal was tested through the new candidate endpoint and displayed a
  passing objective with its fixture model label. Screenshot: `assets/closure-ui.png`.
- Provider selection/serialization was verified with real `OpenAICompatibleModel`
  clients against fixture HTTP, including base/candidate isolation and parent budgets.
  This is an offline contract result. Live configuration keys were absent in this
  session; no real model, MemPalace or QQ operation was performed.
- Remaining release gates: real provider (1 skip), full MemPalace (1), authorized QQ
  observation/send (2), and deliberately unavailable isolation backend (4). Isolation
  stays disabled and is not required for the local file-work/chat loop.

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

## T07
- RED: work-tool modules absent; end-to-end artifact task suspended before registration. GREEN: 13 tests passed after implementation.
- Actual Windows symlink escape, alternate paths, hardlinks, oversized I/O and a real write/read/feedback task verified.
- Windows parent directory handles deny replacement during I/O; file contents are accessed only after handle-path verification.
- Arbitrary execution is unconditionally disabled; actual-isolation tests report skipped, never approved.

## T08
- RED: evolution modules absent; reflection service absent. GREEN: 9 tests passed for evidence, isolated candidates, objective failure, hash-bound approval, pinned versions, activation, rollback and budgeted reflection.
- Regression found and fixed: historical recall was being counted as current-task tool progress. A distinct step_results field now carries only this task's results.
- Candidate evaluation uses a deterministic draft/verify fixture; no claim of real-model skill improvement.

## T09
- RED: API absent; runtime environment/tick/lease tests failed before implementation. GREEN: 5 API and 3 runtime tests passed.
- Browser walkthrough on the actual local server: authenticated chat; whole Recap edit/save (v1); evidence-driven reflection; candidate objective test; operator approval/activation; rollback; finite task completion.
- UI uses the existing application services. Edit conflicts preserve the form and its original base revision.

## T10 acceptance before independent review
- Four-chain test passed: owner event, bounded artifact, failure evidence, reflection, isolated candidate, approval, next-task verification, rollback and restart/source retrieval.
- Added regressions for durable inbox restart, burst coalescing, actual opt-in group dispatch through fixture HTTP, prompt/schema budget reservation and elapsed time on interrupted inference.
- Full suite: 83 passed, 6 skipped. Skips: real provider (1), real MemPalace (1), unavailable isolation backend (4). No live QQ call was made.
- Ruff passed. Wheel built and all five required SQL/Markdown/Web resources verified. CLI replay produced silent/draft outcomes.
- Paired fatigue experiment is in fatigue-comparison.json; it uses identical simulated events and deterministic fixture tasks, not human-fatigue or intelligence measurements.
- Initial skill Markdown is packaged under src/mysoul/builtin/work.md so installed wheels retain the authoritative baseline. Runtime revisions stay in .local/skill-revisions.
- Milestone: offline implementation available; real integration pending. Independent code review follows.

## Final independent review and regression pass

- Fresh reviewer found seven Important application-flow issues; all were reproduced with fixture transports and fixed in one pass.
- Eleven initial regressions failed before fixes; all passed afterward. Further priority, repeated-send and rest-deadline regressions also went red to green.
- Reported work-state and send-label issues were treated as Important because they affect fatigue and truthful effect reporting. Mode preferences and a one-time rest deadline are now wired; no reported minor was left deferred.
- Final full suite: 98 passed, 8 skipped. The additional QQ observation/send tests are explicitly opt-in and were skipped; no live message was sent.
- Allowlisted news registration passed a fixture-backed execution test, preserving public source provenance. No real source was enabled.
- Installed wheel smoke verified SQL, built-in Markdown and web resources. CLI replay preserves Chinese UTF-8 output.
- Browser walkthrough was repeated after restart on the final implementation; a responsive UI screenshot is saved in `assets/operator-ui.png`.
- Details and verification boundaries: `review.md`. Source remains on the named feature branch; no merge, push, deployment or live account setup was performed.

## Model configuration UI follow-up

- Reproduced the missing model configuration endpoint/form with failing Python and
  actual HTML/app.js DOM tests before implementation.
- Added authenticated endpoint/model/API-key settings, redacted reads, atomic local
  save/activation, Windows DPAPI storage, restart restoration and an explicit
  private-free, budgeted, bounded connection test. CLI replay ignores saved providers.
- Verified retained keys cannot silently move to another endpoint; stale revisions,
  active work and owner inference reject a switch. Disk failure preserves the active
  model. Failed probes close clients and do not retry, save or activate configuration.
  Candidate tests use the same configured provider even if environment variables change.
- Independent review found an incorrect probe-schema reservation and hidden URL
  validation blocking an offline switch. Both were reproduced with failing regressions
  and fixed; follow-up review identified no remaining important finding.
- Full verification: **142 Python tests passed, 8 existing live/isolation skips**;
  **11 Node UI tests passed**; Ruff, JS syntax and wheel build passed.
- Browser walkthrough on the actual loopback service: model service navigation,
  provider fields, invalid address followed by offline selection, discard/restore,
  and a 390×844 responsive form with all actions visible. Screenshot:
  `assets/model-settings-mobile.png`. No real API key was entered or provider called.
- Preview remains an offline procedure demonstration. The real provider, full
  MemPalace, authorized QQ and isolation acceptance boundaries remain unchanged.
