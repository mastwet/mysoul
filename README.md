# mysoul

An experimental, single-subject Python companion inspired by Project VIVY: autonomous life, persistent memory, bounded work, and reviewed skill evolution.

## Status

The local offline implementation is available: durable life state, finite LangGraph tasks,
source-scoped Recap/memory, replay and NapCat adapters, bounded file work, reviewed skill
evolution, and a local operator UI. Real provider, full MemPalace and authorized QQ
acceptance remain pending. Arbitrary code execution is disabled.

Life choices now dispatch bounded activities; new evidence can update Recap during
explicit reflection, and execution feedback can produce a reviewable skill proposal.
Candidate tests compare base/candidate artifacts using an isolated fixture or the
configured model. Skills still require operator approval before activation.

```powershell
uv sync --locked --extra dev
uv run python -m mysoul serve
```

For local testing without an operator token or a cumulative model-call ceiling:

```powershell
uv run python -m mysoul serve --local-test
```

This opens the loopback UI directly. Origin/CSRF checks and per-task execution
bounds remain active. Token/output settings are configured separately in the UI.
Use the same flag on subsequent launches; omit it to restore default token access
and the default call budget. Existing counters and conversations are retained.

Open the local access URL printed by the command. Defaults use deterministic replay;
no credentials or QQ account are needed. See [operations and recovery](docs/runbook.md)
for a file-work demonstration, real integration setup and recovery procedures.

Configure a real model under **设置 → 模型服务**: base API URL, model ID and API key.
The local operator token only unlocks the UI. Test the connection, then save and
activate the configuration; keys are never returned by the API. See the runbook
for local secret storage and restart behavior.

```powershell
uv run python -m mysoul replay --trace tests/fixtures/life_trace.jsonl --data-dir .local/replay-demo
uv run ruff check .
uv run pytest -m 'not live and not mempalace and not isolation' -q
```

## Design and verification

- [Implementation plan](docs/PLAN.md): architecture contracts, dependency order, implementation tasks, test gates, and operational setup.
- [Architecture decisions](docs/DECISIONS.md): choices, tradeoffs, scope boundaries, and settings to validate.
- [Validation record](docs/validation.md): actual tests, browser walkthrough and pending gates.
- [Independent review](docs/review.md): findings, regression fixes and verification limits.
- [Paired fatigue trace](docs/fatigue-comparison.json): measured synthetic scheduling comparison.

The planned stack is Python, LangGraph OSS, SQLite, a thin LAPUTA layer, upstream MemPalace, and a PEN-style interface with NapCatQQ and replay backends. Skill evolution follows evidence, reflection, isolated tests, human review, activation, and rollback.

Real provider, MemPalace, and authorized QQ checks have separate validation gates.
The plans and offline tests do not authorize deployment, account configuration or live messages.
