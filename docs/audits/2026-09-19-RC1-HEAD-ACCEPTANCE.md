# RC1 product acceptance audit — 2026-09-19

**PRODUCT ACCEPTANCE AUDIT: FAIL**

This verdict applies to repository **HEAD** `17f8b61a69a7737cc65b102260dc4ec8b10098e5`, not to the uncommitted acceptance repairs in the working tree. Fresh Claude and Codex observation worked, and the HEAD regression passed. Four reproducible, material correctness or acceptance-validity defects still prevent acceptance of that commit. No product code, tests, or canonical project evidence was changed during this audit; no commit or push was made.

## Exact baseline

**FACT —** `git rev-parse HEAD` returned `17f8b61a69a7737cc65b102260dc4ec8b10098e5` on branch `main`. The initial `git status --porcelain` was:

```text
 M README.md
 M docs/ARCHITECTURE.md
 M docs/GLOSSARY.md
 M docs/STATUS.md
 M labs/README.md
 M src/architect/benchmark.py
 M src/architect/chronicle.py
 M src/architect/cli/main.py
 M src/architect/git_history.py
 M src/architect/lab_corpus/retry/evaluator.py
 M src/architect/lab_corpus/retry/scenario.json
 M src/architect/recorder/recorder.py
 M src/architect/session.py
 M tests/test_benchmark.py
 M tests/test_run_lookup.py
?? docs/WORK_PLAN.md
?? docs/audits/
?? experiments/
?? tests/test_acceptance.py
```

**FACT —** HEAD's `docs/STATUS.md` says approved M0–M7 implementation is complete, human product review is pending, A4 is disabled, and M2.4 passive observation, optional NotebookLM, and handoff are deferred. It cites the historical M7 regression of 239 tests. The dirty working-tree `docs/STATUS.md` separately says the A1–A6 repair package passed 263 tests on 2026-09-16 and explicitly does not claim fresh independent acceptance. These are different code states.

**MEASUREMENT —** HEAD collected **239 tests**. The dirty checkout collected **263 tests**; its suite was not used as proof about HEAD.

**Environment and method —** Python 3.14.7 and the existing project virtual environment were used. An isolated local clone at `/tmp/architect-rc1-head-17f8b61` held the exact committed source. `PYTHONPATH` pointed to that clone's `src` so the virtual environment's editable installation could not import dirty source. A temporary `.venv` symlink let the documented subprocess hook command resolve. All live databases, benchmarks, lab attempts, and corruption fixtures stayed under `/tmp`. Claude Code was 2.1.259; Codex reported 0.154.0-alpha.6.1. Both were already authenticated. Local loopback permission was granted for the foreground Codex listener and the OTLP regression tests. No global provider telemetry configuration was edited.

An initial regression attempt was **discarded**: without `PYTHONPATH`, the editable package imported the dirty checkout into the HEAD test tree, and sandboxed loopback sockets were denied. The corrected, loopback-enabled full run was `.venv/bin/python -m pytest -q --tb=short` with `PYTHONPATH=/tmp/architect-rc1-head-17f8b61/src`: **239 passed in 3.77s**. `git diff --check` passed both in the original working tree and the isolated HEAD clone; `git show --check HEAD` also passed.

## Fresh live providers and end-to-end provenance

**FACT — Claude.** In `/tmp/architect-rc1-live-claude`, Architect created run `d460de1d-c749-450f-b93a-8422ed2d568d` with declared NATIVE fidelity. A fresh real `claude -p` process used the documented opt-in hook template. Its native session `2a52eeea-9d96-4963-915b-2bdf7a206c30` was bound exactly to that run. Its output reported `1 passed in 0.00s`. The `SessionStart` hook bound the session; `PostToolUse` hooks produced two normalized rows:

| UTC receipt time | Evidence ID | Observed claim |
|---|---|---|
| 12:55:30.364549 | `734284ba-4b13-4699-bfa6-07fa07e429e3` | `file_read`, README, success |
| 12:55:32.894400 | `0d364a89-1419-454a-97d6-f8bbcbb0d737` | `tool_execution`, Bash, outcome unknown |

The second event's retained hook response contains `1 passed in 0.00s`. Its env-prefixed shell command was not promoted to `test_execution`, nor was the run marked successful. Both events carry `provider=claude`, `fidelity=NATIVE`, `synthetic=false`, `timestamp_source=hook_received_at`, and the bound native session in metadata. The run remains `RUNNING` with no end timestamp, as the documented live hook contract requires.

**FACT — Codex.** In `/tmp/architect-rc1-live-codex`, Architect created run `0a0e177e-5712-48fd-a106-17231b0aeb91`. The documented foreground binary OTLP listener on `127.0.0.1:14328` received a fresh real `codex exec` process, native session `01a0b9bb-b8ac-76f1-aa45-60fcff3368ca`. Codex read README and ran the smoke test, reporting `1 passed in 0.00s`. After Codex exited and flushed, the listener reported **6 recorded, 22 ignored, 0 rejected**. The six rows are two `approval_requested` and four `tool_execution` observations, all with the same native session, NATIVE fidelity, and `synthetic=false`. The `exec_command` tool-result record `2aac0058-e5a1-42b7-8745-1f3b26044d99` has provider-reported tool success; it does not prove a passing test. The run remains `RUNNING`, and no `test_execution` was inferred from telemetry that omits command contents.

