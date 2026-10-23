# Initiative task lanes implementation

Spec: the foreground/background and independent publication proposal approved in the conversation on 2026-10-23.

## Binding behavior
One subject and one visible conversation. Every three minutes is a decision opportunity, not a command to speak. Foreground owner input preempts epoch. Background read-only goals take one checkpointed step per wake, retain progress and never auto-publish their final note. The wake may publish a useful message, schedule/continue background work, or stay silent. Persisted interactions provide immediate handled-input and publication receipts; do not reinstate full dialogue history or implicit MemPalace retrieval. Existing credentials, QQ gates, Recap and other pending changes remain intact.

## Task 1: Immediate attention receipts
Add bounded owner-only runtime attention data to initiative context from canonical persisted interactions. Include replied inputs, recent actual publications and task progress with original times. Failed replies must not be marked answered. Reject exact repeated initiative publications; semantic avoidance uses recent receipts, not keyword lists. Test stale Recap, restart, scope isolation and context limits (RED then GREEN).

## Task 2: Checkpointed background execution
Add backward-compatible Goal.lane and ActivityRecord.pause_reason, optional ActivityDecision.background_task contract. Background goals are runtime restricted to read-only tools. Yield after one committed step, retain semantic notes, resume from checkpoint without repeating tools. Foreground behavior unchanged. Test yield/resume/restart, interruption, cancellation and authority (RED then GREEN).

## Task 3: Wake decision and publication
Replace speech-biased prompt with equal choices to remain silent, perform bounded background work or speak. Support one persisted background task at a time and continuation of committed background work on wake; no automatic foreground resumption by this path. Keep the existing three-minute deadline, admission, fatigue, budget and epoch gates. Include task summaries/results in decision data; only publish when chat_action=reply. Keep status inspectable. Test independent silence/work/reply decisions and owner preemption (RED then GREEN).

## Task 4: Integration and activation
Run full Python suite, Ruff and UI tests. Request one fresh scoped code review, fix material findings with RED/GREEN tests. Exercise real gateway using only public synthetic data. Stop the known local service, fully back up its data, restart on the same port and verify MemPalace health plus ordinary status/browser flow. No private diagnostic gateway replay. Focused commits exclude pre-existing changes; preserve them through index-only patch staging.

## Review focus
Old goals without lane; stale Recap vs immediate publication receipts; large/untrusted task strings; denied tools even if model emits them; cancelled or uncertain tasks never resurrect; owner interruption during a background model/tool await; no new memory-source pollution from runtime receipts; repeat-publication detection cannot suppress task progress; no tight idle resume loop.
