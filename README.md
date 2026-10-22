# mysoul

An experimental, single-subject Python companion inspired by Project VIVY: autonomous life, persistent memory, bounded work, and reviewed skill evolution.

## Status

Planning only. No application implementation, installation, live integration, or test pass is claimed yet.

## Planning documents

- [Implementation plan](docs/PLAN.md): architecture contracts, dependency order, implementation tasks, test gates, and operational setup.
- [Architecture decisions](docs/DECISIONS.md): choices, tradeoffs, scope boundaries, and settings to validate.

The planned stack is Python, LangGraph OSS, SQLite, a thin LAPUTA layer, upstream MemPalace, and a PEN-style interface with NapCatQQ and replay backends. Skill evolution follows evidence, reflection, isolated tests, human review, activation, and rollback.

Start with the offline scaffold and replay lane. Real provider, MemPalace, and authorized QQ checks have separate validation gates. Do not treat this repository or its plans as permission to deploy, configure credentials, or send live messages.
