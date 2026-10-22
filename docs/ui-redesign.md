# Conversation workspace redesign — 2026-10-22

The operator's primary task is conversation. This revision replaces the dashboard
with a quiet conversation workspace: collapsible navigation, a centered message
column, a bottom composer, and a small top-right fatigue/activity card. Tasks,
memory and skill review remain real views of the existing application services.
The recent list navigates actual messages in the single subject's history.

Settings are grouped into appearance/input, subject state, public persona, and
connections/budgets. Light, dark and system appearance plus send-key preference
persist in this browser. Subject/persona changes use the authenticated application
API. Fatigue uses percentages in the UI and the existing 0–1 API contract. Budget
limits are exposed read-only; credentials and permissions remain outside the UI.

Messages use a pinned local Markdown parser, with raw HTML disabled, safe link
protocols, noreferrer/noopener on external links, and images rendered as alternative
text without fetching remote resources. Vendor files are packaged locally, with no
CDN/runtime package download. CSP, bearer, Origin and CSRF protection are retained.

## Validation

- Before implementation, browser probes confirmed settings, fatigue details and
  task navigation were missing. The budget-limit API test failed before the field
  was added. Node message-policy tests failed before the conversation module existed.
- `uv run pytest -q`: 130 passed, 8 existing explicit live/isolation skips.
- `node --test tests/ui/conversation.test.mjs`: 4 passed. Covers Markdown structure,
  raw HTML/dangerous URLs, no remote image requests and IME/send-key distinctions.
- Ruff, JavaScript syntax and wheel build passed.
- Real browser walkthrough on the loopback replay service: desktop and 390×844;
  fatigue status detail, grouped settings, theme selection, subject-state save,
  mobile navigation/modal focus return, budget readings, Shift+Enter newline,
  Enter submission, pending state and exactly one final visible message.
- Screenshots: `assets/chat-ui-desktop.png`, `assets/chat-ui-mobile.png`.
- No live model, MemPalace or QQ call was made for this UI revision.

## Third-party notice

`src/mysoul/web/vendor/markdown-it.min.js` is the unmodified browser distribution
from the npm registry package `markdown-it@14.1.0`, MIT licensed. Its license is
preserved beside it as `markdown-it.LICENSE`. Upstream:
https://github.com/markdown-it/markdown-it/tree/14.1.0

SHA-256: `38c70a1e7ca91ab40e2d9e6e60129851a717ed1c7d4acbbdd41bf9503791cf68`.
