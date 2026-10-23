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

## Vivy-aligned memory and automatic persona chain (2026-10-23)

- Complete owner/assistant/failure sources now feed bounded, offset-aware windows.
  Six durable stages cover collect, prepare, reconcile, reflect, effects and finish.
  Recap and source coverage publish atomically. Later-stage retry does not refold a
  committed Recap; no new evidence makes no model call. A separate three-minute
  maintenance policy runs through the existing single-subject admission gate.
- Persona changes automatically activate with base/epoch/evidence checks, history,
  old/new text and rollback. Identity, relationship, dark, WORLD additions and separate
  inferred observations are eligible. Redline/Mission/Dream/public/owner USER remain
  manual. WORLD is never injected automatically, and additions preserve its unseen
  base. Inference labels do not guarantee semantic truth or perfect fiction detection.
- Independent review found three Important issues: incomplete turns after migration,
  missing task tool/final result content, and destructive replacement of unseen WORLD.
  Each regression failed before its fix and passed afterward. Final full suite:
  **231 Python passed, 8 explicit skips; 26 UI passed**. Ruff, JavaScript syntax,
  whitespace checks and offline source/wheel build passed. No deferred minor findings.
- Disposable real-provider check used the saved gemini-3.8-flash-high gateway with
  separate data at `.local/cognition-real-check-20261023`. Recap publication passed
  (version 1, 349 characters), but reflection timed out at 120 seconds twice and at
  240 seconds on one isolated retry. All retries retained Recap version 1 and the same
  failed stage. No persona change activated in this scenario. The actual saved timeout
  was not modified. Real positive-change activation is **not certified** by this run;
  deterministic automatic activation, version pinning and rollback are verified.
- Stopped the existing 8767 service and backed up all 17 runtime files to
  `.local/backups/ui-redesign-before-cognition-20261023-001950` before activation.
  Restarted the same `.local/ui-redesign` directory with `--local-test`. Session is
  tokenless; cumulative call/token limits are null; initiative remains enabled at
  three minutes. Existing provider credentials and data were retained.
- The actual service automatically started a run at **00:19:52 Asia/Shanghai** and
  completed by **00:20:17** using the real provider. Run
  `7ad051175023445a9a2d006d4b6a7788` has all six receipts, no error, outcome `no_change`,
  three covered sources, zero pending sources, Recap **v9 -> v10**, persona still **v1**.
  The model explicitly found only task state changes and no supported persona change.
  This verifies the real complete no-change path; it does not substitute for the
  failed positive-change scenario. The next natural chat check started at 00:20:42.
- Browser fixture 8768 verified complete source details, empty manual run, pause/resume,
  old/new change text and rollback v1 -> v2, including a 390x844 layout. Actual 8767
  browser verified the completed source coverage/receipts, automatic persona enabled,
  and no console errors. Actual owner persona was not rolled back as a test. Fixture
  server/tab were closed; actual service/tab remain available. Screenshot:
  `C:/Users/Administrator/Desktop/mysoul/.local/cognition-live-completed.png`.
- Migration deliberately retains 18 already-published legacy excerpts as legacy,
  without claiming complete historical coverage or replaying the entire archive.
  Old task final notes were not historically stored and cannot be reconstructed.
  New startup recovery runs on each boot; new task notes are durable.

### Review rulings and remaining acceptance boundaries

1. Maintenance failures are durable retry receipts rather than scheduler exceptions;
   fresh goals/skill feedback receive first admission. Continuous new work may delay
   maintenance. This preserves the agreed owner/work priority.
2. Runtime activation/recovery and rendered browser acceptance were checked by the
   executor, separately from code review. A preserved backup remains the recovery
   route for an undiscovered migration problem; untested layouts may need refinement.
3. Citation validation proves allowed provenance, not truth of inferred observations;
   owner correction and version rollback remain necessary for bad inferences.
4. MemPalace/QQ/isolation gates remain separate. Local completion means local authority
   publication and note enqueue; it does not certify external delivery. MemPalace is
   not connected here and its pending queue remains visible. No real QQ send occurred.
5. Large archive performance/retention have no certified scale target. Source/history
   enumeration can become slow as data grows; no scale benchmark is claimed.
6. The isolation contract is one main owner scope. Generalized independent owner
   sessions would require additional isolation work before that use is supported.

Delivery remains **offline loop complete / real integrations pending acceptance**.
A real provider no-change cycle passed, while the disposable positive-change reflection
failed. Skipped or failed external checks are not counted as passing full v0.1.

## Main-chat initiative diagnosis and visibility (2026-10-23)

