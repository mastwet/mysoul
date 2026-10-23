# mysoul local operations

## Start and verify

Use the feature checkout shown in the delivery message. Python 3.12 and uv are required.

```powershell
uv sync --locked --extra dev
uv run python -m mysoul serve
```

Open the loopback URL printed by the command. Its fragment contains the local operator token; the browser removes it from the address after reading it. The token is retained in that tab's session storage. Private reads require the token; mutations additionally require the configured origin and a session CSRF nonce. Keep one process per data directory. No LAN/public binding is supported.

### Configure the model in the UI

Open **设置 → 模型服务**, choose **真实模型 · OpenAI 兼容接口**, and enter the
provider's base API URL (normally ending in `/v1`), raw model ID and API key.
The **本机操作令牌** authenticates this UI; it is unrelated to the provider API key.
The header reports the active model independently of the QQ transport backend.

**测试连接** sends one minimal structured-output request with a 30-second limit,
no retry and no chat/Recap/evidence payload. It consumes the subject's durable
model budget and neither saves nor activates the form. **保存并启用** atomically
saves and switches the active model while the subject is idle. Normal inference
then sends its scoped context to that configured service. Saving does not itself
test compatibility or pass the full live integration gate. **撤销修改** restores
the latest polled configuration and clears the unsaved key, including after a
version conflict. A failed save retains inputs.

Saved settings take precedence over model environment variables on the next
`serve` start. They are stored only in the selected data directory's `model.settings`,
excluded from Git. On Windows, DPAPI encrypts the entire file for the current OS
user; copying it to another user/machine is not a portable credential backup.
On POSIX, the file is owner-readable/writable (`0600`), without DPAPI encryption.
Keys never appear in API reads and blank keys preserve the current key only for
the exact same base URL. A new base URL requires a newly entered key. HTTPS and
loopback HTTP endpoints are supported; redirects are not followed. Switching to
offline mode retains the last saved provider details for a later switch back.
The `replay` command always ignores saved providers and remains offline.

After updating/restarting this development server, reload existing UI tabs to get
the matching JavaScript and a new session CSRF nonce. A provider base URL must
include its required path, e.g. `/v1`; mysoul appends `/chat/completions`.
Provider replies can be raw schema-valid JSON or one complete outer JSON code
fence. Extra prose, partial/multiple blocks and invalid fields remain rejected.

**单次输出 token 上限** is optional: leave it blank to omit `max_tokens` entirely,
allowing the provider to apply its own limits. **系统累计 token 预算** is independently
optional: blank means unlimited; `0` still blocks calls. Save to apply both settings
and restore them on restart. Legacy saved configurations and clients that omit these
fields preserve the existing runtime limits; explicit JSON `null` means unlimited.
New UI/owner-created work goals inherit the unlimited token choice. Existing goals
retain their original budgets; finite goals keep their original per-step ceiling.
Candidate trials retain their independent step/token limits and honor a smaller
configured output cap. Call counts, deadlines, context byte limits and permissions
remain active.

Token counters are admission estimates, not billed usage. Without an output cap,
the provider reservation includes only input/schema/framing estimates; it cannot
bound the eventual output or bill. Use provider-side spending controls for a monetary
cap. Reasoning models can consume a small output allowance internally before any
JSON text is returned, so a tiny cap can make a valid connection test fail.

The default uses deterministic offline responses and fixture memory. It is useful for exercising state and review workflows; it does not perform general AI work. For a deterministic file-task demonstration, set `MYSOUL_MODEL_MODE=procedure-replay`. That fixture writes `report.txt`, and reads it back when the active skill contains `Procedure: verify`.

The UI opens in the conversation view. The top-right fatigue card opens current
activity and budget details. The sidebar holds tasks, memory, skill review and grouped
settings. Appearance and Enter-send preferences save in this browser; subject state
and public-persona edits require their explicit save actions. Enter sends by default;
Shift+Enter inserts a newline. Settings can switch sending to Ctrl/Command+Enter.

