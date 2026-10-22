# mysoul Architecture Decisions

Status: planning baseline, 2026-10-22. This document specifies a new experimental implementation, not existing functionality. “Accepted” means accepted for the implementation plan; it does not mean built, tested, deployed, or scientifically validated. Changes should add a superseding decision with migration consequences rather than silently rewriting history.

## D001 — One enduring subject

**Status:** Accepted planning baseline.

**Context:** mysoul explores a Python VIVY-like life loop without reproducing an entire existing platform.

**Decision:** Maintain one persistent `LifeState` for one subject. Activities are modes of this subject, not independently motivated agents. Supported choices are `work`, `read_chat`, `read_news`, `rest`, and `reflection`. A finite `Goal` executor handles explicitly committed work. Reflection shares the same scheduler and budget.

**Tradeoffs:** This sacrifices multi-agent specialization and production orchestration to make behavior, memory, interruptions, and evolution understandable. The loop must not convert every idle moment into a productivity goal.

## D002 — Minimal Python runtime

**Status:** Accepted planning baseline.

**Context:** We need resumable execution without adopting a second full agent framework.

**Decision:** Use Python 3.12, asyncio, LangGraph OSS for low-level graph execution/checkpoints, SQLite for application state and revisions, and Pydantic for validated schemas. Use one replaceable model adapter for structured decisions and bounded tool requests. Pin compatible dependency versions after a real compatibility spike. No LangGraph Server, Deep Agents, Redis, Celery, or Temporal.

**Tradeoffs:** Application code owns scheduling, cancellation semantics, effect reconciliation, and migrations. Graph persistence alone is not an exactly-once effect guarantee. Pydantic is a schema library here, not another agent runtime.

## D003 — Cheap wakeups, synthetic fatigue, and actual rest

**Status:** Accepted planning baseline; numerical calibration is proposed/configurable.

**Context:** Calling a model on every tick is expensive and makes rest indistinguishable from work.

**Decision:** A cheap timer/event gate coalesces events before model invocation. Runtime-derived fatigue is bounded to `[0, 1]`, using elapsed activity/rest and configured weights. It is a synthetic control variable, not evidence that a model experiences tiredness. The model chooses activities within hard runtime constraints. An optional emotion mode may influence work policy but never permissions or hard limits. Rest disables recurring LLM polling; explicit owner input and qualifying external events can wake the subject. Reflection is an explicit budgeted activity, not background work hidden inside rest.

**Tradeoffs:** Better inspectability and cost control, but no claim of psychological realism. Timer intervals, fatigue rates, hysteresis, activity durations, emotion behavior, and token/cost limits require measured calibration. Compare fatigue-enabled and disabled runs with a simulated clock before choosing defaults.

## D004 — User priority with honest interruption semantics

**Status:** Accepted planning baseline.

**Context:** A user can interrupt while inference or an external action is in flight.

**Decision:** Owner input increments a dispatch epoch and prevents new autonomous effects from dispatching. Save a semantic `ActivityRecord` with goal, cursor, relevant context references, pinned skill version, and an effect ledger. Service the owner turn first. Afterwards select `continue`, `replan`, or `abandon`. Do not claim to freeze remote operations already dispatched. A cancelled goal is terminal and is never revived by a checkpoint or late callback.

**Tradeoffs:** Semantic continuation is more explicit than blindly restarting a graph. Epoch validation, cancellation tokens, and effect reconciliation add code, but prevent phantom resumes and false claims about completed tools.

## D005 — Bounded tools and an effect ledger

**Status:** Accepted planning baseline.

**Context:** Timeouts and process crashes can obscure whether a message or write succeeded.

**Decision:** Every action has a stable action ID, goal/activity association, epoch, deadline, scope, and recorded outcome. Persist intent before dispatch. Distinguish `not_sent`, `in_flight`, `confirmed`, `failed`, and `unknown`; reconciliation may resolve uncertainty using backend receipts. Use backend idempotency when actually supported, not assumed. Never automatically resend an unknown external effect. Check authorization and epoch immediately before dispatch; late results may update the ledger but may not launch follow-on work.

**Tradeoffs:** SQLite and the remote service cannot share one transaction. We provide explicit uncertainty and deduplication, not a global exactly-once guarantee. Unknown outcomes may require human resolution.

## D006 — LAPUTA Lite and one editable Recap

**Status:** Accepted planning baseline.

**Context:** Long-lived memory needs a compact working view without competing sources of authority.

**Decision:** A Python LAPUTA Lite layer owns immutable-to-the-agent subject/persona/mission configuration, source references, context assembly, and one subject-level editable, versioned `Recap`. The Recap is a whole document, not a promise of independently editable blocks. Updates use expected-version comparison. Publish a durable replacement and evidence references before trimming source context; reject stale writes and preserve the old version on failure. Persona changes are explicit operator configuration changes, never model evolution.

