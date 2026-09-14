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

M2.3a adds `CodexObserver` behind the same Observer protocol. It accepts only a
narrow synthetic OTel-style record and maps documented tool-result and
tool-decision families to the existing ArchitectEvent vocabulary. Codex-specific
attributes remain metadata, sensitive content fields are omitted, and
FlightRecorder has no Codex dependency. `conversation.id` uses the existing
provider-session binding under the `codex` namespace.

M2.3b adds a foreground binary OTLP/HTTP logs receiver. It decodes provider
records, invokes the same CodexObserver in live mode, safely binds a provided
native session to the explicitly selected run, and persists only through
FlightRecorder. The receiver owns transport and listener/run correlation;
the observer owns event mapping and metadata filtering. No schema or recorder
changes are needed. Protocol limits, privacy, and verified live evidence are
canonical in [`integrations/codex.md`](integrations/codex.md).

- NATIVE — provider-supported hooks or telemetry.
- SESSION_LOG — provider-local transcripts or session files.
- PASSIVE — Git, filesystem, and process output observations.

Architect must never claim visibility beyond the evidence available at the active fidelity level.

## M3.1 — Project Chronicle Foundation

`architect.chronicle.ProjectChronicle(db_path).query(project_id, run_id=None)`
derives one immutable `ChronicleEpisode` per selected run. `run_id`, when supplied,
is exact; an absent run returns an empty list. The database must already exist
and contain exactly one registered project matching `project_id`. This preserves
the existing project-local ownership model without guessing ownership in shared
databases. Unknown project IDs and ambiguous ownership raise `ValueError`.

Queries use a single SQLite read transaction in read-only mode. No tables,
migrations, runtime dependencies, CLI commands or background processing are
added. Re-querying rebuilds the derived state. The stable episode identity is
database-scoped `run:<project_id>:<full_run_id>`. New observations update that
episode on the next query without creating another episode. Design rationale:
[`ADR-004`](adr/ADR-004-chronicle-foundation.md).

Episode `project_id`/`project_root` reference the projects row. `run_id` references
the runs row, which is the source for `run_status`, `began_at` and `ended_at`.
Times are UTC with microseconds; legacy SQLite CURRENT_TIMESTAMP values are
UTC. Unknown start/end times remain null. Pending/empty runs still produce an
episode with no event facts. Neither latest event time nor successful tool
execution establishes run completion.

Facts group normalized events by `(event_type, status, provider, fidelity)` with
an observation count and supporting `evidence_event_ids`. These IDs are
ArchitectEvent IDs in the original events payloads, not SQLite insertion IDs.
Every fact's evidence resolves through FlightRecorder or the original SQLite
payload. Provider/fidelity/status remain null if absent; run defaults are never
substituted. Provider metadata (including synthetic/live labels) stays available
on source events. Successful tools are not promoted to successful tests, and
arbitrary metadata is not interpreted or copied into Chronicle.

Episodes sort by begin time, unknown starts last, then full run ID. Evidence
uses FlightRecorder ordering (UTC timestamp then SQLite insertion ID); fact
groups follow first supporting observation order. Stable JSON includes counts.
The shared `normalized_timeline` decoder preserves the existing recorder
contract: legacy payloads are skipped; invalid normalized envelopes fail.
Chronicle additionally rejects mismatched run IDs and duplicate evidence IDs
within a run. It never repairs or deletes original evidence.

M3.1 provides structured history only. Narrative summaries, richer change or
decision analysis, persistent annotations, `/day`, `/resume`, `/changes` and
`/explain` remain outside this foundation. Acceptance evidence is in
[`milestones/M3.1.md`](milestones/M3.1.md).

## M3.2 — Chronicle CLI and evidence inspection

`architect chronicle [--run FULL_RUN_ID] [--json]` adapts the M3.1 service to
current-project CLI usage. The CLI requires an existing database at the current
root, exactly one registered project and a matching stored root path. It does
not initialize state. IDs are exact; prefix resolution remains outside this
command. Listing JSON is an array of the unchanged M3.1 episode representation.
Plain text includes episode/run identity, root, run status/times, fact counts,
provider/fidelity/status and evidence IDs. Unknown values remain explicit.

`architect chronicle --run FULL_RUN_ID --event EVENT_ID [--json]` resolves one
source event through `ProjectChronicle.evidence(project_id, run_id=..., event_id=...)`.
The service reads and validates source evidence using the same decoder and
identity checks as episode generation, within a read-only SQLite snapshot.
JSON output is the original normalized ArchitectEvent object, including stored
metadata. Text evidence output is a heading followed by formatted JSON. No new
provider fields are collected or inferred. Legacy rows and other runs' evidence
cannot resolve through this interface.

