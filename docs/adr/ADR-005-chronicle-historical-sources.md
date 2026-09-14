# ADR-005: Deterministic historical sources and work receipts

## Context and authority

The human approved the complete M3 closure contract: change and durable decision
history, work receipts, explicit automation classification and failure history.
This extends the M3.1/M3.2 read-only foundation without changing recorder/provider
ownership or adding persistent Chronicle storage.

## Decisions

- Git history is queried on demand from the exact registered repository root.
  Resolve the requested revision once to a full commit ID, then traverse reachable
  commits. Use committer UTC timestamps and commit-ID ties for deterministic order.
  Compare merge trees to their first parent; show renames as delete/add. Include
  root commits and empty commits. Ignore working-tree content. Git replacement
  objects and inherited GIT_* redirection are excluded from this source query.
- Change provenance is repository root + full commit ID + changed path, with the
  comparison parent identifying the prior tree (especially for deletions).
- Durable decision history consists of regular, version-controlled
  `docs/adr/**/ADR-*.md` document revisions. Return commit/path/blob provenance;
  deletion records point to prior content in the first parent. This does not
  infer whether a decision is accepted, superseded or implemented. Symlinks and
  submodules are not read as ADR documents. There is no other explicit durable
  decision-record contract in the current model. Tool approval is never a
  durable project decision.
- SQLite work receipts are derived in one read-only snapshot per service call.
  A terminal run (SUCCESS/FAILED/CANCELLED) or a run with normalized observations
  qualifies. Empty pending/running registrations alone do not prove work.
  Run identity/status/timing cite the runs row. Observation facts cite event IDs.
  Receipt identity remains stable as evidence arrives; it is not a frozen audit
  artifact, a new event store or a claim of completed work when status is pending.
- Optional `metadata.automated` must be a JSON boolean on a normalized
  `run_started` or `run_finished` event to declare whole-run automation. This is
  the smallest explicit representation in the existing metadata model. All valid
  declarations must agree; absence/conflict stays null. A true value yields an
  automation receipt; false explicitly declares non-automation. Keep declaration
  event IDs. Strings, numbers, ordinary tool metadata and provider identity do
  not establish automation. Existing provider integrations do not currently emit
  this declaration; they remain unknown without explicitly supplied evidence.
- Failures come from runs.status=FAILED, normalized error events, and failed
  tool_execution/test_execution observations. A run failure and its tool failures
  are distinct pieces of evidence, not deduplicated causal incidents. No narrative
  reason or recovery recommendation is generated.

## Consequences

No schema/migration, dependency, scheduler, daemon or LLM is added. Standard-library
subprocess invokes the installed Git executable read-only. Git and SQLite are
separate source snapshots, not an atomic combined transaction. No temporal
coincidence creates commit/run attribution. Source resolution requires retained
Git objects or SQLite evidence; externally deleting sources is outside this
projection's guarantees. History is limited to commits reachable from the chosen
revision and available locally; there is no fetch, alternate-branch aggregation
or uncommitted-change capture. Large-history indexing/pagination is deferred.