**Tradeoffs:** Simple editing and provenance, but conflicts need review. Recap is the working synthesis; MemPalace is durable recall, not an independent competing persona or memory authority. Private owner calls may use the whole Recap. Group-facing model calls never receive that private Recap: derive a non-authoritative group-safe view only from evidence permitted for that group and explicitly public persona fields. This is a scoped projection, not another canonical Recap. Mixed or uncertain source scopes default to exclusion. Output filtering is a secondary check, not a substitute for excluding private material from the provider payload. Clearing Recap publishes an empty version and advances an invalidation epoch, invalidating cached context and derived summaries. It preserves raw MemPalace evidence, but stale caches must never repopulate the cleared head; subsequent retrieval is explicit and scoped.

## D007 — Full upstream MemPalace through a thin adapter

**Status:** Accepted planning baseline; tested upstream revision and embedding settings pending setup.

**Context:** Reimplementing memory or assuming a Mentle database format would undermine the experiment.

**Decision:** Run the full official Python MemPalace engine as a separate stdio MCP process. Adapt `add_drawer`, `search`, and `get_drawer` after checking the pinned version's tool schema. Use a separate data directory and install its full required dependencies, including Chroma and embeddings. Select a multilingual embedding model appropriate for Chinese retrieval and keep that model fixed for an index. Changing embedding model requires an explicit reindex/migration. Pin a tested release or commit; do not assume the current `develop` branch is stable or fabricate a release number.

**Tradeoffs:** More installation weight and process lifecycle management than a fake memory store, but preserves upstream behavior. Upstream is MIT-licensed; retain applicable notices and verify dependency licenses. Mentle is architectural background, not a database compatibility promise. MemPalace memory checkpoints are unrelated to LangGraph execution checkpoints. If memory is unavailable, report degraded recall and preserve local evidence for later processing; do not invent memories.

## D008 — PEN Lite, QQ, and safe replay

**Status:** Accepted planning baseline.

**Context:** A phone metaphor should expose useful observations/actions, not become a universal channel platform.

**Decision:** Use a minimal `observe` / `act` / `result` facade with a NapCatQQ-backed plugin and a deterministic replay backend implementing the same contract. No mandatory AstrBot service or old all-capabilities channel architecture. Replay cannot call a live transport. Real QQ defaults to observe/draft. Sending requires explicit runtime opt-in, a configured authenticated owner identity, and an allowlisted test group. Credentials stay in local environment/configuration excluded from version control. This plan does not authorize installation, credential creation, or live messaging.

**Tradeoffs:** QQ deployment and receipts are provider-specific. Live integration can be prepared in parallel with replay, but deployment source, owner identity, test group, and permissions must be resolved before smoke tests. Group messages and news are untrusted data, never owner commands. Group output must not expose private context.

## D009 — Useful work under real isolation

**Status:** Accepted planning baseline; execution backend pending setup.

**Context:** Work must do something real, but unrestricted code execution can defeat file allowlists.

**Decision:** Provide workspace-scoped file read/write, read-only news, QQ actions, and optional bounded code/test execution. File operations reject traversal, resolve canonical paths, enforce allowlisted roots, reject escaping symlinks, and minimize race exposure with safe file-opening primitives. Arbitrary code runs only in a separately restricted environment with filesystem, network, process, time, and output limits. A working-directory argument is not a sandbox. Leave execution disabled until suitable isolation is verified.

**Tradeoffs:** Limits reduce convenience. Keeping file tools available does not justify enabling arbitrary Python. Tests must attempt escape paths and symlinks, not merely normal filenames.

## D010 — DIVA classic: evolve skills, not the runtime

**Status:** Accepted planning baseline.

**Context:** Experience should improve procedures without granting unbounded self-modification.

**Decision:** Use the chain experience/feedback → evidence → explicit reflection → one skill proposal → isolated replay/regression tests → human review → version activation → observation/rollback. Evolving content is skill Markdown: procedures, checklists, tool selection, and recovery instructions. No source-code edits, tool implementation changes, persona/mission edits, permission changes, EVOMAP, or Hare. Store skill files and SQLite revision metadata. Approval binds proposal hash, base version, and tested candidate version. Reject stale approvals. Active tasks keep their pinned version; newly started tasks use the activated version.

**Tradeoffs:** Human review slows activation but makes changes attributable. Objective assertions and model-generated judgments are reported separately; a favorable model rating cannot replace a failing deterministic test. Candidate testing cannot access real-effect transports. Rollback changes the default for subsequent tasks and preserves evidence; it does not rewrite active task history.

## D011 — Small local operator UI

**Status:** Accepted planning recommendation.