```powershell
uv run python -m mysoul replay --trace tests/fixtures/life_trace.jsonl --data-dir .local/replay-demo
uv run ruff check .
uv run pytest -m 'not live and not mempalace and not isolation' -q
uv run python scripts/fatigue_trace.py
```

`replay` forces offline phone, model and memory settings even if live variables exist. Environment variables are read explicitly; `.env` is not automatically loaded. Use `uv run --env-file .env ...` if desired. Never commit that file.

## Automatic activity boundaries

Life decisions dispatch committed work, configured news reads and explicit reflection.
An authenticated owner work choice can commit a new goal; external source text cannot
create work authority. Pending work and newly retained evidence produce a durable
readiness signal. Each unchanged signal is considered once, including across restart;
plain rest does not poll the model. A selected future rest deadline defers background
readiness. Quiet mode suppresses incidental wakeups. Changed readiness or a new owner
turn permits a fresh decision.

Completed/failed tasks retain source-backed feedback. Failure feedback can produce
one reviewable proposal during reflection. Pending owner/public evidence can produce
a private Recap during that same explicit budgeted activity. Publication and segment
retirement share a transaction; failures retain the old Recap and raw evidence. Clear
also retires older pending consolidation segments. Whole private Recap remains excluded
from group model requests.

Candidate tests compare immutable base and candidate versions in separate temporary
workspaces. The candidate-test endpoint accepts up to four objective cases (`id`,
`objective`, `initial_files`, `expected_files`, `required_tools`). Offline mode uses
the draft/verify fixture; configured provider mode uses a fresh configured provider.
Both expose local tools only; provider calls also charge the original subject's budget.
A favorable model judgment cannot override a failed artifact assertion. Actual provider
behavior/improvement remains unverified. Skill activation still requires operator review.

## Live setup gates

Each gate remains independent. Configuration or a skipped test is not validation.

| Capability | Configuration and verification |
| --- | --- |
| Model | Configure **设置 → 模型服务**, or set `MYSOUL_MODEL_MODE=provider`, `MYSOUL_PROVIDER_URL`, raw `MYSOUL_MODEL`, and `MYSOUL_API_KEY` when no saved local model settings exist. The marked live contract test reads environment credentials and requires explicit `MYSOUL_VALIDATE_PROVIDER=1`. UI connection tests do not replace this gate. |
| Full MemPalace | Install full upstream dependencies in a separate Python environment at a pinned, reviewed checkout. Set `MYSOUL_MEMORY_BACKEND=mempalace` and `MYSOUL_MEMPALACE_CONFIG` to a local JSON process configuration. Run the marked Chinese write/search/get/restart test. No lightweight replacement satisfies this gate. |
| QQ | Verify the official NapCat deployment and version. Set `MYSOUL_PHONE_BACKEND=napcat`, endpoint/token variables, trusted owner ID, and comma-separated allowed group IDs. Group history polling is observe-only by default. No deployment, login, or live message was performed during development. |
| Code execution | Disabled. No isolation backend is implemented. Skipped isolation tests cannot enable execution. |
| News | Set comma-separated exact HTTPS `MYSOUL_NEWS_SOURCES` to expose the allowlisted `read_news` tool. Fetched text remains untrusted public evidence. No source is enabled by default. |

The full MemPalace source revision `f41e8e75ddaadf5588d5127715fa531d79eadb45` passed the real Chinese write/search/get/restart gate on 2026-10-23. The tested CPU runtime uses upstream 3.12.0, Chroma 1.5.9 and multilingual `embeddinggemma` (q8 ONNX, 384 dimensions). See the dated validation entry for exact scope; this does not certify QQ or code isolation.

Example process configuration (local absolute paths must be supplied):

```json
{
  "command": "C:/path/to/mempalace-env/Scripts/python.exe",
  "args": ["-m", "mempalace.mcp_server"],
  "source_dir": "C:/path/to/pinned/mempalace",
  "revision": "f41e8e75ddaadf5588d5127715fa531d79eadb45",
  "data_dir": "C:/path/to/mysoul/.local/mempalace",
  "embedding_model": "embeddinggemma",
  "env": {}
}
```