Both modes buffer output until validation succeeds. Missing run/event, project
ownership errors and invalid normalized evidence yield exit code 1, stderr
only. `--event` without `--run` is a usage error (exit code 2). An empty project
lists no episodes successfully. Repeated commands over unchanged evidence have
identical output, independent of terminal width; no Rich markup is interpreted.

Project discovery and the subsequent service call are separate reads; each
service call uses one snapshot. Results describe evidence visible at that query,
not a retained historical snapshot. Evidence inspection resolves current stored
source rows. No schema, dependency, persistent Chronicle state or new architecture
boundary was added. ADR-004 still governs this design. Later M3 source extensions
are described below.
Acceptance evidence: [`milestones/M3.2.md`](milestones/M3.2.md).

## M3.3–M3.5 — Historical sources and parent closure

The approved M3 parent contract is implemented through deterministic read-only
query services and additional `architect chronicle --view` selections. Rationale
and source semantics are canonical in [ADR-005](adr/ADR-005-chronicle-historical-sources.md).

### Git change and ADR history

`GitHistory(project_root).changes(revision="HEAD")` returns commit records with
`commit_id`, committer `timestamp`, `parents`, `comparison_parent` and
`changed_paths` (path/status). Resolve the revision once per query; sorting is
(timestamp, full commit ID), not causal/topological order. Paths within a commit
sort lexically. Root changes compare to an empty tree, merges to the first parent,
renames appear as D/A, and empty commits remain represented. NUL-delimited Git
output preserves spaces, tabs, newlines and arbitrary filename bytes. No diff
content, commit-message interpretation or semantic summary is generated.

`GitHistory.decisions(revision)` returns ADR document revisions, ordered by
change-record order then path. Each provides the modifying commit, status, path,
source commit and blob ID. A deletion cites the previous file content. Only
regular tracked `docs/adr/**/ADR-*.md` files qualify; working-tree edits, symlinks,
submodules and approval_requested events never become durable decisions.
`GitHistory.file(full_commit_id, exact_path)` resolves regular source files to
blob identity and original bytes. Deleted paths resolve in comparison_parent;
other tree entries remain inspectable through Git itself. No branch or prefix
is accepted by the file resolver. Git source availability errors are explicit.

### Work and automation receipts

`ProjectChronicle.receipts(project_id, run_id=None)` produces one structured
receipt per terminal or normalized-event-backed run. An exact filtered run
without qualifying evidence returns no receipts. Project ownership and event
validation match the M3.1 service. Identity is `work:<project_id>:<run_id>` within
the database; times/status reference `run_source={table:"runs", run_id:...}`.

Receipts retain event IDs and selected observation fields (time, type, status,
provider, fidelity, tool and target). They expose tests, file_changes and explicit
failures separately. File changes require file_changed with a target and status
success or unknown; failed/blocked/pending attempts and file reads do not prove
changes. Unknown test results remain unknown. These are observations, not a
Git diff or inferred list of files modified by a run.

`automated` is true/false/null according to ADR-005's lifecycle metadata contract.
`automation_evidence_event_ids` retains every valid declaration, including
conflicts. Only true produces kind=automation_receipt; other receipts use
kind=work_receipt. No existing provider is assumed automated. The optional
boolean can be supplied through the existing normalized recorder API; no new
capture or scheduling capability is claimed.

### Failure history and access

`ProjectChronicle.failures(project_id, run_id=None)` flattens receipt failures.
Run failures cite the runs row and matching run_finished evidence if available.
Event failures include their original event ID and observed fields. Ordering is
(timestamp with unknown last, run ID, failure kind, event ID). Receipt ordering
is (begin time with unknown last, run ID); receipt observations preserve the
recorder timeline. Each SQLite service query uses one snapshot.

CLI views: `episodes` (default), `changes`, `decisions`, `receipts`, `automations`,
`failures`. New views emit deterministic JSON arrays; default text uses formatted
JSON, while `--json` uses compact JSON. ASCII escaping losslessly represents
unusual Git paths. `--revision` is for Git views; `--run` is for SQLite views.
Git/run association is never guessed: Git views reject `--run`. Existing
`--event` resolution remains exclusive to episodes. The CLI still requires an
initialized project and matching repository root registration. An empty Git
branch yields an empty history. Missing sources/invalid selectors fail explicitly.

M3 adds no persistence, dependency or M4 feature. Read-only Git and SQLite views
are independent snapshots; no cross-source atomicity or commit/run attribution
is promised. Whole-parent validation is in [milestones/M3.md](milestones/M3.md).

## M4 — Deterministic session intelligence