**FACT — trace.** For both runs, the path was native hook/OTLP observation → `ClaudeObserver`/`CodexObserver` → normalized `ArchitectEvent` → `FlightRecorder` SQLite row → `ProjectChronicle` episode/receipt → `SessionIntelligence` status, day, resume, and explain. The source DB row IDs, recorder timeline IDs, and Chronicle episode IDs agree in timestamp/insertion order: **2 of 2 Claude** and **6 of 6 Codex** source events resolved through `chronicle --run ... --event ... --json`. The sampled `session explain` evidence equaled the original event; `cause` remained null and recommendations empty. `chronicle --view receipts` retained the same event IDs; failure views were empty. `session status`, `changes`, `day`, `resume`, `explain`, and `chronicle` were exercised. Temporary Git fixture commits made **after** the provider runs allowed Git-backed day/changes commands; those commits were listed independently and never attributed to the runs. A nonexistent event ID exited 1 with no stdout for both providers.

**FACT — fidelity and boundary.** A separate PASSIVE fixture remained PASSIVE through Chronicle. Live provider names, native event names, session IDs, tool inputs/response or allowlisted OTel attributes stayed in event metadata; the normalized event fields and recorder/Chronicle source imports remained provider independent. Codex did not persist prompt/command/output fields. NATIVE on these fresh runs is supported by the actual foreground provider processes and opt-in native channels, not inferred from the temporary Git commits or `synthetic=false` alone. Provider process origin is operational evidence, not cryptographic attestation.

## M5 Context Economy acceptance

**LIMITATION — fresh-agent correctness probe.** Automatic approval review rejected an authenticated `codex exec` cold-start session against this private repository. The stated reason was that the session would transmit potentially sensitive repository documentation to an external provider; the live smoke authorization did not specifically authorize this repository payload. The rejected action was not bypassed. Consequently, no fresh agent's five answers, actual model token use, dependency misses, repair loops, or model tool-call count can be claimed. Authorization to send repository documentation to Codex would be required for that remaining check.

**MEASUREMENT — local, deterministic substitute.** Following `docs/EXECUTION_PROTOCOL.md` progressive discovery, an isolated fresh process compared a generous canonical-document control with the implemented `LocalContext.bootstrap` plus exact targeted reads. These are measured *source payloads*, not comparable model sessions:

| Path | Sources delivered | UTF-8 bytes | Source characters | Explicit source reads | One observed wall time |
|---|---:|---:|---:|---:|---:|
| Control: AGENTS, PRODUCT, ARCHITECTURE, ROADMAP, STATUS, EXECUTION_PROTOCOL, GLOSSARY, six ADRs | 13 files | 64,726 | 64,428 | 13 | 0.291 ms |
| M5: bootstrap plus targeted ROADMAP, ARCHITECTURE and EXECUTION_PROTOCOL ranges | 7 unique files, 9 ranges | 22,231 | 22,047 | 9 | 86.265 ms, cold index |

Bootstrap alone selected `AGENTS.md`, `docs/STATUS.md`, `tests/test_session.py`, and `docs/PRODUCT.md`: **10,638 source characters**, labeled estimate **2,660 tokens**, HEAD matched. It omitted `docs/ROADMAP.md` and `docs/ARCHITECTURE.md` for the 12,000-character budget, so the local procedure explicitly read their relevant ranges before assessing roadmap and architecture. The selected test file was unnecessary for this question. Indexing examined **75 tracked files**; the source-read counts above exclude these refresh reads. No context-reduction percentage or model-correctness advantage is inferred. M5 does not expose native token consumption or a trace of files an external agent actually read. The targeted payload contains the stated roadmap closure, observer/recorder boundary, deferred scope, and human-review next step; whether a fresh agent would use it correctly remains untested.

## M6 Research and M7 Labs product smoke

**FACT — M6.** The real `architect benchmark run`/`compare` CLI path executed suite SHA-256 `ca1bdd5a3616a4ef92ca5457142d56ba44a10be99c72a135608b144f55177dac` against pinned HEAD and source archive SHA-256 `2ed9a9343fe8060279e9656347303e0b7cf5d1d0b1fc1410979d14d4476741d0`. Receipt `c04bf833-f19f-4146-a082-c6832ac98da5` has two successful `none` controls, two successful bootstrap trials whose commands opened the `{context_file}` JSON and asserted snippets exist, and one correctly failed output-predicate trial. Repeats have stable outcome and source/context hashes; elapsed time varies. `compare` kept case/strategy groups distinct. The receipt uses pinned Git source, M5 context hashes, and command output/exit as its explicit RESEARCH oracle. It does not claim a Flight Recorder run link or actual model quality. The fixture's reported `input_tokens` is a command-supplied number and must not be treated as model usage.

