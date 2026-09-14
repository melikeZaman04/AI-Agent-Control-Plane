# Codex telemetry integration

## M2.3a normalized boundary

M2.3a implements synthetic normalization only. It does not configure Codex or
receive live OTLP traffic. The input fixture is a narrow representation with
`event_name`, a timezone-aware `timestamp`, and an `attributes` object. This is
an Architect test boundary, not a complete OTLP wire schema.

Supported mappings:

- `codex.tool_result` → `tool_execution`, or `test_execution` for a direct,
  deterministically identifiable pytest command. Provider-reported `success`
  determines normalized success or failure.
- `codex.tool_decision` → `approval_requested`. The provider decision remains
  in metadata; approval maps to success and denial/abort to blocked.
- MCP calls represented by tool results remain `tool_execution`; MCP identity
  remains provider metadata.

Other Codex event families are ignored. In particular, `codex.user_prompt` is
not ingested. Prompt capture is unnecessary for Flight Recorder operation and
Codex prompt export should remain disabled. Attribute names containing prompt,
content, output, token, credentials, or secrets are omitted from normalized
metadata. This is a conservative boundary, not secret detection.

Events use provider `codex` and fidelity `NATIVE`. The documented
`conversation.id` binds to an existing Architect run through the existing
`provider_sessions` table under provider `codex`. It never becomes the
Architect run ID. Live validation must confirm that the identifier remains
stable across exported records before M2.3b is complete.

The implementation follows the official OpenAI documentation for
[Codex observability and telemetry](https://developers.openai.com/codex/config-file/config-advanced/#observability-and-telemetry)
and the [configuration reference](https://developers.openai.com/codex/config-file/config-reference/).
OTel export is opt-in, supports OTLP/HTTP and OTLP/gRPC, is batched, and keeps
raw prompt logging disabled unless explicitly enabled.

## M2.3b transport decision

| Option | Dependencies and complexity | Local operation | Fidelity and testing | Operational burden |
|---|---|---|---|---|
| A. Architect-local OTLP/HTTP receiver | Small receiver plus correct OTLP JSON envelope validation; no protobuf needed when Codex uses HTTP JSON | Bind loopback and write directly to the existing ingest boundary | Native log fidelity; isolated HTTP fixtures are straightforward | Architect must own listener lifecycle, limits, error handling, and shutdown flushing |
| B. OpenTelemetry Collector | External binary and collector configuration; standard OTLP handling | Local-compatible but adds another process | Highest protocol maturity and easy forwarding | Installation, versioning, configuration, and process management are heavy for the current milestone |
| C. Another Codex export path | No documented alternative currently provides equivalent tool-result and approval log coverage | Unknown | Cannot validate equivalent fidelity | Depends on an interface that is not established |

Recommendation for M2.3b: a minimal loopback-only OTLP/HTTP JSON receiver,
explicitly started for one project/run and limited to `/v1/logs`. Codex already
documents OTLP/HTTP with JSON protocol. The receiver should translate only the
supported Codex log records and reuse session binding, CodexObserver, and
FlightRecorder. It must define request-size limits, deterministic errors,
graceful shutdown, and a smoke workflow before implementation. Do not add a
collector, gRPC/protobuf stack, daemon, or global Codex configuration.

Open question for M2.3b: confirm the live OTLP JSON envelope and exact per-event
attribute keys, including `conversation.id`, using an opt-in temporary project.
