# mysoul Implementation Plan

> Implementation guidance: work task-by-task with independent review at phase gates. Do not treat this plan as permission for live deployment or external messaging.

**Goal:** Build a small, independent Python experiment in which one enduring subject chooses how to spend time, remembers sources, finishes bounded work, handles interruption honestly, and improves reviewed skills.

**Architecture:** An asyncio life loop controls one subject and a finite LangGraph executor. LAPUTA Lite assembles scoped context from versioned Recap plus full upstream MemPalace recall; PEN Lite provides the same phone-like interface for replay and NapCatQQ. DIVA classic proposes skill changes behind isolated tests and explicit review.

**Tech stack:** Python 3.12, asyncio, LangGraph OSS, SQLite, Pydantic, upstream MemPalace over stdio MCP, FastAPI and plain HTML/JavaScript.

**Spec:** [DECISIONS.md](DECISIONS.md), decisions D001–D012. All paths, interfaces, commands, and tests below are proposed. This repository begins without implementation; no test or live integration is claimed complete.

## Global constraints

- One subject, not a multi-agent society; no automatic self-code modification.
- Model choices are soft preferences; runtime permissions, budgets, and dispatch epochs are hard controls.
- Owner input preempts new autonomous effects, not remote actions already in flight.
- Rest makes no recurring model calls; reflection is visible and budgeted.
- Group/news text is untrusted data. Private context must not enter group-facing prompts or output.
- Replay and candidate skill tests cannot send real messages.
- Whole-document Recap edits use version checks; publish replacement before trimming context. Group-facing calls never receive the private whole Recap, only an allowed-source projection. Clearing Recap invalidates cached summaries, not raw memory evidence.
- Full MemPalace is required for the real memory gate; graph and memory checkpoints are distinct.
- Execution remains disabled unless actual isolation is available. Never call `cwd` a sandbox.
- Defaults remain observe/draft, local-only UI, and no live sending. Keep credentials and runtime data out of Git.

## Review focus

1. Owner input races with model completion, tool dispatch, remote completion, and restart: no new stale autonomous effects, no phantom resume (T03, T05).
2. External action succeeded but acknowledgment was lost: record uncertainty and never blindly resend (T03, T06).
3. Malicious group/news text asks for private recall or owner-only actions: retain data provenance and deny elevation/leakage (T04, T06).
4. Recap edits, skill approvals, and active tasks overlap: reject stale changes and keep task-pinned versions (T04, T08, T09).
5. Paths, symlinks, large event bursts, missing adapters, and corrupted input: fail boundedly without escaping the workspace or retry storms (T02, T06, T07).

## Architecture and contracts

### Control/data flow

`timer / owner input / phone events → event gate → scoped context → activity decision → bounded executor → effect ledger / evidence → Recap + MemPalace`

`experience / feedback → budgeted reflection → skill proposal → isolated tests → human approval → next-task activation → observe / rollback`

The event gate, permission checks, fatigue update, and budget accounting do not require a model. SQLite owns application state transitions. LangGraph owns resumable execution state. MemPalace owns its own recall index/data directory. Avoid a distributed transaction: persist outbox-style memory writes with stable evidence IDs and reconcile delivery separately.

### Proposed package map