**FACT — M7.** The real `architect lab list/start/check/progress` CLI path started retry lab `e20e1840dd4b4e7c867801c7c424fd4d`. Its untouched fixture failed attempt 1 (exit 1; stderr 197 bytes with SHA-256 recorded). An incorrect repair keyed deduplication by `(request_id, amount)` passed attempt 2, although a same-ID retry with a changed amount produces balance **106** instead of **7**. Progress marked attempt 2 stale after the workspace changed. A correct per-state, request-ID repair passed attempts 3 and 4, with separate file/check/scenario hashes and ordered receipts. The evaluator and learner source remain inspectable; receipts preserve exit outcome, byte counts and hashes, but not raw stderr text. This is a checker coverage failure, not evidence of learner mastery.

## Reliability and adversarial findings

**MEASUREMENT — passing probes.** In temporary databases/workspaces, duplicate `event_id` recording was rejected; two equal-time events retained insertion order across repeated timeline queries; an explicit `FAILED` run kept its end time and three failure entries; unknown and wrong-run evidence IDs were rejected; a conflicting provider-session binding was rejected; a legacy payload was not promoted to normalized evidence; and PASSIVE evidence stayed PASSIVE. An injected event-insert failure rolled back run start and event together, then retry/explicit failure completion succeeded. Benchmark subprocess descendants were cleaned up after normal parent exit and timeout. Loopback listener rejection/recovery behavior was covered by the full 239-test run.

**FACT — material HEAD defects reproduced during this campaign:**

| ID | Severity | Minimal reproducer and observed result |
|---|---|
| A1 | MAJOR, provenance/completeness | In a disposable DB, record a valid normalized event, then delete only `timestamp` from its stored JSON. `FlightRecorder.timeline` returns zero and Chronicle silently omits its ID. With one other valid event present, `chronicle --json` exits **0** and emits a plausible incomplete episode. Separately, an M0 `log_event` row containing a normalized payload for another run is returned by Recorder under the wrong run while Chronicle rejects it. |
| A2 | MAJOR, session reporting | Create a RUNNING run with a recorded start and no normalized events. `session status` includes it, Chronicle has `began_at`, but `session day` for that UTC date returns `work: []`. |
| A3 | MAJOR, lab oracle | Retry lab's unchanged bundled checker passes the `(request_id, amount)` wrong repair (106 instead of 7). A separate global-seen wrong repair also passes while interleaved states produce 14 instead of 7. |
| A4 | MAJOR, benchmark validity | A valid `bootstrap` case with argv `python -c 'print("OK")'` and **no** `{context_file}` placeholder passes and reports 56 context characters / 14 estimated tokens, though the command never receives the bundle. |
| A5 | MINOR, Git provenance | `GitHistory.file()` accepts `HEAD^{tree}` and returns that tree object ID as `commit_id`, although the API promises a commit ID. |
| A6 | MINOR, documentation | HEAD's component table labels CLI/Storage `IN PROGRESS` and passive/NotebookLM `PLANNED` despite the narrower completed/deferred status elsewhere. |

The A1–A5 observations were reproduced using the isolated HEAD import path and temporary fixtures; the pre-existing [probe source](2026-09-15/probes.py) and [recovery probe](2026-09-15/recovery.py) describe the procedures. Fresh output files and the new invariant/live-trace scripts remain under `/tmp/architect-rc1-*` for local inspection. No test assertion was weakened, and no defect was fixed during this first audit pass.

## Limits, deferred scope, and decision

**LIMITATION —** The external fresh-agent context task was blocked by automatic approval review. The local comparison measures source bytes/characters and one-process timing; it cannot establish model token savings or agent answer correctness. The smoke tests establish actual provider transport and observed event fidelity in temporary projects, while provider-native tools' complete histories and guaranteed delivery are outside the documented contract. Benchmark and lab receipts retain hashes/outcomes rather than raw command output. The HEAD result does not evaluate whether the dirty, uncommitted repair package deserves acceptance.

**FACT — deferred scope.** M2.4 passive observer, optional NotebookLM, handoff, A4/new roadmap, agent runtime orchestration, guaranteed telemetry delivery/retry deduplication, and stronger execution isolation are documented exclusions. Their absence was not counted as a defect.

**INFERENCE — verdict.** The clean HEAD regression and fresh native provider paths support important implemented claims. A1 loses source evidence silently; A2 omits a recorded boundary; A3 certifies incorrect lab behavior; A4 can report an undelivered context strategy as measured. Each violates a current product contract and is independently reproducible, so the only supported verdict for **HEAD** is **PRODUCT ACCEPTANCE AUDIT: FAIL**. Review of the separate, uncommitted repair package and the blocked fresh-agent context check remains outside this HEAD verdict.