- The user's report was valid: an enabled three-minute check was not proof of a new
  assistant message. Actual checks at 01:15 and 01:18 timed out after 120 seconds;
  the 01:24 request returned a provider error after about 145 seconds. After the
  interrupted session, the configured localhost:8045 gateway was not running.
- Persist each check's start, finish, outcome, decision reason and structured model
  failure. Expose the current receipt through the shared status API and show the
  reason in settings and failure category in the main-chat status. Cancellation
  propagates after recording an interrupted result; startup closes orphaned waiting
  records. Settings pause is distinguished from owner-input interruption.
- Clarify that enabled autonomy may begin a concrete new topic using shared interests
  and existing knowledge, without requiring a new owner turn. Preserve quiet, epoch,
  fatigue, budget and duplicate-topic constraints. The heartbeat still cannot browse
  or send externally; it must not claim live exploration without tool evidence.
- Include assistant-initiated messages in the recent-message sidebar, which previously
  filtered them out. A regression demonstrated that omission before the correction.
- Real-provider synthetic plant-knowledge fixtures generated assistant initiatives;
  they contained no actual user conversations. A proposed private-context diagnostic
  replay was rejected by automatic approval and was not executed.
- Independent review identified cancellation/restart receipts left waiting and pause
  mislabeled as input interruption. Both were reproduced RED and fixed GREEN.
  Final **236 Python passed, 8 external skips; 27 UI passed**; Ruff, JS syntax,
  whitespace checks and offline package build passed. Existing branch retained.
- Runtime retains tokenless local testing, unlimited cumulative budgets, selected
  model and three-minute cadence. Saved request timeout changed from 120 to 240 seconds.
  Existing data was backed up before activation. Antigravity Tools was restarted from
  the installed desktop shortcut target when port 8045 was confirmed unavailable.
  Gateway port connectivity alone is not counted as successful proactive speech.
- After restoring the gateway, `/models` returned 200 and included the configured
  gemini-3.8-flash-high; a non-private minimal generation returned HTTP 200 with a reply.
  The actual natural initiative starting **09:12:22** still timed out at **09:16:22**
  (240 seconds), with no assistant interaction published. Thus actual proactive
  speech is **not accepted as fixed**. The next scheduled check remains enabled.
  Exact private-context diagnostic replay awaits explicit authorization after the
  automatic approval rejection; no such replay has been executed.

### Main-chat initiative live acceptance after recovery (2026-10-23, Asia/Shanghai)

- Two successive natural checks published actual assistant messages without any new
  owner event: 09:16:27 -> **09:18:16**, 1721 characters, and 09:19:28 -> **09:20:28**.
  Both receipts are `outcome=message`, both interactions have `choice=initiative`
  and empty owner input. The provider continued the still-authorized fiction request;
  no synthetic fixture reply was inserted into the real conversation. Browser verified
  the proactive label and sidebar entry, with no console errors. Screenshot:
  `C:/Users/Administrator/Desktop/mysoul/.local/initiative-real-success.png`.
- Owner subsequently explicitly authorized private-context diagnostic replay to the
  configured localhost:8045 gateway and its upstream. One isolated snapshot replay
  used **16644 context characters** and the unchanged gemini-3.8-flash-high provider.
  It returned **HTTP 200 after 54.83 seconds**, schema-valid `read_chat/reply`, 164
  reply characters, no error. It published only into the isolated fixture database.
  Sanitized report: `.local/initiative-authorized-replay-20261023/diagnostic-result.json`.
- The exact-context replay supplies evidence that the current structured-output
  contract and payload are accepted. Prior 120/240-second timeouts and the stopped
  gateway remain recorded failures; provider latency is variable. No deterministic
  schema rejection was reproduced. The live automatic-message path is now accepted
  for these two observed rounds, without promising a message on every future check.


### Unified conversation and hierarchical compression (2026-10-23)

- Deterministic timeline/archive/compression tests cover100->70,4->3, maximum-level
  root folding, exact oversized fragments, atomic rollback, mutable task sources,
  epoch/Recap races, persisted-result restart, high/low capacity hysteresis and group
  exclusion. The end-to-end flow joins owner chat, natural initiative, real workspace
  write/read verification, cancellation, L1/L2, restart, non-overlap and raw expansion;
  compression creates no new cognitive source or persona version.
- UI/API tests cover stable pagination during live append, stale revision responses,
  task card edits, failed older fetch preserving messages/draft, no session list,
  owner-only archive inspection and existing Host/Origin/CSRF/operator protections.