`SessionIntelligence(db_path, project_id)` composes existing evidence into status,
resume, explain and day reports; changes uses the Git history source directly.
CLI: `architect session <status|changes|day|resume|explain> [--json]`.
Existing `architect status` retains its M0 behavior.

Status reports recorded counts/active IDs and source episodes, explicitly leaving
live process state unknown. Resume selects an exact run or the greatest recorded
start time (unknown starts first, full-ID ties), returns source history and no
invented next actions or provider command. Explain exposes exact run/event
evidence, with unknown cause and no recommendations. These reports do not execute
agents, resume provider sessions or interpret arbitrary metadata as facts.

Day requires `--date YYYY-MM-DD`, defaults to UTC and accepts an IANA timezone.
It filters observed receipt events and run boundary occurrences, not all activity
of a run merely because that run began on the day. Changes accepts `--revision`
and optional reachable `--since` baseline; baseline ancestry is excluded. Git
and SQLite remain independent snapshots. No commit/run causal attribution or
past run status is reconstructed from today's status. All source IDs remain in
the output; error cases emit stderr without partial JSON. LLM narratives and
handoff are deferred. Evidence: [milestones/M4.md](milestones/M4.md).

## M5 — Local Context Economy

`LocalContext(root)` implements the small `KnowledgeProvider` search/read protocol.
Explicit refresh enumerates Git stage-0 tracked regular files, hashes current
working-tree bytes, reuses unchanged symbol analysis and drops removed entries.
It tracks HEAD separately from dirty working content. Python symbols use stdlib
AST; other UTF-8 files remain path-searchable. Parse failures are labeled.

The atomic `.architect/context-index.json` cache contains hashes, sizes, line
counts, symbols and skip reasons, not full source bodies or prompts. Repo map and
search refresh first; reads require current tracked regular membership and matching
hash, then return exact line ranges and hashes. Binary, non-UTF-8, symlink,
submodule, conflicted and oversized sources are rejected or explicitly excluded.
Untracked files are excluded; newly staged files qualify. This local tool is not
an adversarial filesystem sandbox or a retained source snapshot.

Bootstrap reads canonical AGENTS/STATUS/ROADMAP files when indexed, followed by
keyword-ranked paths/symbols. Its budget covers source-text characters only;
omitted files and skip reasons are explicit. Estimated tokens are ceil(chars/4),
not provider tokenizer usage. Metadata wrappers and future prompts are outside
that estimate. No provider content is sent externally. Optional knowledge sources
can implement the protocol; NotebookLM remains deferred. Hash validation reads
tracked file bytes on refresh; incremental savings apply to parsing and selected
context output, not zero-I/O refresh.

CLI: `architect context index|map|search|read|bootstrap`, with explicit query,
path/line range and character budget options. Context compilation does not invoke
models. Acceptance evidence: [milestones/M5.md](milestones/M5.md).

## Component Status

| Component | Status |
|---|---|
| CLI | IN PROGRESS |
| Storage | IN PROGRESS |
| Flight Recorder Core | COMPLETE |
| Observer Adapters | FOUNDATION, LIVE CLAUDE AND LIVE CODEX COMPLETE; PASSIVE PLANNED |
| Project Chronicle | M3 COMPLETE; M4 NOT STARTED |
| Session Intelligence | M4 COMPLETE |
| Context Economy | M5 COMPLETE |
| NotebookLM Provider | PLANNED |
| Benchmark | PLANNED |
| LEARN Labs | PLANNED |

## M6 explicit benchmark runtime (COMPLETE)

RESEARCH uses version-1 JSON suites and explicit argv subprocesses. Each trial gets
a fresh regular-file Git archive of clean tracked HEAD, without .git or untracked
files. Context none/bootstrap uses M5 and checks source hashes against that archive.
Suite hashes, source archive hashes, case identity and declared agent/model labels
preserve comparison boundaries; duplicate receipts are rejected. Results store
exit/timeout, elapsed seconds, output sizes/hashes, predicate success, context
characters/estimated tokens and optional command-reported usage. Missing usage is
unknown. No raw argv, output or prompt is stored in receipts.

This POSIX runner executes trusted commands with inherited user permissions and
environment: temporary working directories are not security sandboxes. Commands
can use absolute paths/network; native agent permissions still belong to the agent.
Timeouts kill the process group, including descendants on normal completion.
Output spools are temporary; evaluation/usage parsing is limited to 1 MiB, but disk
spool growth is not bounded independently of the timeout. Escaped process groups
are outside this trusted-command contract. JSON receipts are atomic local files
under .architect/benchmarks; SQLite and observer paths remain unchanged.