The adapter binds upstream palace/config paths and embedding selection to this configuration, checks the checkout revision and current MCP schemas, and records an index identity. Changing the model/revision for an existing directory is refused. Use a new directory and an explicit source replay/reindex procedure; retain the previous directory until verified. LangGraph's `graph-checkpoints.sqlite` is unrelated to MemPalace's memory checkpoint tool.

Enable QQ sending only after explicit authorization: a configured owner, allowlisted test group, and `MYSOUL_SEND_ENABLED=true` are all required. Missing acknowledgment remains unknown. OneBot receipt lookup by this project's action ID is unsupported. Start with observation and then one explicitly authorized test message; save the action ID and returned receipt. Group contexts exclude private Recap, private evidence and private work-skill text before provider invocation. A nickname or message claiming to be the owner has no authority. The local authenticated UI is the owner command entry point; QQ group input stays data.

The marked observation test additionally requires `MYSOUL_VALIDATE_QQ=1`. The send test requires separate `MYSOUL_QQ_SMOKE_SEND=1` and explicit `MYSOUL_QQ_TEST_GROUP`; it sends exactly `mysoul integration smoke test` through the effect ledger. These opt-ins were not enabled during development. Do not set the send flag without authorization for that actual message.

## Recovery and review

- **Stop autonomous sends:** stop the process, set `MYSOUL_SEND_ENABLED=false`, restart. Already dispatched requests may still finish remotely; inspect their receipts.
- **Unknown action:** inspect the effect record and remote history. Query receipts when supported. Never retry the same uncertain remote effect under a new action ID merely to clear uncertainty. If it cannot be resolved, retain unknown and abandon the dependent activity.
- **Interrupted work:** the UI exposes continue, replan and abandon. Continue retains the semantic cursor; replan starts a new execution thread with the same goal and retained evidence. Cancel is terminal, including across restart and late callbacks. Active tasks keep their pinned skill. Admission carries the original dispatch epoch across asynchronous context retrieval.
- **Recap conflict:** keep the editor contents, reload the committed version, and deliberately reconcile before resubmitting. Clear creates a new empty version and preserves raw evidence/history; it is not permanent erasure. Already admitted/in-flight data is not retrospectively wiped. Every subsequent model admission refreshes Recap version/invalidation metadata; a concurrent change during graph admission suspends for explicit continuation.
- **Memory unavailable:** the UI/context reports degraded recall. Local evidence and pending memory writes remain in SQLite. Restore the configured engine and restart; delivery uses stable evidence IDs. Do not change the embedding model in place.
- **Skill review:** select evidence, reflect or submit bounded Markdown, inspect the diff and objective tests, then explicitly approve the tested hash. Reject unsupported proposals. Rollback selects the default for subsequent work; historical task versions and evidence remain.
- **Budget exhausted:** stop before new inference when a configured finite budget is reached. Counters are durable per subject; change the token budget under model settings or set runtime environment limits. With capped output, provider reservations include prompt/schema bytes, output caps and configured attempts. Uncapped output reserves input/framing estimates only. Neither counter is measured billing or tokenizer usage.
- **Backups:** stop the service, copy the entire data directory including both SQLite databases, skill revisions, token and memory directory. A stopped service avoids inconsistent cross-file snapshots. Restore into a separate directory, start one process there, and verify histories before returning to daily use. Retain the original backup.
- **Retention:** raw transcripts/evidence and Recap history are retained locally. Specify a separate targeted deletion policy before sustained live use; clearing Recap does not erase backend evidence or backups.
- **Reply recovery:** each event claims a durable reply intent before execution. On restart, a confirmed or uncertain operation is recovered from that association; a new reply goal is never silently created. Coalesced conversation batches produce at most one reply. Oversized events retain full evidence and an explicit overflow outcome so unrelated inbox entries continue.
- **Modes and rest:** quiet mode suppresses incidental model wakeups; direct address and authenticated owner input can wake it. Focused mode supplies a preference for bounded work without changing permissions. A chosen rest deadline can wake once; plain rest does not poll a model. Foreground tasks are recorded as work for fatigue accounting.

