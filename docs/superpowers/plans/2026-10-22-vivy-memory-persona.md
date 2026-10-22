# Vivy-aligned Memory and Automatic Persona Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Continuously organize complete experience into Recap and automatically activate evidence-backed persona changes, with durable recovery and rollback.

**Architecture:** Extend the existing single-subject service with one durable cognitive pipeline. SQLite owns run coverage and persona authority; the existing memory adapter/outbox owns retrieval delivery. No new process, scheduler, external dependency or Go component.

**Tech Stack:** Python 3.12, asyncio, Pydantic, SQLite, existing LangGraph executor, FastAPI and existing HTML/JS UI.

**Spec:** `docs/superpowers/specs/2026-10-22-vivy-memory-persona-design.md` (owner correction: automatic persona activation).

## Global Constraints

- Sequential implementation in this chat on `codex/mysoul-v01`.
- Existing loopback-only local-test mode, unlimited call budget and three-minute chat heartbeat remain active.
- One canonical Recap; no silent source truncation or false full-source coverage.
- Redline, Dream, Mission, public group persona and owner-written USER text are not automatic write targets.
- Citation checks establish provenance, not factual correctness; model observations remain labeled.
- No live QQ sending, arbitrary execution, external memory replacement or automatic history purge.
- Each stage: failing tests, smallest implementation, verification, focused commit.

## Review Focus

- Owner sends another turn while consolidation awaits a model: reject stale commits and retain pending sources (Task 2).
- One long story spans a batch: retain its unprocessed suffix and provenance, never promote fiction into owner facts (Task 1/2).
- User edits or clears Recap between stages: never resurrect old text or skip uncommitted coverage (Task 2).
- Automatic persona update races with manual edit or rollback: compare versions and preserve the human change (Task 3).
- Restart after Recap commit but before persona activation: resume from receipts without duplicate folds or persona revisions (Task 2/3).

## Files and ownership

- `src/mysoul/cognition.py`: typed policy/run/source-window contracts and durable lifecycle orchestration.
- `src/mysoul/storage.py`, `laputa.py`: transactional source capture, covered coordinates, Recap CAS and run receipts.
- `src/mysoul/persona.py`: automatic-field policy, USER observations, versioned changes and rollback.
- `src/mysoul/model.py`, `provider.py`: typed reflection adapter contract, deterministic offline response and validated provider schema.
- `src/mysoul/service.py`, `autonomy.py`, `domain.py`: admission, scheduling, context projection and persisted activity pinning.
- `src/mysoul/api.py`, `web/index.html`, `web/app.js`, `web/style.css`: shared-service controls and visible outcomes.
- `tests/integration/test_cognition.py`, `test_persona_evolution.py`, existing API/privacy/UI tests: behavior and failure proofs.

### Task 1: Durable complete source windows

**Interfaces:** `CognitiveStore.capture_interaction(event_id: str) -> None`; `capture_outcome(activity_id: str) -> None`; `pending_window(max_chars: int) -> SourceWindow | None`. SourceWindow carries stable source IDs, ordered whole segments or explicit start/end offsets, base Recap version and invalidation epoch.

- [x] Write tests `test_capture_once_preserves_both_roles`, `test_failed_turn_stays_failure`, `test_large_segment_keeps_unseen_suffix`, `test_reopen_preserves_pending_window`; assert full source equality, role tags, idempotent counts and exact continuation offsets.
- [x] Run `.venv/Scripts/python -B -m pytest tests/integration/test_cognition.py -q`; observe failure before implementation.
- [x] Implement additive object records using existing SQLite transactions. Capture after an interaction settles, including proactive assistant output; do not invent a user message for initiative. Legacy published excerpts remain labeled legacy; backfill only pending inputs on migration. Keep current raw events/evidence.
- [x] Verify the tests and existing evidence/Recap privacy tests. Commit the source-capture slice.

### Task 2: Recoverable automatic Recap pipeline

**Interfaces:** `CognitiveService.run_due(*, force: bool = False) -> CognitiveRun | None`; `status() -> dict`; `set_policy(expected_version: int, enabled: bool, persona_enabled: bool, interval_minutes: int) -> CognitivePolicy`. Default trial interval is 3 minutes, window budget 16000 characters; no evidence yields no run/model call. Policy fields and caps are validated and persisted.

