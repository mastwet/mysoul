# Vivy-aligned memory consolidation and persona evolution

Status: proposed design for owner review; no product behavior has changed.
Date: 2026-10-22 (Asia/Shanghai).
Baseline: mysoul cfdb5b2; local agent-vivy 7b42b292; local laputa 4b2bec2.

## Intent and boundary

The owner requests Vivy-equivalent memory organization and persona evolution in
mysoul. Success means new lived evidence is durably collected, organized into
usable continuity, considered for evidence-backed persona changes, and visibly
processed without requiring a manual maintenance request after every chat.
The current Python service, SQLite authority, finite LangGraph executor and
Memory adapter remain the implementation. No Go runtime or second scheduler is
introduced. Existing three-minute initiative and explicit local-test settings
remain available.

This extends D006/D010, which currently forbid model-proposed persona evolution.
A superseding decision will authorize proposals through the persona authority,
not unrestricted model writes. Skill evolution remains a separate existing
reviewed chain. This draft does not change the accepted decisions yet.

## Reference findings: implementation versus target policy

Inspected local source, without changing the reference repositories:

- `laputa/laputa/evolution/diva/strategy.go`: collect -> prepare -> reconcile ->
  reflect -> effects -> finish, typed candidates, durable effect receipts,
  explicit no-change/partial/recovery outcomes.
- `laputa/laputa/evolution/diva/prompts.go` and `effects.go`: reference-bound
  memory changes, persona requests, capability proposals and reflection notes;
  Mission and Dream are excluded from this automatic evolution strategy.
- `laputa/garden/evolution/domain.go`: persona effects submit review requests;
  they do not directly activate identity changes.
- `agent-vivy/internal/app/memory_loop_persona_test.go`: approve/reject and
  restart proofs, with existing sessions retaining their frozen persona and
  new sessions using approved revisions.
- `agent-vivy/docs/architecture/VIVY-UNIFIED-CONTEXT-MEMORY.md`: one subject Recap,
  raw evidence retention, atomic revision/coverage, human-edit conflicts,
  frozen authority and WORLD exclusion. This document explicitly describes
  an owner-selected target that is not all implemented. The existing DIVA
  strategy still reconciles Work; do not claim its Recap-only target is shipped.
- `laputa/laputa/persona/service.go`: a separate P16 route permits certain direct
  agent writes. Do not combine that older route with the newer six-stage
  evolution policy or silently grant those extra rights to mysoul.

Current mysoul has versioned Recap with a pending queue, but folds individual
1000-character evidence excerpts in batches of four. Readiness is handed to a
model activity choice; a resting decision can defer unchanged maintenance.
Persona has eight editable sections and revision history, but no model proposal,
review decision or pinned persona projection for future task boundaries.

## Approach and alternatives

Recommended: adapt the reference lifecycle and authority boundaries into the
existing mysoul service. Reuse its one Recap, evidence IDs, transaction layer,
epoch admission, memory outbox and operator UI. Add a durable cognitive-run
record and persona-review records; do not introduce a competing memory engine.

Copying the Go runtime would duplicate scheduling/storage and conflict with
D002. Adding only prompts to the present reflection function would be smaller,
but would not provide replay receipts, reliable source coverage or governed
persona activation. Neither is selected.

## Processing lifecycle

1. **Collect:** commit complete owner/assistant interaction segments and bounded
   task outcomes with stable source IDs, chronology, roles and scope. Failed
   turns remain recorded as failures; generated stories never become observed
   owner biography. Existing raw evidence is retained.
2. **Prepare:** freeze an ordered source window, Recap base revision, persona
   base revision, policy revision and dispatch epoch. Admit whole segments up to
   a configurable character budget. Oversized single segments need an explicit
   continuation coordinate; never mark an unseen truncated suffix processed.
3. **Reconcile:** generate a whole Recap replacement from its committed head and
   the selected source window. Commit Recap revision and coverage atomically.
   Failure, clear, concurrent manual edit or stale epoch preserves the prior
   committed head and leaves uncommitted input available for retry.
4. **Reflect:** examine only committed admitted evidence and the current
   authority snapshot. Produce typed persona proposals, a reflection note, or
   an explicit no-change outcome. Validate cited IDs against this window;
   evidence text cannot choose permissions, operation IDs or storage targets.
5. **Effects:** publish local results through their existing owners, with stable
   operation IDs and receipts. Long-term-memory writes use the existing outbox;
   external unknown outcomes require reconciliation and are not blindly resent.
   Persona proposals never write the active persona head.