- Browser fixture8768 with150 original turns: newest50 ->100 on older load; draft
  retained. L1 inspection returned50 original records; task result and proactive reply
  rendered in one chat. Desktop1280x720 and same-origin fixture390x680 checked;
  narrow chat retains fatigue card, menu and composer with task text wrapping. Only
  the disposable wrapper allows same-origin framing; production still denies frames.
- Real configured gemini-3.8-flash-high via localhost8045 compressed synthetic public
  plant facts, published one archive receipt: **completed, one call,9.98 seconds,
  203 summary characters**. No actual owner history was used for that provider test.
  Sanitized local report: `.local/unified-provider-fixture/result.json`.
- Actual8767 service was stopped, full-directory backed up (17 files), migrated and
  restarted in existing local-test mode. **62 unique timeline items:60 chats/2 tasks**,
  complete paginated enumeration. Model,131072-character budget,240-second timeout,
  unlimited aggregate budgets and three-minute initiative remain configured. Actual
  history is below current compression triggers; no live archive receipt is claimed.
- MemPalace, authorized QQ send and isolation gates remain independent external
  acceptance items. Their skips do not certify complete v0.1. Local offline closure
  plus this observed provider compression is the scope of this feature acceptance.


Final independent review and fixes:

- One fresh read-only reviewer inspected144ae85..be70d1f. Eight Important findings,
  no Critical/minor findings. Each was reproduced before fixing: blocked eligible
  runs after unfinished items, actual serialized pressure measurement, dialogue/archive
  overlap after many tasks, lossy-summary detail recall, unfinished input restart,
  busy task-card status, concurrent prepend anchors, and explicit-zero change cursors.
- All eight were fixed in one pass and covered by integration/UI regressions.
  An additional combined scope fixture exposed private archive metadata in the frontier;
  strict scope filtering was reproduced RED and fixed GREEN too. Unfinished leaves do
  not count toward the100-complete-unit trigger. Query details carry immutable leaf,
  role and [start,end,total] coordinates, max500 original characters per hit, admitted
  only into remaining context budget. Archive search/get reuse the Memory boundary;
  no summary or query excerpt becomes a new persona source.
- Final **274 Python passed,8 external skips;34 UI passed**. Ruff, JS syntax,
  offline source/wheel build and git whitespace checks all passed on final code.
  No second review substituted for these covering regressions. No deferred minors.
- Actual browser after migration: newest50 ->63 unique cards on older load; no session
  list,45 proactive labels in the initially loaded page, one task card visible, no
  console errors. At11:37:57 local, a natural initiative began and published1257
  characters with empty owner input. No artificial history entered actual chat.
- Final reviewed code restarted after another complete stopped backup:
  `.local/backups/unified-reviewed-20261023-115019/ui-redesign`; application database
  SHA256 matched the source copy. Service healthy with65 active original leaves at
  that check. No actual archive run is claimed below threshold. Final screenshot
  `C:/Users/Administrator/Desktop/mysoul/.local/unified-chat-acceptance.png` shows
  the disposable fixture, including task and proactive reply in one conversation.

Review rulings retained after scratch-ledger cleanup:

- Typed-object enumeration performance is accepted without a production-size benchmark;
  if it becomes slow, dedicated indexed archive tables are future work.
- Live migration/provider/docs were outside the review range; completed backup,
  runtime and browser evidence above is the acceptance authority. If recovery fails,
  restore the stopped full-directory backup and repeat acceptance.
- MemPalace/QQ/isolation remain external gates. Treating local acceptance as fullv0.1
  would leave those integrations unproven; this delivery makes no such certification.
- The known test line-length issue is resolved by a clean Ruff run; it is not an
  outstanding functional defect. New changes must rerun the static gate.


### Concise, citation-free event memories (2026-10-23)

- Owner requested Recap/active-memory prose without experience hashes, one short event
  per line, location/person only when supplied, and a date/time precise to seconds:
  `YYYY-MM-DD HH:mm:ss — 简短记忆描述`. Fractions and timezone suffixes are excluded
  from display; original structured evidence timestamps and internal IDs remain intact.
- Both automatic consolidation and legacy synthesis now use the same prompt and safe
  display projection. Recap source aliases replace opaque IDs in synthesis input;
  persona reflection retains real evidence references. Source-citation brackets are
  removed before publication, while factual fingerprint/code text remains intact.
  Citation-only output fails without erasing Recap or advancing source coverage.
- Real-provider synthetic toucan fixture returned exactly the requested short event
  with its source timestamp in11.34 seconds. Owner subsequently requested second-only
  display; deterministic tests cover removal of fractions/zone suffixes in input/output.