## Main-chat heartbeat

In Settings → Life, enable main-chat initiative and choose the interval. The
three-minute option is useful for observing the loop; it is a model check, not a
promise to send a message each time. The chat status distinguishes checking,
quiet completion, a proactive message and failure. Pending maintenance already
considered by the model does not permanently block a due heartbeat.

The next due time is persisted across restart. The background polling cycle and
active inference can delay a due check slightly; checks do not run concurrently.
Quiet/focused mode, high fatigue, active owner/work execution and exhausted
budgets can defer checks. A finite model-call budget is cumulative, including
quiet/failed checks: the default 100 calls supports at most five hours at a
three-minute cadence from a fresh counter, before other model work is counted.
Inspect Settings and the call budget if checks stop. For local testing, start with `--local-test` to disable the operator-token
requirement and cumulative call ceiling. Alternatively, set
`MYSOUL_MODEL_CALL_LIMIT=unlimited` to disable only that ceiling, or use a finite
integer for a longer run. `MYSOUL_OPERATOR_AUTH_REQUIRED=false` controls tokenless
loopback access separately. Keep the chosen flags/environment on each restart. Do not reset stored
counters or force repeated retries to conceal failures. A failed request leaves
the next scheduled attempt available; inspect the configured model gateway when
failures recur.

## References and notices

