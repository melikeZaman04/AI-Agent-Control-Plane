# Architect OS Architecture

Architect OS is a local-first control layer above coding agents. Its high-level direction is:

```text
USER
 |
 v
Architect CLI
 |
 +-- Project Chronicle
 +-- Context Compiler
 +-- Flight Recorder
 +-- Benchmark
 +-- Agent Adapter / Observer
        |
        +-- Claude
        +-- Codex
        +-- Gemini
        +-- Qwen
                |
                v
            Repository
```

M0 provides CLI and storage. M1 adds the normalized event contract, FlightRecorder, lifecycle updates, and CLI inspection. M2.1 adds the observer boundary. M2.2 adds opt-in CLI hook ingestion, validated by a real Claude smoke test documented in `integrations/claude.md`.

M1 stores the complete `ArchitectEvent` JSON in the existing events payload, preserving legacy rows without migration. Normalized timelines sort by UTC timestamp (microsecond precision), then SQLite insertion ID for ties. Legacy M0 payloads remain stored but are not presented as normalized evidence.

`FlightRecorder.record` persists lifecycle events and corresponding run updates atomically. Runs may be PENDING or RUNNING before reaching SUCCESS, FAILED, or CANCELLED. `run_finished` carries `metadata.run_status` with the terminal outcome; its event status must agree (success, failed, or blocked for cancellation). Terminal runs cannot restart or finish again. M0 `create_run` and `log_event` remain compatibility primitives; normalized lifecycle operations go through FlightRecorder.

## Ownership Boundary

Agents own their model conversations, native slash commands, code generation, native tool execution, sandboxes, permissions, and provider session behavior.

Architect owns run and normalized event history, the project timeline, context audit, project resume, daily summaries, explanations, benchmarks, and project-level engineering memory. It observes and coordinates agent-native behavior rather than reimplementing it.

## Observation Pipeline

```text
Claude / Codex / Other Agent
            |
            v
Provider Observer
            |
            v
Normalized Architect Event
            |
            v
Flight Recorder
            |
            v
SQLite / JSONL
            |
            v
Project Chronicle
```

Provider-specific event formats must not leak into the core storage model.

### Implemented M2.1 boundary

`Observer.normalize(payload, run_id=...)` returns normalized events without persistence. `ClaudeObserver` implements this contract using synthetic data only. `ingest(provider, payload, db_path=...)` resolves the session, calls the observer, then passes events to FlightRecorder. Recorder has no observer imports. The current observer emits zero or one event per payload; ingestion does not promise batch atomicity or retry deduplication.

The additive `provider_sessions` table has a composite primary key `(provider, provider_session_id)` and a foreign key to `runs.run_id`. Exact, case-sensitive identifiers are used. Repeated identical bindings succeed; conflicting bindings and absent runs fail. Existing runs/events are unchanged, and schema initialization is idempotent.

Synthetic payloads use `hook_event_name`, `session_id`, and a timezone-aware `timestamp`. Tool observations require `tool_name` and an object `tool_input`. Read uses `file_path`; Bash uses `command`. Direct `pytest`, `python -m pytest`, and `python3 -m pytest` commands without shell composition/expansion map to test_execution; other Bash commands map to tool_execution. PostToolUseFailure maps to failed tool_execution. PostToolUse alone does not prove test success. Unknown hooks/tools produce no event; malformed supported payloads raise ValueError. Ingest requires a known session even for ignored events.

SessionStart maps to run_started only with synthetic `run_scope="bound_run"` and `run_started=true`. Stop/SessionEnd map to run_finished only with the same run_scope and explicit `run_outcome` (SUCCESS/FAILED/CANCELLED). These are synthetic evidence fields, not claims about actual Claude hook fields. Session boundaries alone do not establish run completion.

Events carry provider="claude", fidelity="NATIVE", and metadata.synthetic=true. Provider event/tool names, session ID, hook source, tool inputs/responses and error details stay in metadata. NATIVE describes the modeled structured-provider path, not a live observation. Live payload schema validation belongs to M2.2.

## Observer Fidelity

M2.2 uses explicit live mode on the same observer/ingest boundary. The default Python
API preserves M2.1 synthetic behavior. `architect ingest claude` consumes native stdin
JSON, binds SessionStart using ARCHITECT_RUN_ID, and persists tool observations via
FlightRecorder. Receipt timestamps are labeled; session lifecycle is not converted
to run completion. Setup and detailed live semantics are canonical in
[`integrations/claude.md`](integrations/claude.md). No recorder or schema changes were
needed for live mode.

- NATIVE — provider-supported hooks or telemetry.
- SESSION_LOG — provider-local transcripts or session files.
- PASSIVE — Git, filesystem, and process output observations.

Architect must never claim visibility beyond the evidence available at the active fidelity level.

## Component Status

| Component | Status |
|---|---|
| CLI | IN PROGRESS |
| Storage | IN PROGRESS |
| Flight Recorder Core | COMPLETE |
| Observer Adapters | FOUNDATION AND LIVE CLAUDE COMPLETE; OTHER PROVIDERS PLANNED |
| Project Chronicle | PLANNED |
| Session Intelligence | PLANNED |
| Context Economy | PLANNED |
| NotebookLM Provider | PLANNED |
| Benchmark | PLANNED |
| LEARN Labs | PLANNED |