- Automatic approval initially rejected sending the existing private Recap because
  specific data/destination authorization was missing. No rejected command executed.
  Owner then explicitly authorized this Recap to localhost8045/v1 and its possible
  upstream; the one real reformat completed in72.94 seconds. Version102 (9435 chars,
  113 experience/outcome citations) became103 (3405 chars,0 citations,52 timed lines).
  A local-only, zero-inference time-format pass published104 (2729 chars), retaining
  all source refs and previous versions. All52 lines match the second-only format.
- Full stopped-directory backups before both changes:
  - `.local/backups/recap-style-20261023-170140/ui-redesign`
  - `.local/backups/recap-seconds-20261023-170427/ui-redesign`

- Actual8767 service restarted with tokenless local-test settings, unlimited aggregate
  budgets and three-minute initiative intact. Final280 Python passed/8 external skips,
  34 UI passed, clean Ruff, JS syntax, offline build and whitespace checks. No new
  external release-gate certification is implied.


### Full upstream MemPalace activation (2026-10-23)

- Installed clean full upstream commit `f41e8e75ddaadf5588d5127715fa531d79eadb45`
  (3.12.0) in a separate Python3.12.12 environment; Chroma1.5.9,
  ONNX Runtime1.31.0 and `embeddinggemma` q8,384 dimensions. Exact observed
  dependency versions are recorded in `integrations/mempalace/runtime-dependencies.lock`.
  Public model warmup returned384 dimensions in33.06s. Actual private indexing uses
  cached weights with HF offline enabled, CPU/two threads and telemetry disabled.
- Real full-engine tests: **2 passed,4 deselected in14.91s**. Chinese original
  write/search/get survives a fresh stdio process; semantic paraphrase without exact
  bird name finds the toucan fixture; equal text under distinct source IDs keeps
  distinct drawer receipts; chunk hits deduplicate; owner records are unavailable
  to group get/search. These ran against a separate disposable index, not owner chat.
- Regression first reproduced loss of identical-text provenance, upstream chunk
  duplication and missing legacy local-delivery migration. Stable per-source rooms,
  authoritative source_path, returned evidence deduplication and startup backfill
  fix these. Confirmed remote receipts are not requeued on restart. Health records
  actual successful/failed MCP operations; it is no longer inferred from a setting.
- Port8767 was fully backed up while stopped, activated through persistent local
  configuration, and restarted normally. Initial235 pending records completed;
  another123 previously local-delivered originals were identified and automatically
  requeued by the added migration. Final actual status: **358 confirmed mappings,
  0 pending**, connected. No synthetic fixture was inserted into owner chat/index.
- Browser actual Chinese query “巨嘴鸟的嘴为什么很轻又能散热” found the prior
  complete assistant original as the first result. After actual server restart, the
  paraphrase “那种大嘴巴的热带鸟，为什么嘴又轻又能调节体温” also found
  that retained original without naming the bird. Short/long switching works through
  the narrow-screen sidebar and keeps chat drafts. The standalone real restart tests
  and actual server restart both retained the existing source mappings/index.
- Existing independent limitation observed before activation: the owner's last chat
  had `context_budget`; hierarchical compression had failed7 times with an invalid
  provider structure and retained its plan/backoff. A successful MemPalace lookup
  does not prove the chat generation/compression path has recovered. This work does
  not claim that provider-context issue fixed or perform an additional private replay.
- Final isolated feature snapshot: **290 Python passed,9 skipped in47.77s**;
  **36 UI passed**. Ruff and JavaScript syntax passed. Of the9 default external
  skips, the2 MemPalace cases also passed separately against the real engine;
  the remaining7 skips are not passed gates. Provider, QQ and code isolation remain
  independent acceptance items. Offline source/wheel build and whitespace checks
  passed on the scoped feature.

- One independent read-only review found one Important test-isolation issue and two
  minor health/legacy-provenance concerns. Both real tests now force temporary
  engine directories, proven RED/GREEN; invalid receipts and changed remote content
  report unavailable, also RED/GREEN. No pre-activation real mappings existed in the
  actual subject; upgrades from older shared-room real indexes require explicit
  migration/replay (documented limitation, not silently rewritten receipts).
- Concurrent work from another desktop conversation changed the same checkout's
  context/autonomy policy during acceptance. Those changes are outside this feature
  and preserved. The final MemPalace regression runs use an isolated snapshot of
  base `a3fca93` plus only this feature's changes. The commit stages only the three
  MemPalace service hunks; it does not include the concurrent context changes.
