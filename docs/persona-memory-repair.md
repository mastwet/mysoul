# Persona, memory and model admission repair

This repair addresses three operator reports: the subject had no editable
personality system, recall did not preserve reliable dialogue continuity, and
long provider calls were reported as `Model unavailable`.

## Delivered

- Added an operator-owned, eight-section persona profile with a separate public
  projection, SQLite revision history and compare-and-swap updates. Group model
  context receives only the public projection; owner-only instructions stay in
  private conversations. Existing public persona configuration is migrated.
- Added paired owner/assistant conversation history, safe backfill of successful
  local replies, and durable assistant-reply evidence. Local lexical recall now
  uses the query and labels generated stories as generated content. The memory
  page exposes search, evidence counts and the active backend. MemPalace remains
  unconfigured; queued evidence is retained locally and is not represented as
  synchronized.
- Made the application context character budget and provider timeout editable
  and persistent. The defaults are 131,072 characters and 120 seconds, with
  bounded settings. Successful replies can exceed the former 4,000-character
  ceiling. Provider failures have safe categories for timeout, context limit,
  authentication, rate limit, connection and other response errors.
- Updated the UI with persona editing/version history, memory search and status,
  model context/timeout controls, and actionable chat errors that retain the
  draft without automatic resend.
- Promoted the persona editor to its own left-sidebar page so it is reachable
  without opening Settings.
- Prevented a completed owner chat answer from also being dispatched as a second
  background work goal.

## Verification

- Offline Python suite: 172 passed, 8 skipped.
- UI Node suite: 17 passed.
- Ruff and JavaScript syntax checks passed.
- The saved local OpenAI-compatible provider completed a long continuation of
  the existing “停云” story in about 45 seconds. Its answer continued the stored
  plot; identity and local memory search were also exercised against the app.
- The recap was reviewed and republished with explicit fiction provenance and
  no inferred owner biography. Previous recap versions and source evidence were
  retained.

## Remaining external gate

This is an offline/local-provider repair, not a claim that all T01–T10 real
integrations are complete. MemPalace persistence/retrieval and live QQ remain
separate validation gates. Current memory operation is durable local lexical
search; it does not provide MemPalace semantic retrieval.