| Path | Responsibility |
| --- | --- |
| `pyproject.toml`, lockfile, `.env.example`, `.gitignore` | Reproducible environment and secret-free configuration examples |
| `src/mysoul/domain.py`, `config.py` | Pydantic contracts, trusted operator configuration |
| `src/mysoul/storage.py`, `migrations/` | SQLite state, evidence, event dedup, effect and revision transactions |
| `src/mysoul/life.py`, `scheduler.py` | Single-subject activity selection, fatigue, cheap wakeups/coalescing |
| `src/mysoul/model.py` | One swappable model adapter and validation boundary |
| `src/mysoul/executor.py`, `effects.py` | Finite graph, dispatch gate, outcome reconciliation, cancellation |
| `src/mysoul/laputa.py`, `memory.py` | Scoped context, whole Recap revisions, MemPalace MCP lifecycle |
| `src/mysoul/phone/base.py`, `replay.py`, `napcat.py` | Common observe/act/result facade and mutually exclusive backends |
| `src/mysoul/tools/files.py`, `execution.py`, `news.py` | Narrow allowlisted work/read tools |
| `src/mysoul/skills.py`, `evolution.py` | Skill versions, evidence-bound proposal/test/activation lifecycle |
| `src/mysoul/api.py`, `web/index.html`, `web/app.js` | Local operator UI using application services |
| `skills/`, `tests/unit/`, `tests/integration/`, `tests/e2e/`, `tests/fixtures/` | Initial procedures, deterministic tests and redacted replay inputs |
| `docs/runbook.md`, `docs/validation.md` | Setup, recovery, unresolved live gates, measured results |

Proposed local data layout: `.local/state.sqlite`, `.local/graph-checkpoints.sqlite`, `.local/mempalace/`, `.local/workspace/`, and `.local/skill-revisions/`. Exclude all from Git. Chroma storage is upstream MemPalace's responsibility, not a second project-managed memory system.

### Shared schemas and invariants

Define these in T01 so later tasks share one vocabulary:

- `Event`: ID, source/backend, received time, source time if known, sender identity, conversation scope, content reference, dedup key, and trust classification. Only authenticated owner input is `owner_command`.
- `LifeState`: subject ID, activity, mode, fatigue, fatigue-update time, budget counters, dispatch epoch, pending event references, current activity ID. Fatigue must be finite and within `[0,1]`.
- `ActivityDecision`: activity enum, bounded rationale, optional goal ID, optional rest-until time. Runtime may reject decisions that violate budgets or policy.
- `Goal`: ID, explicit objective, completion criteria, step/time/token limits, status, cancellation marker, pinned skill version. Terminal states are completed, failed, cancelled, abandoned.
- `ActivityRecord`: ID, goal ID if any, semantic step cursor, status, context/evidence references, checkpoint reference, dispatch epoch, pinned skill version, effect IDs, continuation decision. `suspended` is not `cancelled`.
- `ToolRequest`: action ID, activity/goal IDs, epoch, tool name, validated arguments, audience/scope, deadline. `ToolResult`: action ID, outcome enum, receipt if supported, evidence reference, error category, completion time.
- `RecapVersion`: subject ID, version, parent version, text, evidence references, author type, content hash, creation time, invalidation epoch.
- `SkillProposal`: ID, skill ID, base version/hash, candidate hash, proposed Markdown/diff, evidence references, test run IDs, status. `SkillVersion`: immutable content hash, parent, review record, activation time.

Core protocols, with auxiliary types defined alongside them:

- `ModelAdapter.decide(context: ContextBundle, limits: ModelLimits) -> ActivityDecision` (async); `execute_step(context, tool_specs, limits) -> StepDecision` (async). Structured validation and bounded retry are adapter responsibilities; effects are not.
- `Phone.observe(cursor: str | None) -> EventBatch` (async); `act(request: ToolRequest) -> ToolResult` (async); `result(action_id: str) -> ToolResult` (async). Backend capability metadata states whether lookup and idempotency are supported.
- `Memory.add(evidence: Evidence) -> MemoryRef`, `search(query: str, scope: Scope, limit: int) -> list[MemoryHit]`, `get(ref: MemoryRef, scope: Scope) -> Evidence` (async). These project methods adapt the pinned MCP schema, not invented upstream signatures.
- `ContextAssembler.build(scope: Scope, budget: ContextBudget) -> ContextBundle` (async). Reserve required instructions and task state first; signal overflow explicitly. Private owner calls may use whole Recap. Group-facing calls exclude it entirely and construct a non-authoritative projection from allowed-source evidence and public persona fields; mixed/uncertain scope is excluded. Cache keys include scope and Recap invalidation epoch. Inspect the final provider payload, not just rendered output.
- `RecapStore.publish(expected_version: int, text: str, refs: list[EvidenceRef]) -> RecapVersion`. One transaction inserts the revision and advances the current pointer; conflicts leave both unchanged. `RecapStore.clear(expected_version: int) -> RecapVersion` publishes an empty version, increments the invalidation epoch, and invalidates cached/derived summaries. Raw MemPalace evidence remains intact. Old cache entries cannot repopulate the cleared head; later retrieval must be explicit and scoped.
- `EffectDispatcher.dispatch(request: ToolRequest) -> ToolResult` (async). Recheck epoch, cancellation, permissions, and budget inside the serialized dispatch boundary immediately before transport invocation.
- `Executor.start(goal: Goal) -> ActivityRecord`, `interrupt(owner_event: Event) -> ActivityRecord | None`, `resume(activity_id: str, decision: ResumeDecision) -> ActivityRecord` (async). `ResumeDecision` is continue/replan/abandon; cancelled goals reject resume.
- `SkillStore.activate(proposal_id: str, expected_base_hash: str, approved_candidate_hash: str) -> SkillVersion`; `rollback(skill_id: str, target_version: str) -> SkillVersion`. Both require explicit operator action and transactional version checks.

