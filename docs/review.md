# Independent review and disposition

Date: 2026-10-22. Reviewed range: `4e336cf..83f8ac1`.
A fresh-context reviewer inspected the complete branch read-only and reproduced failures
using temporary directories and fixture HTTP. No real QQ message or provider request was made.
The review required changes; the author then completed one regression-driven fix pass.

## Important findings fixed

All regressions were observed failing before implementation, then passed in
`tests/integration/test_review_regressions.py`.

| Finding | Resulting behavior |
| --- | --- |
| Crash after sending but before interaction persistence allowed another send | A durable event-to-reply intent is claimed before execution. Recovery reads its existing effects; confirmed and unknown outcomes never create a replacement autonomous goal. Both receipt paths have crash tests. |
| Asynchronous context loading adopted a new owner epoch | The original admission epoch travels through context preparation and goal admission. Stale preparation cannot dispatch. Owner turns bypass ambient inference waits, and ambient processing yields while an owner turn is active. |
| A coalesced reply ran once per original event | A conversation batch consumes each event but selects at most one response operation. A repeated send step is also refused after the first reply action. |
| Valid oversized events permanently blocked the inbox | Conversation work is split into bounded chunks. An individually overflowing event keeps its full evidence and an explicit overflow outcome; unrelated pending events continue. |
| Cleared Recap remained in later model calls | Context carries Recap revision/invalidation metadata and refreshes before new admission. A revision race during graph admission suspends explicitly. Already transmitted snapshots remain historical evidence. |
| Candidate tests overwrote concurrent rejection | Test evidence is retained, but finalization rereads proposal hash/status in a transaction and appends to the current test IDs. Rejection or activation cannot be reopened. |
| Memory delivery depended on new phone events | Every bounded tick can drain the outbox, including quiet ticks and foreground work. Unavailable memory preserves pending evidence and never wakes the model. |

## Minor findings and grading

The activity/mode/rest and receipt-label findings were promoted to Important for this
experiment: incorrect work state changes fatigue accounting, and a false “sent” result
misrepresents an external effect. Their regression tests now cover real work state,
one-time rest expiry, quiet-mode suppression, receipt-derived text, and local drafts
never being reported as QQ sends. The frontend now labels confirmed sends and activated
skills according to their actual state. No reported minor remains deferred.

## Decisions and verification limits

- The PowerShell ledger replaces the skill's Bash helper scripts because the existing
  T01–T10 plan headings use a different format. Task commits, red/green evidence and
  this durable report retain the equivalent record; automatic helper bookkeeping is absent.
- Actual provider compliance, full MemPalace persistence and NapCat deployment/receipt
  behavior remain separate live gates. Configuration alone does not close them; the
  delivered milestone is offline-ready, not fully validated v0.1.
- Arbitrary execution remains disabled, so there is no claim about an isolation backend.
- Windows descriptor/symlink/hardlink checks passed. POSIX-specific behavior and
  adversarial filesystem race stress were not independently validated; verify those
  before deployment on a different platform.
- Fatigue and candidate procedures use deterministic experiments. They establish
  scheduling and versioned-procedure behavior, not psychological fatigue or general
  model improvement.

Final verification: **98 passed, 8 skipped**. Skips are one real provider, one real
MemPalace, two separately authorized QQ checks, and four unavailable-isolation scenarios.
Ruff and JavaScript syntax checks passed. Current source builds a wheel; installed-wheel
resource and SQLite/skill initialization were checked separately.
