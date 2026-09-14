# ADR-004: Chronicle as a deterministic run projection

## Context

M3.1 requires structured, reproducible project history with evidence links. Runs
and normalized events already persist in project-local SQLite. The existing
schema has no run-to-project column; the CLI registers the current project in
its own database. Chronicle must not manufacture ownership or duplicate events.

## Decision

Derive one `ChronicleEpisode` per run on demand from a single read-only SQLite
snapshot. Do not introduce a materialized table, migration or cache for M3.1.
The project-local database must contain exactly one registered project; reject
unregistered/shared databases rather than infer run ownership.

Identity is database-scoped `(project_id, kind="run", full run_id)`, rendered as
`run:<project_id>:<run_id>`. Re-querying is rebuilding: no stored derived state
can duplicate or become stale. Equivalent evidence produces identical JSON.

Run timestamps and status come directly from the identified runs row. Each
`ObservationFact` groups normalized observations by event type, event status,
provider and fidelity, retaining every supporting event ID and a derived count.
Unknown values stay unknown. Source metadata is available through original
events; Chronicle does not copy or interpret arbitrary metadata or tool output.
No provider parsers, LLMs or command classification enter the Chronicle path.

## Consequences

Queries cost a scan of selected run evidence, acceptable for the foundation.
There are no persistent episode annotations or historical snapshots of prior
query results. Raw events remain available and untouched. Multi-project shared
databases would require a future explicit ownership decision; M3.1 rejects them.
This implements the already-approved Chronicle boundary; it changes no existing
provider, recorder ownership or storage boundaries.

## M3.2 application

The CLI exposes this same projection and exact source-event inspection. Both
service paths share normalized evidence validation and read-only snapshot
semantics. No materialized state or ownership redesign was introduced.