## Ready now versus setup later

**Ready to scaffold now:** contracts, SQLite state, fake clock/model, life loop, finite executor, replay phone backend, scoped context fixtures, skill version workflow, and the local UI. No provider credentials, QQ account, group selection, or installation approval is needed to write and test these components.

**Resolve before live gates:** model/provider credentials and limits, the tested MemPalace revision and multilingual index model, NapCatQQ deployment and receipt behavior, authenticated owner/test-group allowlist, and explicit permission for the live smoke action. A code sandbox is required only before enabling arbitrary execution. Missing these settings does not block scaffold or replay delivery.

## Delivery sequence

Dependencies: T01 → T02/T03; T01–T03 → T04-offline; T01–T03 + T04-offline → T05 → T07/T08 → T09 → T10. T04-live (real MemPalace validation) is a parallel release gate, not a dependency of T05 or replay-ready T07–T09. T06 adapter development can run beside T04–T08 after T01/T03; its live gate remains opt-in. T10 full v0.1 requires T04-live plus the real provider and authorized QQ gates. T05 combines the earlier contracts into the first complete replay slice. Do not delay replay scaffolding for provider credentials, QQ deployment, or sandbox selection.

For every task: first write the listed failing tests, run the named test file and confirm failure for the intended missing behavior, implement the narrow deliverable, rerun to green, review its gate, and commit only that coherent unit. Commands are proposed, not executed by this document.

### T01 — Bootstrap contracts and durable state

**Decisions:** D001, D002, D005. **Files:** `pyproject.toml`, `.env.example`, `.gitignore`, `domain.py`, `config.py`, `storage.py`, `migrations/001_initial.sql`, `tests/unit/test_storage.py`.

**Produces:** Shared schemas above; `StateStore.load_subject(subject_id)`, `save_transition(expected_epoch, transition)`, event dedup and ledger persistence. Use short SQLite transactions, schema migration versioning, UTC persistence, and injected clocks. Serialize state-changing application operations; do not hold database transactions across network awaits.

- [ ] Add failing `test_duplicate_event_has_one_record`, `test_stale_epoch_rejected`, `test_cancelled_goal_remains_terminal_after_reload`, and `test_invalid_fatigue_rejected`.
- [ ] Run `python -m pytest tests/unit/test_storage.py -q`; verify expected missing behavior.
- [ ] Implement schemas, migration, transactions, and safe config loading. Add development extras for pytest, pytest-asyncio, and Ruff; lock resolved versions.
- [ ] Rerun the tests, inspect `.gitignore` against secrets/runtime data, and commit.

**Gate:** A restarted process reads identical subject/goal state; invalid/stale changes do not mutate it.

### T02 — Make the life loop cheap and bounded

**Decisions:** D001, D003. **Consumes:** `LifeState`, events, state store. **Files:** `life.py`, `scheduler.py`, `model.py`, `tests/unit/test_life.py`.

