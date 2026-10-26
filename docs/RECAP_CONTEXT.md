# Recap-based context continuity

Each new owner turn starts with runtime instructions, scoped persona, the current input/task and the committed Recap. Scoped Memory.search results are admitted only within the remaining context budget. Raw dialogue, pending Recap synthesis sources and the local archive frontier are no longer automatically injected.

The executor retains tool results and activity checkpoints throughout the current task, including interruption and restart recovery. A new ordinary chat turn creates a fresh context rather than copying a completed activity. Historical chat remains available in the timeline.

Recap evidence capture, scheduled synthesis, version checks and failure recovery retain their existing behavior and cadence. Until synthesis publishes, new raw experiences are not automatically visible in subsequent turns; relevant long-term recall can still supply evidence. MemPalace owns long-term storage and retrieval.

Legacy archive data and explicit inspection/compression APIs remain compatible. Idle scheduling no longer runs archive compression, and chat admission neither waits for archive compression nor persists archive-context demand. Existing archive data is retained without being wrapped around the memory backend.

The local character budget still applies to actual model input. Oversized required input or Recap remains an explicit error; optional retrieved evidence that does not fit is omitted. Private owner Recap remains excluded from group calls.