- [LangGraph checkpoint SQLite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite) supplies graph persistence, not exactly-once remote effects.
- [MemPalace](https://github.com/MemPalace/mempalace) supplies the full memory engine. It is MIT licensed; preserve its notices and review dependency notices when packaging it. Its source and large dependencies are not vendored into mysoul.
- [NapCat OneBot API](https://napneko.github.io/onebot/api) and [OneBot 11](https://github.com/botuniverse/onebot-11/blob/master/api/public.md) define the adapter's provider-specific calls.

## Memory organization and automatic persona evolution

Memory → Automatic organization shows source coverage, durable stages and failures.
The default policy checks every three minutes, admits at most 16000 source characters,
and keeps eight complete recent turns in owner context. New owner dialogue takes
precedence. A previous plain REST choice cannot permanently suppress due maintenance.
No pending source means no model call. The main-chat heartbeat has its own schedule.

“整理 / 重试” queues the same service used by the loop; the returned run ID persists.
It can explicitly run with automatic maintenance paused, while subject admission,
mode/rest/fatigue, epoch and configured budgets remain authoritative. If the subject
is busy, the queued request waits. Failure retries back off 3/6/12/24/48/60 minutes,
capped at 60; the failed stage and error remain visible. A successful Recap commit
is not repeated when only persona reflection needs retry. No-change is a valid result.

Persona → Automatic evolution enables or pauses evidence-bound updates. Supported
fields are identity, relationship, dark, world and model-inferred user observations.
Redline, Mission, Dream, public group projection and the owner's USER section remain
manual. Observations are a separate editable field and are not confirmed biography.
Inspect old/new text and cited source content before deciding whether to correct it.
WORLD remains visible for inspection but is excluded from automatic model projection.
Automatic WORLD text is appended to its existing content under the same version check;
only an explicit owner edit replaces the whole field. An over-capacity merged field
is rejected without deleting the existing knowledge.
History “恢复到 vN” publishes a new revision; it does not delete history. New turns use
the new version, while resumed tasks retain their admitted persona/skill projection.

Recap clear marks existing cognitive sources cleared without erasing their raw evidence.
A model response based on the former Recap or owner epoch cannot republish stale state.
Failed publication leaves source coverage unchanged. Long sources carry exact offsets;
only the admitted prefix is covered, and the remaining suffix stays pending. If the
required raw context plus recent turns cannot fit, the request reports context overflow
rather than silently discarding it. Reduce the maintenance window or increase the
configured context capacity when appropriate. `window_chars` and `tail_turns` are
versioned policy fields available through POST `/api/cognition/policy`.

Migration is additive and runs under the subject lease. Existing pending legacy inputs
are imported; already-published excerpts are labeled legacy coverage and are not replayed
as whole history. Every startup also recovers still-pending unfinished owner turns, even after the
one-time migration marker exists, with an explicit failure label and no invented reply.
Task sources include confirmed tool content and the durable final model note; large
results have separate provenance-bearing slices. Old tasks predate the final-note field
and cannot retroactively supply a note that was never stored. Current
model-generated reflection notes use stable IDs and the memory outbox, but are not fed
back as new experience. MemPalace delivery status remains separate from local publication.

Before updating the running service, stop it and copy the **entire** data directory.
Keep the backup and run only one process for a subject. Start the existing test instance:

```powershell
.\.venv\Scripts\python.exe -m mysoul serve --port 8767 --data-dir .local/ui-redesign --local-test
```

The startup flag preserves tokenless local testing and the unlimited cumulative call
budget; saved provider limits remain separate. Host/Origin/CSRF checks stay active.
To recover a bad automatic persona change, prefer a history rollback. For storage
recovery, restore the stopped full-directory backup into a different directory and
inspect versions and pending runs before switching daily use to it. Do not delete or
hand-edit coverage, operation receipts, or unknown external-effect records.


## Unified chat and archive recovery

The main chat displays one conversation. “加载更早消息” reads50 older originals;
new messages and edits merge by stable identity/revision. Task execution, cancellation
and resume keep their existing card. The memory page's “分层历史” shows active
levels, compression receipts and paginated original evidence beneath each summary.
“压缩 / 重试” queues one bounded eligible batch; it does not override recency,
fatigue, admission or scope. Below all thresholds it correctly reports no work.

Defaults: L0 trigger100/batch70/protected8; upper trigger4/batch3, ceilingL8;
high/low capacity75%/55%; L1 cap4000 characters and higher levels6000.
Actual admitted batches can be smaller to fit request framing. Existing source records,
raw messages, archive children and retired versions remain in SQLite. Recap clear
invalidates saved publication while preserving historical originals. It does not erase
chat. A source correction invalidates affected ancestors and rebuilds raw frontier.

On failure inspect `/api/archives` or the memory page. A failed run retains its source
plan and retries after3/6/12/24/48/60 minutes; manual retry bypasses backoff. An owner
input, policy edit or Recap clear supersedes stale work. A crash after model generation
resumes the persisted result without another model call. Never hand-edit child links,
coverage, epoch or receipts. Use the stopped full-directory backup for recovery in a
separate directory; one subject lease prevents simultaneous writers.

Before activation on2026-10-23, the complete `.local/ui-redesign` directory was copied
while stopped to `.local/backups/unified-history-20261023-113750/ui-redesign` (17 files).
It contains the application SQLite database, LangGraph checkpoints, credentials and
local work products. Keep this local; do not add it to Git. Run the normal8767 command
above after restoring into an inspected separate directory. The migration is additive;
rolling back code alone is not a data restoration procedure.


The reviewed activation also has a newer full backup at
`.local/backups/unified-reviewed-20261023-115019/ui-redesign` with verified database
hash. Prefer this newer snapshot for post-migration recovery. The preserved original
pre-migration backup remains available separately. Detailed old facts can be recalled
through the existing Memory adapter and bounded source excerpts; the model does not
receive an entire archive's originals for one detail query.


Recap entries use `YYYY-MM-DD HH:mm:ss — 简短记忆描述`, with optional real location
and people inside the short event sentence. For example, sharing a toucan article
becomes “我和用户分享了巨嘴鸟的结构奇迹。” rather than a reproduction of article facts.
Internal experience IDs and hashes belong to source metadata, not Recap prose.
Unknown old event times must remain explicitly unknown, never replaced by the time
of consolidation. Original evidence retains full timestamp precision and provenance.
Existing Recap reformatting creates a version and must not advance pending coverage;
it uses the configured provider only with authorization for that private data and
its destination. The second-only display cleanup can run locally without inference.


## MemPalace local deployment and recovery (2026-10-23)

The memory page has **短期记忆** (versioned Recap, automatic organization and
local hierarchical history) and **长期记忆** (full upstream MemPalace semantic
retrieval of original evidence). Recap remains concise; the index retains original
text with source identity and audience isolation. Model context still follows the
same budget/permissions contract; a working index does not resolve a failed
hierarchical compression run or make model context unlimited.

Use a separate Python 3.12 environment for the full engine. The checked-in
`integrations/mempalace/runtime-dependencies.lock` records the tested Windows CPU
dependencies; mysoul's `uv.lock` remains independent. After cloning the official
repository and checking out the pinned revision above:

```powershell
uv venv --python 3.12 .local/mempalace-venv
uv pip install --python .local/mempalace-venv/Scripts/python.exe -r integrations/mempalace/runtime-dependencies.lock
uv pip install --python .local/mempalace-venv/Scripts/python.exe --no-deps .local/upstream-mempalace
```

Customize `integrations/mempalace/process.example.json` with absolute paths. Download
and warm the public embedding weights once, before admitting private originals.
The observed cache snapshot for `onnx-community/embeddinggemma-300m-ONNX` is
`5090578d9565bb06545b4552f76e6bc2c93e4a66`; retain this cache for reproduction.
A public-only warmup can omit `HF_HUB_OFFLINE` and call
`get_embedding_function(model="embeddinggemma")(["中文公共检索测试"])` from
`mempalace.embedding`. Then set `HF_HUB_OFFLINE=1`, disable telemetry as in the
example, and use that same cache. Actual memory embedding/search runs locally on
CPU (two threads); no external embedding API is configured.

For restart-persistent selection, put `memory.settings.json` in the subject data
directory alongside a customized `mempalace.process.json`:

```json
{"backend":"mempalace","process_config":"mempalace.process.json"}
```

Explicit `MYSOUL_MEMORY_BACKEND` / `MYSOUL_MEMPALACE_CONFIG` settings override this
file. The replay command remains explicitly offline. First real connection queues
all originals without a confirmed MemPalace mapping, including records previously
marked delivered by a local fixture. Subsequent starts preserve confirmed receipts;
retries use a stable source room to avoid duplicate or merged provenance.

`/api/status` exposes `memory.long_term`: actual protocol/operation health,
last successful operation, confirmed mappings, pending outbox count and model/source
revision. Connection health is an observation, not a fresh active probe or a release
gate receipt. A runtime failure returns HTTP503 for explicit search; local originals
and pending writes remain intact. If startup cannot establish the engine, inspect
its local configuration and restart with an explicit `MYSOUL_MEMORY_BACKEND=local`
for lexical-only recovery. Remove that override to restore semantic memory.

The actual test subject on port8767 uses `.local/ui-redesign/mempalace` and the
separate `.local/mempalace-venv` / `.local/mempalace-model-cache`. Before restoration,
stop the application and its owned stdio child, then copy the entire subject data
directory (including MemPalace palace/config/index identity, SQLite files and
receipts). Do not run two engines against the same index, replace just one database,
or point existing remote mappings at a new empty index. A new index requires an
explicit migration/replay preserving the old full directory until verified.

Activation backup: `.local/backups/before-mempalace-20261023-173815/ui-redesign`.
First synchronized-index backup:
`.local/backups/mempalace-first-sync-20261023-174811/ui-redesign` (235 remote
mappings; the subsequently discovered 123 legacy local-only records are requeued
at the next startup). Both are stopped full-directory snapshots. Public model
weights live outside them and must also be retained for offline recovery.


When upgrading an older shared-room adapter that already has real remote receipts,
identical originals may share one legacy drawer. This release prevents new collisions
but does not automatically rewrite confirmed old mappings; use the explicit full-index
migration/replay procedure above before relying on that old index's source provenance.
The activated subject had zero real mappings before this migration, so this legacy
case did not apply. The marked real tests always derive an index directory inside
pytest's temporary workspace; they never write into the configured subject index.