**Produces:** `Scheduler.offer(event)`, `next_wake(clock)`; `LifeController.choose(events) -> ActivityDecision`; fake-clock and deterministic-model test adapters. Inject one clock, do not scatter real sleeps in tests.

- [ ] Add `test_rest_has_zero_recurring_model_calls`, `test_owner_wakes_rest`, `test_event_burst_coalesces`, `test_fatigue_clamped_and_rest_recovers`, `test_budget_exhaustion_blocks_model`, and `test_mode_does_not_expand_permissions`.
- [ ] Run `python -m pytest tests/unit/test_life.py -q` and confirm red.
- [ ] Implement cheap gating, finite activity windows, synthetic fatigue accounting, bounded validated decisions, and explicit reflection scheduling. Suppress unchanged self-generated wakeups.
- [ ] Run fatigue/no-fatigue paired simulated traces with the same events; record calls, chosen activity, completion counts, and budget use without claiming one is universally better. Rerun tests and commit.

**Gate:** Long simulated rest stays quiet; bursts produce bounded decision batches; model preference cannot bypass limits.

### T03 — Execute finite goals and reconcile effects

**Decisions:** D002, D004, D005. **Files:** `executor.py`, `effects.py`, `tests/unit/test_executor.py`, `tests/integration/test_checkpoints.py`.

**Produces:** `Executor` and `EffectDispatcher` contracts. Graph nodes prepare bounded steps; all side effects pass through the dispatcher and ledger. Do not place an untracked effect before a replayable graph interrupt.

- [ ] Add `test_interrupt_during_inference`, `test_interrupt_before_dispatch`, `test_interrupt_with_remote_in_flight`, `test_late_result_does_not_resume_cancelled_goal`, `test_unknown_effect_is_not_resent`, and `test_checkpoint_restart_preserves_ledger`.
- [ ] Run `python -m pytest tests/unit/test_executor.py tests/integration/test_checkpoints.py -q` and confirm red.
- [ ] Implement step/time/token limits, semantic suspension, epoch checks, intent-before-dispatch, completion receipts, and unknown-outcome reconciliation. Mark stale in-flight records unknown after restart until verified.
- [ ] Verify continue/replan/abandon on suspended records and reject all resumes of cancelled goals; rerun tests and commit.

**Gate:** Interruptions are honest at inference, pre-dispatch, in-flight, and post-completion boundaries. No duplicate remote effect is assumed safe merely because a graph replays.

### T04 — Add Recap, source-scoped context, and real memory

**Decisions:** D006, D007. **Files:** `laputa.py`, `memory.py`, `tests/unit/test_context.py`, `tests/integration/test_mempalace.py`.

**Offline deliverable (T04-offline):** `ContextAssembler`, `RecapStore`, a fixture `Memory` implementation, and the `Memory` contract. **Parallel real-memory gate (T04-live):** actual upstream MCP integration and persistence validation. T04-offline alone unlocks T05 and later replay-ready work; a deferred T04-live never blocks them. Both use a durable memory-write queue with evidence IDs. Validate upstream tool names/arguments against a pinned tested revision rather than mapping by guesswork.

- [ ] Add `test_recap_stale_edit_conflicts`, `test_failed_publish_keeps_source_context`, `test_context_budget_preserves_required_state`, `test_group_context_excludes_private_sources`, `test_private_recap_canary_absent_from_provider_payload_with_mixed_tags`, `test_recap_clear_invalidates_summaries_but_keeps_raw_evidence`, `test_stale_cache_cannot_repopulate_cleared_recap`, and `test_memory_unavailable_is_explicit`.
- [ ] Run `python -m pytest tests/unit/test_context.py -q`; confirm red, then implement separate private-owner/group-facing assembly, transactional publication/clear, invalidation-aware caching, provenance, and bounded memory process recovery. Group views are projections, never independently editable or canonical memory.
- [ ] Add marked real tests for Chinese evidence write → search → source retrieval, process restart persistence, and separate data/index directories. Select and record embedding model and upstream commit; do not switch embedding models in place.
- [ ] Run `python -m pytest -m mempalace tests/integration/test_mempalace.py -q` only after setup. Record actual results or “deferred”; commit implementation and non-sensitive validation notes.