6. **Finish:** record covered source coordinates, stage receipts and outcome.
   Restart resumes from committed stages. A committed Recap is not repeated if
   the later reflection failed. A repeated run cannot duplicate a proposal.

The host background loop checks eligibility without a model call. Use a separate
persisted maintenance policy, initially a three-minute minimum interval with at
most one bounded source window per run; this does not replace the chat heartbeat.
No new evidence means no inference. New evidence, owner-selected retry or a due
persisted backoff can admit work. Failures are visible and back off; unchanged
readiness must not suppress all future maintenance. Owner input takes precedence.
Active owner/work inference, modes, fatigue and configured budgets remain gates.
Manual 'organize now' uses the same service, records and guards. Empty maintenance
must not delay a due main-chat initiative.

## Persona authority and activation

- Identity, relationship and dark changes become evidence-backed proposals.
- USER observations have a distinct structured projection; preserve owner-written
  USER material byte-for-byte when applying an observations proposal. Do not copy
  the reference's ambiguous whole-USER actor mapping as an implementation shortcut.
- WORLD changes are reviewable knowledge proposals. WORLD remains available on
  explicit inspection and is excluded from automatic persona model injection.
- Redline, Dream, Mission and the public group projection are owner-controlled;
  the automatic chain has no candidate type that can rewrite them.
- Each proposal stores target, old/new text, reason, source IDs, source window,
  base revision/hash and candidate hash. Approve checks exact revision and hash;
  stale, already-decided or incompatible proposals cannot overwrite manual edits.
- Rejection changes no authority. Approval publishes a new version atomically.
  Rollback publishes a new version based on a chosen historical revision; no
  history is erased. The next admitted owner turn/initiative/task uses the new
  version. In-flight inference and resumed tasks keep their admitted projection.
  This is mysoul's activity boundary, explicitly different from Vivy's persistent
  session boundary because mysoul currently has one main chat without sessions.
- Private proposal content and evidence never enter group payloads. Group calls
  continue to use only explicitly public persona text and permitted evidence.

## Storage, service and UI ownership

Extend `persona.py`, `laputa.py`, `storage.py`, `service.py`, `autonomy.py`, context
contracts and the existing model adapter boundary. Use validated typed outputs;
keep orchestration in a focused cognitive-service module if adding it to the
existing files would mix unrelated responsibilities. Preserve skill APIs.

Memory UI shows current Recap, revision, covered/pending sources, recent run
stages, last result/error, retry and a manual run action. Persona UI adds a review
queue with evidence and old/new text, accept/reject, history and rollback.
Do not show a 'completed' label for a failed publish, pending review or outbox
failure. Existing edit drafts survive a conflict. All UI actions call the same
application service and preserve current Host/Origin/CSRF behavior.

Migrate additively: existing persona text/history and Recap revisions remain.
Legacy pending sources are mapped to segments without discarding suffixes.
Already-published legacy excerpts are recorded as legacy coverage, not falsely
claimed as fully folded source segments. Historical replay is explicit and
bounded; do not reprocess the whole chat archive automatically on first startup.

## Acceptance

- Complete Chinese turns retain decisions, corrections and unfinished commitments
  in actual model input after consolidation; fiction remains labeled as fiction.
- Empty window uses zero calls; due maintenance progresses despite an earlier
  activity REST decision; three-minute initiative is not starved.
- Crash before/after each commit, restart, duplicate delivery, partial effects,
  provider timeout, oversized input/output and invalid references preserve
  coverage and produce inspectable outcomes.
- Owner interrupt, manual Recap edit/clear and persona edit reject stale work.
  A failed consolidation does not retire its source context.
- Unapproved/rejected/stale proposals never change persona. Approved revisions
  affect only future admissions; resumed work retains its pinned snapshot.
- Frozen fields, owner USER text and group privacy have direct payload tests.
- UI can inspect sources, run maintenance, review/reject/approve and roll back.
- Full Ruff/Python/UI suite and a browser walkthrough pass. Real-provider checks
  run separately with existing authorization; unconfigured MemPalace/QQ gates
  remain explicitly pending. No test or reflection may send a live QQ message.

## Next stage

Review this draft's lifecycle and persona authority boundary. After approval,
write the implementation plan with failing-test steps, migrations, code ownership,
stage gates and focused commits; execute sequentially in the current session as
previously requested. No implementation or runtime migration has started.
