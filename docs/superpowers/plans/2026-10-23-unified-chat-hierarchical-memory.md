# Unified Chat and Hierarchical Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** One permanent owner conversation with paginated original history, task results and proactive messages, backed by traceable hierarchical context compression.
**Architecture:** Add an ordered timeline and immutable archive tree in the existing SQLite authority. Publish compression and frontier changes atomically; existing single-subject admission schedules bounded maintenance. The UI reads the timeline while model contexts read its scoped non-overlapping archive frontier.
**Tech Stack:** Existing Python 3.12/uv, SQLite, Pydantic, FastAPI, HTML/JS; existing model and memory adapters. No new runtime/dependency.
**Spec:** docs/superpowers/specs/2026-10-23-unified-chat-hierarchical-memory-design.md (owner approved 2026-10-23).
**Execution:** Current chat, sequential implementation on existing codex/mysoul-v01; one final independent review. Owner approved; Tasks1–5 implemented and verified.

## Global Constraints

- Preserve immutable raw messages, internal Scope privacy, epoch/CAS, cancellation terminality, active-task persona/skill pinning, Host/Origin/CSRF, tokenless local-test settings and three-minute initiative.
- L0 unit is a complete interaction/result, not an individual role message. Default count trigger100/batch70, protected recent8; upper-level trigger4/batch3, max level8 with same-level root compaction.
- Serialized input high/low watermarks75%/55%; one bounded batch per admitted run. L1 summary cap4000 characters, higher cap6000; reject empty, tool-producing, incomplete or larger-than-replaced summaries.
- Publication freezes source hashes, child versions, epoch and Recap invalidation epoch. Summaries do not become new persona evidence. No actual QQ send or code execution changes.
- Every task follows RED -> minimal implementation -> GREEN -> focused commit. Full baseline at start; use the workspace's .venv and primary workspace .local directories for pytest temporary files to avoid Windows permissions errors.

## Review Focus

1. Owner input or task update during compression: frozen source revision must fail publication, leaving raw history and current frontier unchanged (Task2 test_publish_rejects_changed_task_leaf).
2. Identical timestamps and new messages during older-page loading: stable sequences/cursors must not duplicate or skip items (Task1 test_cursor_survives_identical_times_and_new_items; Task4 test_pagination_with_live_append).
3. One extremely large result: exact fragment offsets persist and no partial prefix claims whole-leaf coverage (Task2 test_oversized_leaf_fragment_resume).
4. Clearing Recap during a saved compression run: old snapshots cannot publish or restore cleared working memory (Task3 test_clear_supersedes_archive_run).
5. Old feedback and summary evidence returned by lexical search: no recursive persona learning and no parent/child context duplication (Task3 test_recalled_child_is_not_injected_twice).

## File Responsibilities

- New src/mysoul/timeline.py: owner timeline contracts, idempotent source projection, cursor reads and legacy migration.
- New src/mysoul/archives.py: archive contracts, source slices, frontier planning, atomic publication and scoped expansion.
- New src/mysoul/compression.py: durable compression runs, budgeted model admission, recovery and retry.
- New src/mysoul/migrations/002_unified_history.sql: additive timeline/archive tables, sequence/change indexes and schema marker.
- Modify storage.py: ordered migrations and transaction hooks; service.py: lifecycle/assembly/status; autonomy.py: one shared maintenance lane; laputa.py/domain.py: scoped archive context projection; api.py: cursor/archive inspection endpoints.
- New web/timeline.mjs: pure page merging and timeline state; modify web/app.js,index.html,style.css: one-chat presentation and in-place task cards.
- Tests: integration/test_timeline.py,test_archives.py,test_compression.py; e2e/test_unified_history.py; ui/timeline.test.mjs plus existing app tests.

### Task 1: Durable Owner Timeline and Paginated History

**Interfaces:** TimelineStore(store); migrate() -> None; interaction_in(db,event,result) -> TimelineItem; task_in(db,goal,activity) -> TimelineItem; page(*,before:int|None=None,after_change:int=0,limit:int=50) -> TimelinePage. TimelineItem has id, immutable seq, mutable revision/change_seq, kind(chat|task), scope, source_id, timestamps, body. TimelinePage contains ordered items, next_before, has_more, change_cursor and pinned read watermark. before pages read older items; after_change polls inserts and edits, including cards outside the newest page.

