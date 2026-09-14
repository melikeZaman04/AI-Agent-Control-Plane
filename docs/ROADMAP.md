# Architect OS Roadmap

## M0 — Foundation

Deliver the repository contract, architecture/product/roadmap documentation, package metadata, SQLite projects/runs/events storage, CLI foundation, `architect init`, tests, and documentation. Exit criteria: `architect init`, `architect run`, and `architect status` work; tests pass; architecture is documented.

**Status:** COMPLETE.

## M1 — Flight Recorder Core

Define the provider-independent normalized event contract before provider integrations.

**Status:** COMPLETE. Implementation includes normalized events, atomic lifecycle recording, deterministic timelines, and `architect inspect` with full ID or unique prefix lookup. M0 regressions and M1 tests pass; isolated CLI validation succeeded. Do not begin M2 automatically.

## M2 — Observer Integration

Add Claude, Codex, and passive observers that translate provider evidence into normalized Architect events.

**Status:** Approved live integrations COMPLETE; passive observer DEFERRED.

- M2.1 Observer Foundation — COMPLETE: synthetic Claude normalization, session/run bindings, synchronous ingest, and isolated pipeline tests.
- M2.2 Live Claude Integration — COMPLETE: stdin CLI, live-format normalization, opt-in hook template and automated tests implemented. User-performed live smoke test confirmed FILE_READ and TEST_EXECUTION in Architect inspect; see `docs/integrations/claude.md` for evidence.
- M2.3a Codex Observer Foundation — COMPLETE: synthetic OTel-style normalization, Codex session/run correlation, privacy filtering, end-to-end SQLite inspection, and transport design. Live transport is not included; see `docs/integrations/codex.md`.
- M2.3b Live Codex OpenTelemetry Ingest — COMPLETE: foreground loopback binary OTLP/HTTP listener, explicit run correlation, allowlisted live normalization, and transport tests. Real Codex tool-result and approval events were recorded and inspected on 2026-09-14 UTC; evidence and repeatable smoke commands are in `docs/integrations/codex.md`.
- M2.4 Passive Observer — DEFERRED; requires a demonstrated need and human approval.

M2.2 installation is explicit and project-local. M2.3b export is opt-in and user-controlled. Do not start M2.4 automatically.

## M3 — Project Chronicle

Build project timelines, change and decision history, automation receipts, and failure records.

**Parent status:** COMPLETE. Acceptance evidence: [`milestones/M3.md`](milestones/M3.md). M3 was completed under A2; the subsequent A3 approval now governs progression.

Approved closure contract: deterministic access to Git commit identities/times/
changed paths; durable decisions evidenced by version-controlled ADRs (or already
supported explicit decision records); structured evidence-backed run/work receipts;
automation receipts only where explicit evidence establishes automation; and
failure history from explicit run/event outcomes. Source links must resolve,
repeated queries must be deterministic, real Git/SQLite tests and full regressions
must pass, canonical docs must match, and no Human Decision Gate may remain.
No semantic summaries, automation scheduler or M4 session-intelligence commands.

### M3.1 — Chronicle Foundation

**Status:** COMPLETE. First A2 autonomy pilot under `EXECUTION_PROTOCOL.md`.
Implemented as read-only run episodes derived from SQLite, with no schema change.
Acceptance evidence: [`milestones/M3.1.md`](milestones/M3.1.md). M3.2 is approved with the scope below.

Scope: a minimal deterministic, evidence-linked project history derived from
existing runs and normalized events. A service query API is sufficient. SQLite
remains the local source; additive storage only if necessary. No LLM generation.

Exit criteria:

1. Clear Chronicle domain model with project/run association, episode kind,
   begin/end times when known, structured observed facts and evidence IDs.
2. Deterministic output, preserved provenance, minimal local storage, idempotent
   reprocessing and deterministic chronological queries.
3. Normalized Claude/Codex-origin events work through provider-independent core;
   legacy data is not promoted to facts without valid normalization.
4. End-to-end source event resolution, new tests and full regressions pass.
5. Canonical docs reflect behavior and no Human Decision Gate remains unresolved.

Out of scope: narrative intelligence, advanced Git analysis, `/day`, `/resume`,
`/changes`, `/explain`, passive observation, daemons, NotebookLM, Context Compiler,
Repo Map, retrieval, benchmarking, labs, multi-agent orchestration and web UI.

### M3.2 — Chronicle CLI and evidence inspection

**Status:** COMPLETE — approved scope implemented and verified.
Acceptance evidence: [`milestones/M3.2.md`](milestones/M3.2.md).

Exit criteria:

1. A read-only CLI displays current-project or selected-run episodes using the
   M3.1 Chronicle service; deterministic text and JSON output are available.
2. Episode evidence IDs resolve to original normalized events in the selected
   project/run, preserving provider/fidelity, unknown values and source metadata.
3. Missing project/run/event, ambiguous project ownership and malformed evidence
   produce explicit errors without initializing or changing stored history.
4. Real SQLite/FlightRecorder end-to-end CLI tests and full regressions pass;
   canonical docs and command examples match observed behavior.

No new persistence, schema, dependency, natural-language intelligence, advanced
Git analysis, `/day`, `/resume`, `/changes` or `/explain` is included.

### M3.3 — Git change and durable decision history

**Status:** COMPLETE.

Read-only history pinned to Git commit identities, timestamps and changed paths,
plus version-controlled ADR revisions with resolvable file/blob provenance.
Tool approvals must never become durable decisions. Real Git tests cover root,
merge, deletion and unusual paths, repeatability and source resolution.

### M3.4 — Work receipts and failure history

**Status:** COMPLETE.

Derive structured receipts for terminal or observed runs, retain source event IDs,
known file/test/provider/fidelity facts, and explicit failures. Automation requires
an explicit supported evidence marker; absence is unknown, not proof of manual
work. No scheduler, new provider capture or inferred causal narratives.

### M3.5 — Parent closure validation

**Status:** COMPLETE.

Verify all historical query surfaces with real Git/SQLite evidence and stable
ordering, run full regression, review boundaries/diffs, and update canonical
contracts and acceptance evidence. M3 exit evidence is complete; continue according to the current execution protocol.

## M4 — Session Intelligence

Build status, changes, day, resume, explain, and later optional handoff workflows.

**Status:** COMPLETE — evidence in `docs/milestones/M4.md`; handoff and LLM narrative deferred.

Exit criteria: deterministic read-only status, changes, day, resume and explain
reports over existing Chronicle/Git/SQLite, with resolvable source references.
Status reflects recorded run states, not inferred live process state. Changes
reports committed history at a pinned revision and optional explicit baseline.
Day requires an explicit ISO date and timezone (UTC default), selects observed
events, run boundary timestamps and commits in that day. Resume exposes the
selected/latest recorded run, evidence and failures without launching an agent or
inventing next steps. Explain resolves selected run/event evidence with explicit
unknown cause/recommendation fields. Real Git/SQLite and CLI tests verify repeatable
outputs, boundaries and absent evidence; full regression and docs must pass.

## M5 — Context Economy

Build bootstrap memory, Git HEAD tracking, incremental indexing, a repo map, targeted retrieval, context metrics, and a knowledge-provider boundary. NotebookLM remains optional; the repository remains ground truth.

**Status:** COMPLETE — evidence in `docs/milestones/M5.md`.

Conservative exit criteria: an explicit local index tracks Git HEAD and tracked
working-tree content hashes; reuses unchanged symbol analysis and removes deleted
entries. A deterministic repo map, keyword-ranked path/symbol retrieval and exact
line-range reads retain source hashes. Bootstrap context combines canonical entry
files and selected source snippets under an explicit character budget; omitted
content and token-estimation limits are reported. Stale sources are refreshed or
rejected, never silently returned. A small local knowledge-provider protocol
allows future optional sources without replacing Git. Cache only metadata in
`.architect`, never raw prompts or full source bodies. Real repository tests cover
updates/deletions, symlinks, stale reads, budgets and repeatability; full regression
and canonical docs pass. NotebookLM and external retrieval remain optional/deferred.

## M6 — Research / Benchmark

Build evaluation suites, repeatable runs, model and context-strategy comparisons, and token/context metrics.

**Status:** COMPLETE — evidence in `docs/milestones/M6.md`.

Exit criteria: an explicit local JSON suite defines bounded repeated argv commands,
agent/model labels, expected exit/output checks and context strategy (none or M5
bootstrap). The runner executes real subprocesses with timeouts, records per-trial
outcomes/timing/output hashes plus context metrics and optional generic
command-reported token usage, and stores local JSON receipts. Raw commands,
prompts and command output are not persisted in receipts. Comparison groups
results by case/agent/model/context strategy and reports success rates and observed
metrics without claiming model quality from synthetic fixtures. Validate manifests
before execution, preserve source suite/context hashes, test repeatability,
timeouts, failures, metrics and real CLI paths. No external model account is
required; actual provider commands are user-selected, never inferred or launched
by installation. Full regression and canonical docs pass.

## M7 — Learn / Labs

Build a failure corpus, controlled scenarios, hidden failures, success criteria, and progress tracking.

Do not implement M1–M7 during M0.