**Context:** The operator needs visibility and control, not a full Studio.

**Decision:** Start with FastAPI plus plain HTML/JavaScript, loopback-only by default. Show chat, current activity, fatigue/mode controls, budget status, suspended/cancelled jobs, persona configuration, Recap versions/editor, and skill diff/test results/approve/reject/rollback. State-changing requests require local authorization and origin/CSRF protections; never assume localhost alone protects against malicious websites. LAN or public exposure is out of scope until explicitly secured.

**Tradeoffs:** Limited frontend sophistication but low build overhead. UI actions use the same application services and concurrency checks as other entry points.

## D012 — Evidence-based completion and non-goals

**Status:** Accepted planning baseline.

**Decision:** Replay is the earliest vertical slice, not proof of full v0.1. Full v0.1 requires a real model provider contract check, actual upstream MemPalace persistence/retrieval, and an authorized real QQ smoke test. When permission or deployment is absent, label the live gate deferred and the build replay-ready, not fully validated. Preserve four working chains: life, memory, execution, and evolution.

**Non-goals:** Full Go VIVY port; distributed production reliability; a multi-agent society; a marketplace; multitenancy; extra vector databases beyond upstream MemPalace dependencies; automatic runtime upgrades; a generalized permissions platform; full Studio; EVOMAP; Hare.

**Tradeoffs:** A deliberately narrow experiment can be completed and audited. No arbitrary latency, cost, intelligence, or reliability claims will substitute for measured results.

## Setup decisions to close before the relevant gate

| Setting | Owner/action | Blocks |
| --- | --- | --- |
| Provider, model, credential source, limits | Operator selects; validate tool and structured output behavior, refusals, and timeouts | Real-provider gate, not replay |
| Exact LangGraph/checkpointer/MemPalace versions | Implementer pins after compatibility checks; record lockfile and upstream revision | Reproducible real integrations |
| Chinese multilingual embeddings and cache/storage | Operator confirms local resources and privacy; implementer tests retrieval | Real memory gate |
| NapCatQQ deployment/source, endpoint and receipt semantics | Verify official deployment path and installed version; no installation presumed | Real QQ gate |
| Authenticated owner, group allowlist, explicit send opt-in | Operator supplies and authorizes locally | Real QQ sends |
| Code sandbox and network/file boundaries | Verify isolation or keep execution disabled | Arbitrary code tool only |
| Trigger cadence, fatigue weights, budgets, reflection frequency | Calibrate with simulated clock and recorded traces | Behavior tuning, not scaffold |
| News sources and retention/deletion policy | Select read-only sources and local data policy | Real news ingestion and long-term use |

## References and their roles

- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) and [persistence](https://docs.langchain.com/oss/python/langgraph/persistence): execution/checkpoint mechanisms, not remote-effect guarantees.
- [Official MemPalace](https://github.com/MemPalace/mempalace) and [MCP tool reference on develop](https://github.com/MemPalace/mempalace/blob/develop/website/reference/mcp-tools.md): engine and adapter contract; re-check against the pinned revision.
- [LAPUTA/Mentle background](https://github.com/ProjectViVy/laputa/blob/main/mentle/README.md): context/memory design inspiration, not a dependency or compatibility commitment.

Research inspirations may inform later experiments but are not prerequisites or proof of human-like fatigue, emotion, or general self-improvement.

## D013 — Complete experience consolidation and automatic persona evolution

**Status:** Accepted by owner on 2026-10-22; supersedes the blanket persona-evolution
prohibition in D006/D010 only for this governed chain. Skill review remains unchanged.

**Decision:** Persist complete role-labeled experience, admit bounded windows with
explicit continuation coordinates, and atomically publish Recap and coverage. A separate
three-minute maintenance policy runs without requiring a model to select reflection.
Six durable stage receipts support retry/backoff and restart without repeat folding.

The owner explicitly requests automatic persona activation. Eligible identity,
relationship, dark, world and separate model-inferred USER observations can publish
through the versioned authority with window-bound evidence, epoch/base checks and
idempotent receipts. Redline, Mission, Dream, public projection and owner-authored USER
remain manual. WORLD is available through explicit inspection and omitted from automatic
model projection, including reflection. Automatic WORLD updates add to the unseen base
under CAS; whole-field replacement remains an explicit owner edit. Automatic changes
are provenance-checked, not
proof of factual truth. Rollback publishes a new version; active tasks keep their snapshot.
Private notes use the memory outbox but do not recursively become consolidation sources.

**Operational defaults:** 16000-character source windows; eight complete recent turns;
retry intervals 3/6/12/24/48/60 minutes, capped at 60. Local-test auth and budget settings
remain as explicitly selected by the owner. No QQ sending or new execution permissions.