**Gate:** Real retrieved evidence can be traced to a source. A fake memory adapter is useful for unit tests but does not satisfy the real-memory gate.

### T05 — Deliver the first complete replay slice

**Decisions:** D004, D008, D012. **Files:** `phone/base.py`, `phone/replay.py`, `tests/fixtures/life_trace.jsonl`, `tests/e2e/test_replay_life.py`.

**Consumes:** T01–T03 and T04-offline contracts only; fixture memory/model adapters are permitted for this early gate. T04-live is not a dependency. **Produces:** A deterministic end-to-end event runner and redacted trace format.

- [ ] Add `test_read_silent_reply_choices`, `test_owner_interrupt_preserves_task`, `test_resume_uses_effect_evidence`, `test_replay_has_no_live_transport`, and `test_restart_deduplicates_events`.
- [ ] Run `python -m pytest tests/e2e/test_replay_life.py -q` and confirm red.
- [ ] Implement replay observe/act/result, controlled clock, explicit owner identity fixtures, and a finite task that can be interrupted and resumed. Silence is a successful explicit choice, not a missing result.
- [ ] Run the same trace twice and compare semantic outputs/ledger invariants, not random model prose; review and commit.

**Gate:** Event → read/silent/draft-reply choice → owner interruption → task preservation → continuation works without network effects. Label this replay-ready, not complete v0.1.

### T06 — Validate the real model and QQ in parallel

**Decisions:** D002, D005, D008. **Files:** provider implementation in `model.py`, `phone/napcat.py`, `tests/integration/test_provider.py`, `test_napcat.py`, `docs/runbook.md`.

**Consumes:** Model and phone contracts. **Produces:** A validated provider implementation and explicit NapCat capability/receipt mapping. Operator-supplied setup is required only for live tests.

- [ ] Add contract tests for malformed structured output, refusal, timeout, bounded retry, duplicate QQ events, forged owner names, group prompt injection, rate limits, disconnects, and unsupported receipt lookup.
- [ ] Run `python -m pytest tests/integration/test_provider.py tests/integration/test_napcat.py -m 'not live' -q`; implement fixture-backed adapters until green.
- [ ] Verify the operator-selected provider against structured decisions and tool-call schemas. Run marked provider tests with local credentials; record model identifier and results without secrets.
- [ ] After explicit live permission and deployment verification, run observe-only QQ smoke first, then one allowed test-group action with action ID/receipt capture. Prove non-allowlisted destinations and missing send opt-in are denied. Otherwise record the live gate deferred, not failed or completed.
- [ ] Rerun contract tests and commit.

**Gate:** The same facade works for replay and real QQ. Replay cannot instantiate a live transport. Source/deployment, provider, owner, allowlist, and opt-in settings are documented setup blockers only.

### T07 — Add bounded useful work and read-only news

**Decisions:** D005, D009. **Files:** `tools/files.py`, `execution.py`, `news.py`, `tests/unit/test_work_tools.py`, `tests/integration/test_isolation.py`.

**Produces:** Registered tool specifications consumed by the dispatcher, scoped file operations, read-only news observations, and an execution capability that is disabled unless isolation is verified.

- [ ] Add `test_path_traversal_denied`, `test_symlink_escape_denied`, `test_oversized_output_bounded`, `test_execution_policy_requires_verified_backend`, `test_execution_disabled_without_sandbox`, and `test_news_cannot_issue_owner_command`.
- [ ] Run `python -m pytest tests/unit/test_work_tools.py -q`; implement file/news tools and disabled execution mode first.
- [ ] If a suitable sandbox is selected, add opt-in `isolation`-marked tests in `tests/integration/test_isolation.py`: `test_timeout_kills_process_tree`, `test_network_denied_in_sandbox`, `test_filesystem_escape_denied`, and resource-limit/cleanup checks. Run them against the actual backend with explicit local configuration; they are not mocked unit proofs. Require this gate to pass before enabling execution. Do not enable execution solely because a normal command succeeds.
- [ ] Complete a finite workspace artifact task with evidence and limits, rerun tests, and commit.