- [x] Add failing tests for empty no-call, due scheduling after REST, retries after failure, owner epoch interruption, concurrent Recap edit/clear, oversized output and crash before/after Recap publication. Verify coverage advances only with a successful atomic publication.
- [x] Implement collect/prepare/reconcile/reflect/effects/finish receipts. Reconcile uses existing `execute_step` with no tools and a complete-document response. Store admitted window and results before stage progression. A committed Recap is not recomputed on later-stage retry. Persist bounded exponential retry delay (3, 6, 12, 24, maximum 60 minutes); explicit retry remains available. Expose the last failure and stage.
- [x] Replace automatic excerpt folding with source-window consolidation, preserving manual Recap CAS and clear behavior. Admit pending raw context until successful coverage; retain the most recent eight complete turns as a configurable tail, subject to the existing context character budget. Fail explicitly when required content cannot fit.
- [x] Integrate one bounded maintenance run per due interval through existing subject admission. Ordinary rest performs only cheap checks; an admitted maintenance run is a visible reflection activity. Owner input wins; due chat initiative receives service between maintenance batches.
- [x] Run targeted tests plus scheduler, proactive chat, Recap and restart integration tests. Commit the pipeline slice.

### Task 3: Automatic persona changes with protected fields

**Interfaces:** `ModelAdapter.reflect(context: ContextBundle, limits: ModelLimits) -> ReflectionDecision`; `PersonaStore.apply_evolution(expected_version: int, expected_epoch: int, operation_id: str, changes: list[PersonaChange], refs: list[str]) -> PersonaProfile`; `rollback(expected_version: int, target_version: int) -> PersonaProfile`.

ReflectionDecision contains a bounded list of typed changes and notes, or an explicit no-change reason. Allowed automatic targets: identity, relationship, dark, world, user_observations. USER observations are a separate field from owner-authored sections.user. Unknown/protected fields are rejected. Each change carries proposed text, a reason and source IDs from the admitted window; runtime supplies operation ID, base version/hash and scope.

- [x] Write failing tests proving valid activation without approval, no-change without a new revision, invalid citations/protected fields denied, owner USER text preserved, duplicate operation idempotent, stale version rejected, rollback is a new revision, restart recovers partial stage completion.
- [x] Implement typed provider schema with existing strict JSON handling; offline fixtures produce deterministic output. Automatically publish valid changes through one atomic authority transaction and log old/new text, evidence, reason, hash and outcome. Memory reflection notes remain private source-labeled evidence and use the existing delivery queue.
- [x] Add persona version metadata to admitted contexts/tasks. New owner turns/initiatives/tasks use current authority; existing activities retain stored instructions and source revision across resume/restart. Exclude WORLD from automatic injection. Group calls retain the explicit public projection only.
- [x] Add payload tests with private marker, generated fiction, stale rollback race, suspended task and new-turn revision. Supersede D006/D010 explicitly for this narrow automatic policy; preserve skill constraints and runtime permissions.
- [x] Run model, persona, privacy, task-resume and cognition tests. Commit the automatic-evolution slice.

### Task 4: Memory/persona controls and visible receipts

**Interfaces:** GET `/api/cognition`; POST `/api/cognition/run` (queued job); POST `/api/cognition/policy`; GET `/api/persona/changes`; POST `/api/persona/rollback`. Mutations use the existing local session, Origin and CSRF rules. Run/policy inputs are versioned; return durable run IDs and honest status rather than long blocking UI calls.

- [x] Add failing API/UI tests for automatic-state display, manual run -> persisted result, failed publication, policy pause, source drill-down, change old/new text, rollback and stale editor preservation.
- [x] Extend existing Memory and Persona pages with small status summaries, recent-run/change lists and details. No mandatory approval queue. Keep complete Recap editing and current persona editing. Actions call the same application service used by the loop.
- [x] Verify API authorization/default token mode and local-test mode, all existing UI tests, representative narrow layout and actual browser flow. Commit the UI slice.

### Task 5: End-to-end acceptance and current runtime activation

- [x] Add an end-to-end deterministic scenario: owner experience -> automatic Recap -> automatic persona version -> future model payload -> manual correction/rollback -> restart -> no duplicate effects.
- [x] Run full Python suite, Ruff, UI tests, JS syntax and package build. Request independent branch review, fix important findings with regression tests, and record deferred gates honestly.
- [x] Back up the stopped local data directory; restart the current port 8767 service with existing local-test mode. Enable the new maintenance/automatic-persona policy. Verify real-provider structured output with a private disposable test dataset first; do not manufacture owner biography or alter the owner's identity as an acceptance fixture.
- [x] Observe the actual application's next eligible window; inspect run receipt, Recap source coverage and any automatic persona change/no-change result. Verify browser inspect and rollback controls without rolling back genuine user data for a test.
- [x] Record results in `docs/validation.md`, recovery/launch settings in `docs/runbook.md`, and actual completion in this plan. Commit and keep the running service usable.

## Plan review and execution

Execution method is already selected: sequential work in the current chat.
Owner approved implementation with automatic persona activation. All implementation
and acceptance steps were executed. Independent review found three Important defects;
all were reproduced and corrected in one fix pass. Live service 8767 completed a
no-change cognitive cycle. The disposable real positive-change scenario timed out
at reflection, including its retries; this remains a failed external acceptance, not
a pass. MemPalace/QQ/isolation gates remain deferred. See docs/validation.md for the
complete record. Existing branch and running data are retained.
