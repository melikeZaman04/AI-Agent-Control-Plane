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
Architect run ID. Live validation confirmed a stable identifier across tool
and approval records in each tested native session (evidence below).

The implementation follows the official OpenAI documentation for
[Codex observability and telemetry](https://developers.openai.com/codex/config-file/config-advanced/#observability-and-telemetry)
and the [configuration reference](https://developers.openai.com/codex/config-file/config-reference/).
OTel export is opt-in, supports OTLP/HTTP and OTLP/gRPC, is batched, and keeps
raw prompt logging disabled unless explicitly enabled.

## M2.3b — live binary transport (COMPLETE)

The M2.3a proposal for JSON was superseded by the approved binary configuration
and verified live traffic. `opentelemetry-proto` supplies the generated
`ExportLogsServiceRequest` / `ExportLogsServiceResponse` messages; its transitive
`protobuf` runtime handles decoding. No handwritten protobuf parser, SDK,
Collector, gRPC, traces, metrics, or background service is added.

`architect codex-listen --run <full-id-or-unique-prefix>` accepts only
`127.0.0.1` (default port 14318). It checks the existing project database and run
before opening the socket, rejects ambiguous IDs, prints the endpoint and
resolved run, and closes on Ctrl+C with recorded/ignored/rejected counts.
The current working directory selects the project; payload paths never do.

Each listener binds all supported records to exactly one existing Architect
run. A provided `conversation.id` is preserved and bound using `provider_sessions`;
conflicts are rejected. Without it, the explicit run is sufficient and no
session identity is invented. Concurrent multi-session routing is out of scope:
only point the intended Codex process at the listener.

Decoding traverses resource logs, scope logs, and log records. Scalar resource
attributes are merged with log attributes (log wins); `event.name` identifies
the event, with the OTLP event-name/body string as fallback. The native OTLP
timestamp (or observed timestamp) is converted to UTC microseconds. Supported
records without either timestamp are rejected, not stamped with invented time.
CodexObserver owns all normalization; FlightRecorder owns event persistence.
The older stdin `architect ingest codex` path remains unsupported; use the
explicit listener instead.

### Verified shape and privacy

Codex 0.154.0-alpha.6.1 emitted `event.name`, `conversation.id`, `tool_name`,
`call_id`, `app.version`, and `model`. Tool results supplied **string**
`success="true"` and `duration_ms="53"`; approvals supplied `decision="approved"`.
M2.3a assumed boolean success and numeric duration. Only live mode now also
accepts exact `"true"` / `"false"` and numeric duration strings; finite,
nonnegative duration validation still applies. Synthetic behavior is unchanged.

Live metadata is allowlisted to `conversation.id`, `tool_name`, `success`,
`duration_ms`, `decision`, `decision_source`, `call_id`, `model`, `app.version`.
Prompt, arguments, command, output, account/email, auth, and arbitrary unknown
or nested fields are not persisted. Raw requests are not logged. Export may
still contain sensitive output even with prompt capture off: use a harmless
project and trust local processes. The allowlist is not a secret scanner and
the loopback endpoint has no authentication; do not expose it through a proxy.

Live tool results become TOOL_EXECUTION; without retaining/parsing command
arguments we do not infer TEST_EXECUTION or FILE_READ. Provider success is tool
success, not necessarily proof of passing tests. Codex emitted both `exec` and
`exec_command` tool results with different call IDs; both are retained as native
observations, not claimed to be separate user actions. Approval observations do
not establish that a human was prompted. No run completion is inferred:
`architect status` can correctly remain RUNNING after the listener stops.

### HTTP limits and acknowledgements

- Only POST `/v1/logs`, `application/x-protobuf`, uncompressed Content-Length
  requests; no chunked transfer. Body limit 1 MiB, at most 2048 log records,
  five-second socket I/O timeout, synchronous foreground handling.
- Valid/unknown records: HTTP 200 protobuf acknowledgement; unknown event
  families increment ignored without fabricating events.
- Invalid supported records/session conflicts: HTTP 200 protobuf partial
  success with rejected count and a generic message, while valid siblings persist.
- Malformed protobuf/envelope: 400; wrong route: 404; GET: 405; missing/invalid
  length: 411; oversized body: 413; unsupported media/encoding: 415;
  socket timeout: 408; storage failure: 503.
- No batch atomicity, retry deduplication, guaranteed delivery, or shutdown
  recovery. Keep the receiver open until Codex exits and flushes its batch.
  Ctrl+C stops receiving; later exports can be lost. HTTP retries after partial
  storage failure can duplicate already persisted observations.

## Repeatable fish-shell live smoke

Install the new dependency from the repository first. Never overwrite your
existing Codex configuration. The following settings are supported by the
[official OpenAI documentation](https://learn.chatgpt.com/docs/config-file/config-advanced).

For a persistent opt-in, manually merge (do not duplicate existing tables) into
Linux `~/.codex/config.toml`, then restart Codex:

```toml
[otel]
log_user_prompt = false
environment = "architect-smoke"

[otel.exporter.otlp-http]
endpoint = "http://127.0.0.1:14318/v1/logs"
protocol = "binary"
```

After testing, restore the previous telemetry settings, or remove the
`[otel.exporter.otlp-http]` table and set `exporter = "none"` inside `[otel]`.
Do not leave both exporter forms. Restart Codex after the change. Architect
never edits this file. The invocation-only override below needs no config edit.

### Terminal 1 — temporary project and foreground receiver

```fish
cd "/home/melikezaman/Desktop/AI Agent Control Plane"
source .venv/bin/activate.fish
python -m pip install -e '.[dev]'
set -gx architect_repo (pwd)
set -gx smoke_dir (mktemp -d /tmp/architect-codex-smoke.XXXXXX)
cp "$architect_repo/docs/integrations/smoke/README.md" "$smoke_dir/README.md"
cp "$architect_repo/docs/integrations/smoke/test_smoke.py" "$smoke_dir/test_smoke.py"
cd "$smoke_dir"
architect init
architect run "Codex live telemetry smoke test" --agent codex --fidelity NATIVE
read -P 'Paste the Run ID printed above: ' run_id
echo "Terminal 2 project: $smoke_dir"
architect codex-listen --run "$run_id" --host 127.0.0.1 --port 14318
```

### Terminal 2 — real Codex activity

Paste Terminal 1's temporary project path at the prompt. This exact command
uses invocation-only configuration, so no global config edit is necessary:

```fish
set -gx architect_repo "/home/melikezaman/Desktop/AI Agent Control Plane"
source "$architect_repo/.venv/bin/activate.fish"
read -P 'Paste Terminal 1 temporary project path: ' smoke_dir
cd "$smoke_dir"
codex exec --ephemeral --skip-git-repo-check --sandbox read-only \
  -c 'otel.log_user_prompt=false' \
  -c 'otel.environment="architect-smoke"' \
  -c 'otel.exporter={otlp-http={endpoint="http://127.0.0.1:14318/v1/logs",protocol="binary"}}' \
  'Read README.md using your available file/shell tool, then run PYTHONDONTWRITEBYTECODE=1 "/home/melikezaman/Desktop/AI Agent Control Plane/.venv/bin/python" -m pytest -q -s -p no:cacheprovider test_smoke.py. Do not edit files or delegate.'
```

Alternatively, after manually merging the config block, start `codex` normally
in this temporary project and give the same task; trust only this known folder.
If `codex` is unavailable, use the installed Codex executable's full path.
The `-s` and cache/bytecode settings avoid pytest writes in the read-only smoke
environment. No Git init is required; the temporary project is not a Git repo.

### Terminal 1 — inspect after Codex exits

Wait for Terminal 2 to finish (export is batched), then press Ctrl+C in Terminal 1:

```fish
architect inspect "$run_id"
architect status
cd "$architect_repo"
git status
```

Expect at least one NATIVE TOOL_EXECUTION or APPROVAL_REQUESTED with
`synthetic: false`. An empty timeline is not acceptance: check endpoint/port,
listener counters, configuration, and that the process exited to flush telemetry.
Keep the temporary database until evidence is no longer needed. Runtime data
is not a Git checkpoint; commit source changes separately from the repository.

## Executed acceptance evidence

Validated on 2026-09-14 UTC (2026-09-15 Europe/Istanbul), installed Codex
`0.154.0-alpha.6.1`, in `/tmp/architect-codex-smoke.gwhCYz`. No Architect source
was edited by the smoke agent, no global Codex configuration was changed, and
`log_user_prompt=false` was used throughout via invocation overrides.

- Architect run: `a27bbb96-c74e-4de2-833d-950899ab42ea`.
- Final native session: `01a0a1f5-7e11-7ae2-849b-861ba407012a`, stable across
  all six accepted final-test records and bound to that run.
- Final receiver: `architect codex-listen --run a27bbb96 --port 14320`.
  Invocation override used the matching `http://127.0.0.1:14320/v1/logs`;
  the documented default remains 14318. The earlier diagnostic listener was
  stopped after validation.
- Real README read and pytest execution completed; smoke pytest: `1 passed in 0.00s`.
- Final receiver Ctrl+C summary: `Recorded: 6; ignored: 22; rejected: 0`.
- `architect inspect a27bbb96` showed APPROVAL_REQUESTED at
  `2026-09-14T22:06:59.632036+00:00`, TOOL_EXECUTION at
  `2026-09-14T22:06:59.676993+00:00`, and subsequent tool/approval observations.
  Metadata showed provider session, native tool names, `synthetic=false`;
  the run and persisted events have NATIVE fidelity.
- Earlier attempts recorded approval events but rejected tool results because
  of string-valued success/duration. This discrepancy was diagnosed from field
  types, fixed only in live normalization, and covered by binary fixture tests.
  The initial pytest command also failed because capture needed temporary files;
  the final read-only-safe command above passed. Earlier observations remain
  in the same temporary run; the six-record count refers only to the final test.
- Automated regression/transport suite: `136 passed in 0.74s`.

M2.3b meets live acceptance and is COMPLETE. M2.4 has not been started.
