# Native Palace Browser Implementation Plan

**Goal:** Add the selected read-only native structure browser, drawer details and diagnostics.
**Spec:** `docs/research/mempalace-management-2026-10-23.md`, option A selected by the user.
**Architecture:** Operator-only API translates real MCP responses into explicit browser data. A standalone browser module owns selection, pagination, details and request ordering. Existing evidence ingestion and model tools stay unchanged.
**Tech stack:** Existing Python/FastAPI/MCP, vanilla JavaScript modules and CSS.

## Constraints and decisions

- Reuse the existing implementation worktree; preserve other edits and do not commit unrelated work.
- Read only: no migration, move, edit or delete operations.
- Native taxonomy counts are stored chunks; list totals are logical drawers.
- Global inspection requires existing operator authorization and is never exposed as a model tool.
- Render untrusted text with textContent. Unknown drawers and unavailable engines show retryable errors.
- Keep the last committed list and its filters together on failed requests; discard stale list/detail responses.
- Approved option A is the implementation scope; execute here without another scope confirmation.

## Tasks

- [x] 1. Write failing backend tests for native taxonomy/list/detail, source mapping, capability errors, malformed responses, auth and input validation. Implement `PalaceInspector` and guarded GET routes `/api/memory/palace`, `/api/memory/palace/drawers`, `/api/memory/palace/drawer`.
- [x] 2. Write browser tests for selection/paging/details, plain-text rendering, stale responses and retry. Implement `palace.mjs`, lazy activation from the long-term tab, accessible filter/list/detail layout and responsive CSS. Register module route and update the existing UI test harness import.
- [x] 3. Run focused backend/UI regression tests, lint and an isolated real-engine list/detail contract. Inspect desktop and mobile renderings. Activate the tested application when the current instance is idle and verify live read-only endpoints.

## Review focus

Missing MCP tools must not look like an empty palace; failed refresh must not show old results under new filters; logical drawers must not be counted as chunks; native text must not execute HTML; global management reads must retain operator authorization.

## Execution record

Initial inspection: current server connected to pinned full MCP engine. Read-only index snapshot: 1 wing, 439 rooms, 439 logical drawers, 669 physical rows. Shared worktree contains unrelated edits.

Completed 2026-10-23: focused backend/API suite 21 passed (two pre-existing live cases deselected); native palace test module with real isolated engine 4 passed. Browser regression suite 39 passed. Ruff and git diff --check passed. Independent review found two asynchronous navigation issues; both reproduced with failing tests, fixed, and independently rechecked. Live server restarted with its original flags after verifying rest/idle, then native overview/list/detail returned ready and exact source match. Live snapshot: 1 wing, 488 rooms, 488 logical drawers, 718 physical chunks, no pending synchronization. Original content and categorization were not changed by this feature. The running companion continues its own normal writes.

Visual checks: default desktop viewport and 390×844 narrow viewport. No horizontal overflow at 390px, original detail opens into view, native diagnostic panel works, browser error log empty. Screenshot: `C:/Users/Administrator/Desktop/mysoul/.local/native-palace/native-palace-final.png`.

Testing note: temporary jsdom 26.1.0 dependency installed under the Desktop task's `.local/native-palace/deps`; the loader in that directory resolves it for existing node:test files. No runtime dependency added. Full unrelated repository test suite was not run. No commits or unrelated edits were included.
