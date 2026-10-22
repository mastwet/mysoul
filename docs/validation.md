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

## Reasoning model connection and optional token limits

- User authorized a local gateway test. The plain Hello request succeeded, but
  the old 128-output-token probe returned HTTP 200 with `finish_reason=length`
  and an incomplete JSON/code fence after 123 reasoning tokens. A larger-cap
  request returned valid JSON in roughly 11 seconds, exceeding the old 10-second
  probe deadline. The user's saved base URL also omitted `/v1`; its chat endpoint
  returned HTTP 404. The configured base URL was corrected to include `/v1`.
- The probe now uses a 30-second deadline with no retries. Optional output caps
  omit `max_tokens` when null; the system's cumulative token budget independently
  accepts null for unlimited. Both are persisted and displayed accurately. Null
  budget checks cover life, reflection, Recap, execution and candidate accounting.
  Existing finite goals/trials retain their limits; smaller explicit output caps
  propagate into candidate trials. Omitted fields and old saved configurations
  preserve existing finite budgets rather than silently disabling them.
- RED→GREEN regressions cover output-field omission in actual HTTP payloads,
  reasoning-response truncation, unlimited chat/work/Recap, restart persistence,
  zero-budget blocking, compatibility migration, and finite goal/candidate caps.
  Two independent review findings on candidate inheritance and finite-goal output
  reservations were reproduced and fixed; follow-up found no important issue.
- Real gateway evidence: `gemini-3.8-flash-tiered` passed the actual local
  `/api/model/test` without saving or switching the model (~6 seconds), and the
  explicitly opted-in real provider contract test passed (1 passed). The user's
  existing `gemini-3.8-flash-high` then passed the same real connection probe
  (~5 seconds). The selected model was retained, the base URL corrected, and both
  requested token limits saved as unlimited. No secret was added to source/docs.
- Full verification: **150 Python tests passed, 8 explicit gates skipped**;
  **12 Node UI tests passed**; Ruff, JS syntax and wheel build passed. The real
  provider test above was run separately with explicit opt-in. Screenshot:
  `assets/model-token-limits.png`. Full MemPalace, QQ and isolation remain pending;
  this provider result does not establish complete v0.1 acceptance.

## Actual chat follow-through

- The user's original open tab still had the older JavaScript and raised
  `Cannot read properties of null (reading 'toLocaleString')` after budgets became
  unlimited. Reloading that exact tab loaded the nullable-budget renderer and
  refreshed its CSRF session. The temporary second verification tab was closed.
- The actual chat API still returned `Model unavailable` after approximately
  12 seconds. Replaying the assembled owner context against the gateway returned
  HTTP 200 with a complete, schema-valid ActivityDecision inside a Markdown JSON
  fence. Raw Pydantic JSON parsing rejected the outer wrapper; validating the
  unwrapped document succeeded. The adapter now accepts only one complete outer
  JSON/plain fence and applies unchanged schema/tool validation afterward.
- Three accepted fence variants and five strict rejection cases were tested;
  an authenticated actual chat-API fixture verifies the provider reply reaches
  the persisted interaction. Those acceptance tests failed before the fix.
- After restarting the corrected backend and reloading the original user tab,
  the browser sent `聊天验收：你好，请用一句中文回复。` using the saved real
  `gemini-3.8-flash-high` configuration. The page displayed the actual response
  `你好，很高兴为您服务！`, removed its pending row, re-enabled/focused the composer,
  and had no browser console error. Screenshot: `assets/live-chat-success.png`.
- Final verification: **159 Python tests passed, 8 explicit gates skipped**;
  **12 Node UI tests passed**; Ruff, JS syntax and wheel build passed. A fresh
  review found no important issue in the normalization. The separate real provider
  contract result above remains valid; other real integration gates remain pending.


## Three-minute main-chat heartbeat (2026-10-22)

- Reduced the permitted interval minimum from 240 to 3 minutes in both API and
  durable state validation; added a three-minute UI option and accurate minute
  formatting. Fresh-install default remains six hours. The active local service
  was explicitly saved with autonomy enabled and interval 3.
- Fixed starvation when already-considered, unchanged maintenance remained ready:
  a due main-chat check can now proceed after that maintenance's initial admission.
  New readiness still gets priority; mode, fatigue, budget, owner input, executor,
  dispatch epoch, locking and persisted deadline guards remain in force.
- RED tests reproduced rejected three-minute configuration, missing UI option and
  maintenance starvation. GREEN: **185 Python passed, 8 gated tests skipped**;
  **23 UI tests passed**; Ruff, diff whitespace and source/wheel builds passed.
  Regressions exercise tick-driven cadence, no early duplicate, restart persistence
  and maintenance starvation. Independent review found no important issue.
- Live verification used the running loopback service and its existing real
  `gemini-3.8-flash-high` configuration. After saving the interval at 22:43:31
  Asia/Shanghai, natural checks started at **22:46:36**, **22:49:38** and
  **22:52:41**. The first timed out at 120 seconds. The next two completed at
  **22:50:11** and **22:52:59**, choosing silence. No new proactive message was
  generated in this observation. A separate structured connection probe passed.
  The schedule advanced automatically without toggling autonomy or manual ticks.
- Browser reloaded the updated bundle and displayed `每 3 分钟` plus the actual
  last-check outcome. Existing cumulative call limit remains 100 (54 used at the
  end of observation); heartbeat checks consume that budget. This verifies live
  scheduling/recovery and provider decisions, not guaranteed speech every cycle
  or full QQ/MemPalace/isolation acceptance. Skipped gates are not passes.


## Explicit local testing without operator token or call ceiling (2026-10-22)

- User explicitly requested both changes. Added `serve --local-test`, disabling
  operator-token authentication and the cumulative model-call ceiling for that
  launch. Normal launch defaults remain authenticated and limited to 100 calls.
  Separate environment controls are documented. No credential, history, counter,
  task bound, QQ permission or provider token setting is erased by this mode.
- All cumulative call-budget admission sites now accept null, including life,
  heartbeat, executor, Recap, reflection, candidate owner accounting and probes.
  Candidate sandbox-local limits remain bounded. The UI attempts a local session
  on load, enters directly when tokenless, and renders unlimited calls accurately.
  Loopback bind, allowed Host, mutation Origin and CSRF validation remain active.
- RED: 7 Python regressions failed for unsupported settings/CLI and 1 UI test
  failed to enter without a token. GREEN: **193 Python passed, 8 gated skips**;
  **24 UI tests passed**; Ruff, JavaScript syntax, diff whitespace and offline
  source/wheel build passed. Independent review found no important issue.
- Restarted the existing service on port 8767 with its existing data directory
  and `--local-test`. Unauthenticated session/status requests returned 200,
  auth_required=false, model_calls=null and the already-unlimited tokens=null.
  A new browser tab with no token fragment entered directly and displayed
  `59 / 不限`; autonomy remained enabled every 3 minutes and its next natural
  check completed quietly. No additional owner-chat test message was added.
- A local restart helper was saved outside Git at
  `C:/Users/Administrator/Desktop/mysoul/.local/start-local-test.ps1` so the
  current worktree, data directory, port and testing flags can be reused.
  Screenshot is in that local folder as `local-test-unlimited.png`. This change
  does not count skipped QQ, MemPalace or isolation gates as passes.
