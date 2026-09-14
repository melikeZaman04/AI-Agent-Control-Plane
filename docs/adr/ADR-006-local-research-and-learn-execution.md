# ADR-006: Explicit local RESEARCH and LEARN execution

## Context

A3 approved the existing M6 benchmark and M7 labs scope. BUILD history remains
provider-independent; native agents retain conversations, tools and permissions.

## Decision

M6 executes explicit trusted argv suites in fresh regular-file archives of pinned
Git HEAD. M7 executes bundled checks against fresh copies of learner workspaces.
Both use a standard-library POSIX subprocess helper with timeouts and process-group
cleanup. These are repeatable working directories, not new security sandboxes;
no native agent permission policy is bypassed or reimplemented.

Keep local atomic JSON receipts separate by product mode: RESEARCH benchmarks and
LEARN attempts do not fabricate BUILD observations or write FlightRecorder events.
Receipts retain source hashes and measured outcomes, without raw command output.
RESEARCH comparisons separate suite, source, case, declared model/agent and context
strategy. Usage is command-reported; unknown remains unknown. LEARN progress is
ordered attempt evidence, with explicit current-source mismatch and no mastery
inference. File locks serialize per-session lab checks/progress.

## Consequences

No new database schema, runtime dependency, service, agent orchestration or external
account is required. Commands retain inherited user permissions; trusted-code
execution is explicit. Output spools lack an independent disk quota, and escaped
process groups are outside the contract. Sources/suite/corpus/session files must
be retained for later hash resolution. Stronger isolation, signed certification
and remote evaluation would require separately approved contracts.
