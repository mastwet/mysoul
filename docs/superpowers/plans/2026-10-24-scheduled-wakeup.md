# Scheduled Wakeup Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this session with TDD and one final independent review.

**Goal:** Let the existing subject choose its next autonomous wake using one durable tool.
**Architecture:** Shared SQLite wakeup service and model runtime call; existing initiative loop consumes once; settings, reset and cancellation reconcile schedule; read-only voice projection.
**Tech Stack:** Existing Python3.12/uv/FastAPI/SQLite/HTML-JS.
**Spec:** docs/superpowers/specs/2026-10-24-scheduled-wakeup-design.md

## Constraints
Preserve unrelated changes and real data; local UTC storage/injected clock;30–86400s;one pending wake;no new permissions/channels;no private diagnostic replay.

## Review focus
Stale model calls after interruption;duplicate checkpoint replay;due while owner busy;restart/disable/reset;self-scheduling with exhausted budget/context.

- [x] RED/GREEN durable tool validation, replacement/idempotency, permission/epoch, task cancellation, restart and reset. Create wakeup.py and extend model contract compatibly.
- [x] RED/GREEN model tool roundtrip for owner/initiative/executor, bounded calls, acknowledgements and no cognitive/archive receipts. Integrate recall/service/executor.
- [x] RED/GREEN delayed and due wakes, owner priority and exactly one event, handling failures/restarts. Integrate autonomy/API/reset.
- [x] RED/GREEN read-only schedule display in inner voice and status; reuse existing page styles.
- [x] Full offline/UI/lint/build;fresh independent review;public synthetic gateway smoke if configured;backup/restart;browser verify without changing actual schedule;focused commit and validation record.

Validation: current tree382 passed/10 skipped; UI58. Independent index snapshot has five verified pre-existing HEAD context failures; new tests pass. Gateway public Hello503, so real-model acceptance remains pending. See docs/validation.md.