- [x] Write test_migration_is_repeatable, test_interaction_capture_is_atomic, test_task_updates_keep_one_seq, test_cursor_survives_identical_times_and_new_items. Seed150 interactions: first page50, older pages50/50, original IDs exactly once; add/update during paging and verify captured pages remain complete and polling returns the card update.
- [x] Run `.venv/Scripts/python.exe -B -m pytest tests/integration/test_timeline.py -q`; observe missing timeline implementation failures.
- [x] Add ordered, idempotent SQL migrations and unique scoped source identity. Allocate timeline seq once; use a separate monotonic change cursor for edits. Hook completed interactions and goal/activity state transactions. Project pending owner events as one stable pending item resolved in place; unfinished migrated requests remain explicitly unfinished. Exclude group scope from the owner timeline. Legacy ordering is event time plus stable ID; persist migration completion under lease.
- [x] Run timeline, storage, API, owner-input, proactive and executor tests. Verify startup migration preserves current schema/data and no task terminal status changes. Commit `feat: persist one ordered owner timeline`.

### Task 2: Immutable Archives and Atomic Frontier

**Interfaces:** ArchiveStore(store); frontier(scope:Scope) -> list[ArchiveNode]; plan(policy:CompressionPolicy, budget_chars:int, reserved_chars:int) -> CompressionPlan|None; publish(plan:CompressionPlan, summary:str, operation_id:str) -> ArchiveNode; expand(node_id:str,scope:Scope,*,before:int|None=None,limit:int=50) -> ArchivePage. Nodes record id, level, source range/offsets, time span, child IDs/revisions, source hash, summary, epoch/invalidation, generation and active state. CompressionPlan freezes selected contiguous children and their versions.

- [x] Write test_l0_count100_compacts70, test_level4_compacts3, test_level8_root_compaction, test_frontier_is_a_partition, test_publish_rejects_changed_task_leaf, test_publication_rolls_back_on_failure, test_scope_propagates_to_archives and test_oversized_leaf_fragment_resume. Assert complete raw recovery via child traversal and unchanged frontier after rejected publication.
- [x] Run `.venv/Scripts/python.exe -B -m pytest tests/integration/test_archives.py -q`; observe missing archive contract failures.
- [x] Implement leaf projections and indexed scoped frontier. Fold oldest adjacent same-level nodes; capacity pressure may choose a smaller oldest batch that fits, without compressing protected recent8. Level8 may merge older level8 nodes without increasing level. Persist leaf fragments with [start,end,total] coordinates and bounded batch input; only complete leaf coverage retires its original projection. Never partially mark a whole turn compressed. Scope checks apply both to parent and all children.
- [x] Publish parent, child links, receipt and frontier changes in one transaction, with operation hash idempotence and version/epoch/invalidation checks; reject summary growth, empty output and invalid links. Run archive and prior timeline tests. Commit `feat: add traceable hierarchical memory archives`.

### Task 3: Bounded Compression and Context Integration

**Interfaces:** CompressionService(soul); run_due(*,force:bool=False) -> CompressionRun|None; status() -> dict. Durable run stages prepare/generate/publish/finish, with frozen plan/result, attempts, next_attempt_at and error. ContextAssembler gains archive evidence and covered-range metadata; only explicitly owner-scoped projections enter owner context. ArchiveStore plan/publish from Task2 are the authority.

- [x] Write test_empty_archive_work_makes_no_call, test_capacity75_triggers_before_overflow, test_batch_stops_at_low55, test_failure_preserves_context, test_restart_reuses_saved_result, test_owner_epoch_supersedes_publish, test_clear_supersedes_archive_run, test_recalled_child_is_not_injected_twice and test_group_payload_excludes_private_archive_marker. Use a controllable clock/model and inspect actual payloads/reservations.
- [x] Run `.venv/Scripts/python.exe -B -m pytest tests/integration/test_compression.py -q`; observe missing integration failures.
- [x] Use existing model.execute_step(context,[],limits) with `[archive-compression]`; require done=True, no tool, bounded note. Reserve calls/tokens before inference with existing settings. Persist model result before publish; retry3/6/12/24/48/60 minutes, explicit retry allowed. Freeze policy/version and honor shared admission, rest/mode/fatigue/owner preemption. Empty and unchanged readiness stay cheap; compression cannot starve initiative or existing pending goals.
- [x] Assemble fixed instructions/current input/necessary task state, then non-overlapping scoped frontier and protected recent8, then optional recall. Suppress overlapping raw/cognitive/recall projections using source IDs and coverage, not text equality. Retain exact source evidence for persona windows. Keep Recap as a separately versioned current working summary; change automatic reconciliation instructions to maintain current facts/commitments rather than re-append the entire archive. Do not add archive summaries as new cognitive sources or new memory outbox duplicates. On unfit required context, keep raw data and expose explicit overflow plus queued compression; never claim admission succeeded.
- [x] Provide scoped paginated expansion for original evidence through existing Memory adapter boundaries and archive inspection, with bounded query-time expansion. Manual Recap edit/clear checks preserve current behavior and invalidate saved archive publication; historical chat remains accessible. Run memory/privacy/cognition/persona/restart/proactive/executor tests. Commit `feat: integrate bounded archive compression into owner context`.

