# mysoul local operations

## Start and verify

Use the feature checkout shown in the delivery message. Python 3.12 and uv are required.

```powershell
uv sync --locked --extra dev
uv run python -m mysoul serve
```

Open the loopback URL printed by the command. Its fragment contains the local operator token; the browser removes it from the address after reading it. The token is retained in that tab's session storage. Private reads require the token; mutations additionally require the configured origin and a session CSRF nonce. Keep one process per data directory. No LAN/public binding is supported.

The default uses deterministic offline responses and fixture memory. It is useful for exercising state and review workflows; it does not perform general AI work. For a deterministic file-task demonstration, set `MYSOUL_MODEL_MODE=procedure-replay`. That fixture writes `report.txt`, and reads it back when the active skill contains `Procedure: verify`.

```powershell
uv run python -m mysoul replay --trace tests/fixtures/life_trace.jsonl --data-dir .local/replay-demo
uv run ruff check .
uv run pytest -m 'not live and not mempalace and not isolation' -q
uv run python scripts/fatigue_trace.py
```

`replay` forces offline phone, model and memory settings even if live variables exist. Environment variables are read explicitly; `.env` is not automatically loaded. Use `uv run --env-file .env ...` if desired. Never commit that file.

## Live setup gates

Each gate remains independent. Configuration or a skipped test is not validation.

| Capability | Configuration and verification |
| --- | --- |
| Model | Set `MYSOUL_MODEL_MODE=provider`, `MYSOUL_PROVIDER_URL`, raw `MYSOUL_MODEL`, and `MYSOUL_API_KEY`. Explicitly set `MYSOUL_VALIDATE_PROVIDER=1` to run the marked provider contract test. Credentials are not persisted. |
| Full MemPalace | Install full upstream dependencies in a separate Python environment at a pinned, reviewed checkout. Set `MYSOUL_MEMORY_BACKEND=mempalace` and `MYSOUL_MEMPALACE_CONFIG` to a local JSON process configuration. Run the marked Chinese write/search/get/restart test. No lightweight replacement satisfies this gate. |
| QQ | Verify the official NapCat deployment and version. Set `MYSOUL_PHONE_BACKEND=napcat`, endpoint/token variables, trusted owner ID, and comma-separated allowed group IDs. Group history polling is observe-only by default. No deployment, login, or live message was performed during development. |
| Code execution | Disabled. No isolation backend is implemented. Skipped isolation tests cannot enable execution. |
| News | Select trusted read-only sources before enabling live ingestion; fetched text remains untrusted data. |

The inspected MemPalace source revision is `f41e8e75ddaadf5588d5127715fa531d79eadb45`; it has not passed this project's real-engine gate. Its full Python engine declares Chroma and multilingual embedding dependencies. `embeddinggemma` is an upstream multilingual option; confirm available memory/disk and model download/privacy requirements before use. Record the actual revision/model and results after validation.

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

## Recovery and review

- **Stop autonomous sends:** stop the process, set `MYSOUL_SEND_ENABLED=false`, restart. Already dispatched requests may still finish remotely; inspect their receipts.
- **Unknown action:** inspect the effect record and remote history. Query receipts when supported. Never retry the same uncertain remote effect under a new action ID merely to clear uncertainty. If it cannot be resolved, retain unknown and abandon the dependent activity.
- **Interrupted work:** the UI exposes continue, replan and abandon. Continue retains the semantic cursor; replan starts a new execution thread with the same goal and retained evidence. Cancel is terminal, including across restart and late callbacks. Active tasks keep their pinned skill.
- **Recap conflict:** keep the editor contents, reload the committed version, and deliberately reconcile before resubmitting. Clear creates a new empty version and preserves raw evidence/history; it is not permanent erasure. Already admitted/in-flight data is not retrospectively wiped.
- **Memory unavailable:** the UI/context reports degraded recall. Local evidence and pending memory writes remain in SQLite. Restore the configured engine and restart; delivery uses stable evidence IDs. Do not change the embedding model in place.
- **Skill review:** select evidence, reflect or submit bounded Markdown, inspect the diff and objective tests, then explicitly approve the tested hash. Reject unsupported proposals. Rollback selects the default for subsequent work; historical task versions and evidence remain.
- **Budget exhausted:** stop before any new inference. Counters are durable per subject; change trusted limits through local environment configuration if justified. Provider reservations conservatively include prompt/schema bytes, output caps and configured attempts; they are not measured billing or tokenizer counts.
- **Backups:** stop the service, copy the entire data directory including both SQLite databases, skill revisions, token and memory directory. A stopped service avoids inconsistent cross-file snapshots. Restore into a separate directory, start one process there, and verify histories before returning to daily use. Retain the original backup.
- **Retention:** raw transcripts/evidence and Recap history are retained locally. Specify a separate targeted deletion policy before sustained live use; clearing Recap does not erase backend evidence or backups.

## References and notices

- [LangGraph checkpoint SQLite](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite) supplies graph persistence, not exactly-once remote effects.
- [MemPalace](https://github.com/MemPalace/mempalace) supplies the full memory engine. It is MIT licensed; preserve its notices and review dependency notices when packaging it. Its source and large dependencies are not vendored into mysoul.
- [NapCat OneBot API](https://napneko.github.io/onebot/api) and [OneBot 11](https://github.com/botuniverse/onebot-11/blob/master/api/public.md) define the adapter's provider-specific calls.