**Gate:** At least real workspace read/write work is useful; arbitrary code execution may remain unavailable and explicitly disclosed until isolation passes.

### T08 — Close the reviewed skill evolution loop

**Decisions:** D010. **Files:** `skills.py`, `evolution.py`, `skills/work.md`, `tests/unit/test_evolution.py`, `tests/e2e/test_skill_cycle.py`.

**Consumes:** Evidence, explicit reflection activity, finite executor, and replay. **Produces:** Proposal creation, immutable revision store, candidate-test runner, explicit approval/activation/rollback services.

- [ ] Add `test_proposal_requires_evidence`, `test_candidate_cannot_use_real_effects`, `test_runtime_or_persona_edit_rejected`, `test_stale_approval_conflicts`, `test_active_goal_keeps_skill_version`, and `test_rollback_changes_next_task_default`.
- [ ] Run `python -m pytest tests/unit/test_evolution.py tests/e2e/test_skill_cycle.py -q` and confirm red.
- [ ] Implement one proposal at a time: bounded Markdown procedure changes, base/candidate hashes, test evidence, human review records, atomic activation, and rollback. Preserve objective pass/fail separately from model judgments.
- [ ] Drive a fixture failure → evidence → reflection → proposal → candidate regression run → explicit test approval → next-task new behavior → rollback. Rerun tests and commit.

**Gate:** A skill actually changes the next task's selected procedure after review; a generated proposal alone is not an evolution loop.

### T09 — Expose the small local operator UI

**Decisions:** D006, D010, D011. **Files:** `api.py`, `web/index.html`, `web/app.js`, `tests/integration/test_api.py`.

**Consumes:** Existing services only; no duplicate frontend state authority. **Produces:** Loopback UI for chat, activity/fatigue/mode/budgets, suspended jobs, configuration/Recap editing, and skill review.

- [ ] Add tests for stale Recap edits, stale approval hashes, cancelling already-completed work, unauthenticated mutations, invalid origins, and redacted error responses.
- [ ] Run `python -m pytest tests/integration/test_api.py -q`; implement version-bearing requests, local authorization, origin/CSRF checks, and clear confirmed/unknown effect labels.
- [ ] Verify the browser can interrupt, choose continue/replan/abandon, edit one whole Recap, inspect skill diff and both test result types, approve/reject, and roll back. UI must display deferred live gates and disabled tools honestly.
- [ ] Rerun API tests, perform a manual local UI walkthrough, and commit.

**Gate:** All four chains are inspectable and controllable without a full Studio or public server.

### T10 — Verify v0.1 and document recovery

**Decisions:** D012 and all safety invariants. **Files:** `tests/e2e/test_full_cycle.py`, `docs/runbook.md`, `docs/validation.md`.

- [ ] Add a single four-chain scenario: QQ/replay event → choose read/silence/reply → bounded task → owner interrupt → semantic continuation → recall source → observed failure → reviewed skill proposal → next-task activation → rollback.
- [ ] Run deterministic acceptance suite and restart/failure matrix below. Document actual outcomes, dependency pins, configuration, and limitations; no fabricated benchmark numbers.
- [ ] Run real-provider and MemPalace gates. Run QQ smoke only with explicit permission. Record any deferred live gate and call the milestone replay-ready/integration-pending rather than complete v0.1.
- [ ] Document backup/restore, unknown-effect review, cancelled-goal handling, Recap conflict recovery, memory subprocess failure, embedding reindex, rollback, secret handling, and how to disable all autonomous sends.
- [ ] Review scope, privacy, and dependency/license notices; commit the verified milestone.

## Proposed verification commands

These commands become valid after the corresponding files and dependency extras exist. They are not execution results.

