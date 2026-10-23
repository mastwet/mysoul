# Conversation Reset Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement in this session with TDD.

**Goal:** Settings can archive current chat and start an empty short-term conversation.
**Architecture:** Atomic SQLite boundary and Recap revision; version-aware timeline and browser reconciliation.
**Tech Stack:** Existing Python 3.12, FastAPI, SQLite and HTML/JS.
**Spec:** docs/superpowers/specs/2026-10-23-conversation-reset-design.md

## Constraints
Preserve persona, evidence, MemPalace index, credentials, budgets and unrelated working changes. Never reset actual user data during verification. Reuse authorization/Origin/CSRF.

## Review focus
Late model results; pending task restoration; repeated stale reset; restart; late browser polling.

- [x] Backend RED: reset preserves originals, long-term memory and persona; rejects stale revision/unauthorized calls; survives restart and blocks stale cognitive capture.
- [x] Implement conversation service and timeline/context boundary. Include read-only archive pagination/export.
- [x] UI RED: settings confirmation, cancellation, successful reset, failure preservation and late responses. Implement version-aware browser state and archive download.
- [x] Run targeted then full checks, independent review, backup/deploy, browser inspect without performing real reset, focused commit.

## Evidence and rulings

363 offline tests passed /10 external checks skipped;57 UI tests passed;Ruff, JS syntax, offline build and diff checks passed. Fresh review found three P2 issues: Recap actions hidden after reset, stale Recap on refresh failure, and archived failed-task feedback regeneration. All were reproduced RED and repaired GREEN; no deferred findings. Actual service was backed up and restarted; only confirmation/cancellation was inspected in browser. Current revision remains0 and existing MemPalace Chinese query returned1 record.

Ruling: reuse existing settings layout and add read-only last-archive download; preserve raw historical originals rather than hard-delete. User approved reset scope in conversation. Other pending Recap-only/native palace browser work is preserved and excluded from this feature commit.