### Task 4: One Chat UI with Pagination and Task Cards

**Interfaces:** GET /api/timeline?before=&after_change=&limit=; GET /api/archives; GET /api/archives/{id}?before=&limit=; POST /api/archives/run with expected policy version queues one job via existing launcher; timeline.mjs exports mergeTimeline(current,page) and prependScrollAnchor(previousMetrics,nextMetrics). All routes use current read/write security rules. Keep status.interactions for compatibility; UI chat authority moves to timeline endpoint.

- [x] Write API tests for owner-only paging, invalid cursors, cross-scope archive reads, CSRF/Origin and queued-run version conflict. Write UI tests test_single_chat_has_no_session_list, test_pagination_with_live_append, test_task_card_updates_in_place, test_failed_older_page_preserves_loaded_messages, test_archive_inspection_preserves_chat_draft. Assert source/role labels and no duplicate pending/confirmed rows.
- [x] Run targeted API tests and `node --test tests/ui/timeline.test.mjs tests/ui/app.test.mjs`; observe failures before implementation.
- [x] Remove recent-message/session-list UI. Keep one permanent chat, composer and fatigue card. Render pending/reply items and collapsible task status/result cards in timeline order; initiating a task returns to that same chat. Use key-based merges and independent change polling; deduplicate optimistic messages by server identity. Older-page loading maintains viewport anchor and draft; errors preserve loaded pages and allow local retry. Keep memory/persona/settings as management surfaces, not extra conversations.
- [x] Expose archive levels, time ranges, failure/retry and scoped raw inspection in the memory page. Background compression and heartbeat checks do not become chat messages. Verify desktop/narrow layout and loading/error behavior in actual browser on a disposable fixture. Run full UI tests and JS syntax check. Commit `feat: present one permanent paginated chat with task results`.

### Task 5: Migration, Recovery and Live Acceptance

- [x] Write tests/e2e/test_unified_history.py with owner chat -> initiative -> task result -> L1 -> L2 -> restart -> correct context -> raw expansion. Assert stable order, exact leaf coverage, one card per task, cancelled goals stay terminal, and no summary-generated persona feedback.
- [x] Run full Python/Ruff/UI/JS/build/diff checks; request one fresh whole-branch review. Reproduce and fix Important findings with RED/GREEN tests and a full passing suite. Record external gates separately from local completion.
- [x] Verify provider compression on authorized disposable data first. Stop and fully back up `.local/ui-redesign`; migrate/restart8767 with existing flags. Existing explicit authorization permits one current-context diagnostic replay to the configured8045 gateway when needed; no new destination or external send is implied. Do not create fictional owner history as a live test.
- [x] Verify existing history paging, unified live owner/initiative/task projection, compression receipts and restart recovery. Keep testing cards/rollbacks in isolated data. Archive raw content never enters Git. Observe actual bounded maintenance and browser presentation; record any latency, skipped checks or failure honestly.
- [x] Update docs/DECISIONS.md,runbook.md,validation.md and mark this plan's actual completion. Keep codex/mysoul-v01 and current service usable; no merge/push requested. Commit `docs: record unified history acceptance and recovery`.

## Verification Commands

Use unique `--basetemp=C:/Users/Administrator/Desktop/mysoul/.local/<task-run>` and TEMP/TMP in the same primary workspace. Baseline:236Python passed/8 explicit skips,27UI passed. Final commands: `.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider --basetemp=<unique> -q`, `.venv/Scripts/ruff.exe check --no-cache .`, `node --test tests/ui/*.test.mjs`, `node --check src/mysoul/web/app.js`, `uv build --offline`, `git diff --check`. Success requires actual passing output; external skips never certify full v0.1.

## Plan Self-Review

Spec coverage mapped to Tasks1–5; stable ordering and mutable card polling have separate cursors. All shared interfaces above have one defining task and consistent consumers. Privacy, root-level capacity, large leaves, Recap invalidation and persona feedback isolation have named tests. No product dependencies or extra concurrent scheduler planned. Owner approved current-chat sequential execution; final independent review and verified fixes are recorded in docs/validation.md.


## Completion record (2026-10-23)

Tasks1–5 complete; final274 Python passed/8 external skips,34 UI passed, clean Ruff,
JS syntax, offline build and diff. One independent review, eight Important issues
reproduced and fixed; additional scope/count regressions fixed in the same pass.
Synthetic real-provider archive generation passed; actual8767 migrated with full
stopped backups and natural initiative preserved. See docs/validation.md for measured
results and review rulings, docs/runbook.md for recovery. Branch/worktree retained.
No MemPalace/QQ/isolation full-release certification is implied.