```bash
python --version                         # Python 3.12
python -m pip install -e '.[dev]'
python -m ruff check .
python -m pytest tests/unit -q
python -m pytest tests/integration -m 'not live and not mempalace and not isolation' -q
python -m pytest tests/e2e -m 'not live and not isolation' -q
# Opt-in actual sandbox validation; must pass before enabling code execution:
python -m pytest tests/integration/test_isolation.py -m isolation -q
python -m pytest tests/integration/test_mempalace.py -m mempalace -q
python -m pytest tests/integration/test_provider.py -m live -q
# Only after explicit permission and local owner/group/send configuration:
python -m pytest tests/integration/test_napcat.py -m live -q
```

Register `live`, `mempalace`, and `isolation` markers. Live and actual-isolation tests skip unless explicit configuration is present. Default CI excludes isolation and runs deterministic fixtures with no provider secrets or live transport. A skipped isolation test never permits code execution; skipped live tests never count as successful validation.

## Acceptance matrix

| ID | Proof required | Owning task | Release gate |
| --- | --- | --- | --- |
| A01 | One persisted subject chooses all five activities; rest has zero periodic inference | T02 | Deterministic |
| A02 | Clock-driven fatigue A/B, coalesced bursts, mode changes and hard budget denial | T02 | Deterministic |
| A03 | Interrupt in inference/pre-dispatch/in-flight/completed phases; owner served first | T03/T05 | Deterministic |
| A04 | Cancel remains terminal after restart/late callback; continue/replan/abandon preserved | T03 | Deterministic |
| A05 | Lost acknowledgment remains unknown; no blind resend; event dedup after restart | T03/T06 | Deterministic + backend contract |
| A06 | Whole Recap stale-write rejection; failed publication never trims source context; clear invalidates cached summaries without deleting raw evidence or stale repopulation | T04/T09 | Deterministic |
| A07 | Actual MemPalace Chinese write/search/source retrieval survives restart | T04 | Real engine required |
| A08 | Actual group provider payload excludes private Recap canary even with mixed source tags; injection cannot impersonate owner | T04/T06 | Deterministic |
| A09 | Replay cannot send; real QQ receives and sends one allowed test action with evidence | T05/T06 | Authorized live QQ required |
| A10 | Real model passes validated structured/tool-output and bounded error-path checks | T06 | Real provider required |
| A11 | Workspace work succeeds; traversal/symlink escape denied; unsandboxed code disabled | T07 | Deterministic; isolation gate if enabled |
| A12 | Evidence → proposal → isolated tests → hash-bound approval → next-task skill → rollback | T08/T09 | Deterministic complete cycle |
| A13 | Four-chain trace and operator walkthrough; recovery runbook matches behavior | T10 | Integration review |

## Risks and open operational settings

- **Remote-effect uncertainty:** Timeouts do not prove failure. Surface unknown results and reconcile receipts before any retry (D005).
- **Dependency/API drift:** Pin LangGraph, checkpointer, MemPalace revision, embedding model, and NapCat protocol once tested; do not embed unverified current version claims (D002/D007/D008).
- **Resource weight:** Full MemPalace embeddings/Chroma may need more disk/RAM than the core loop. Measure installation and retrieval requirements before selecting deployment hardware (D007).
- **Behavior tuning:** Trigger cadence, fatigue weights, emotion behavior, context quotas, and reflection frequency are experiment variables, not settled science. Start conservative, record traces, and change one factor at a time (D003).
- **Privacy and context leakage:** Retrieval scope is enforced before model assembly and output dispatch. Store minimal redacted fixtures; set local retention/deletion policy before sustained live use (D006/D008).
- **Replay confidence:** Deterministic replay proves invariants but cannot prove real provider or QQ reliability. Keep live gates explicit (D012).
- **Isolation gap:** Until a verified execution environment exists, code execution remains off; file work and replay may proceed (D009).

Immediate setup questions are listed in DECISIONS.md. They must not block writing the scaffold. Start with T01–T03 and the replay backend; prepare the real-integration lane in parallel. Stop after planning until implementation is explicitly requested.
