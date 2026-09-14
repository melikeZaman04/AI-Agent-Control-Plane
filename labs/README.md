# Architect OS Labs — M7

LEARN provides two bundled controlled scenarios. The versioned corpus is packaged
at `src/architect/lab_corpus/` so installed CLI users receive the same exercises.

| ID | Failure category | Acceptance contract |
|---|---|---|
| retry | Non-idempotent retries | Repeated requests credit once; distinct requests and independent ledgers work |
| cache | Stale context | Reads reflect the requested file and latest contents, including empty contents |

```sh
architect init
architect lab list
architect lab start retry
# Edit files in the returned workspace using your chosen editor/agent.
architect lab check <lab-id>
architect lab progress <lab-id>
```

`start` creates a unique `.architect/labs/<id>/workspace` containing faulty learner
files. Instructions and success criteria appear in the JSON response. Acceptance
checks are kept outside that workspace and pinned by hash for the session.
“Hidden” means withheld from the initial learner workspace, not a secret against
inspection; checks are version-controlled and reviewable in the corpus.

`check` explicitly runs the bundled check against a temporary snapshot of all
regular learner files with a bounded timeout. The project and learner source
directories are not the check's working directory. Trusted Python still has the
user's filesystem/network permissions; this is not a security sandbox. POSIX
process-group cleanup comes from M6, while receipts remain separate LEARN records.
This runtime does not launch a coding agent, assign work, or infer mastery.

Every check, including a repeat, records a new atomic JSON attempt under
`.architect/labs/<id>/attempts/`. It stores input/check/scenario hashes, exit code,
timeout, elapsed time and output hashes/sizes, without raw output or code in the
receipt. Failed checks still exit the CLI successfully when their receipt is
recorded: inspect `passed`. Execution/setup errors produce a nonzero CLI exit.
Retain the corpus version and session files to resolve source hashes later.

Progress is a deterministic read of recorded attempts in sequence; a file lock
serializes checks and progress for each session. It reports the last **evaluated**
result, whether current files match that snapshot, and whether the pinned checker
is intact. A previous pass is not a claim that later edits pass. Timestamps and
elapsed times are observations, not repeatable metrics. No overall skill score is
inferred.

The initial corpus is deliberately small. Race conditions, deadlocks, hidden
dependencies and hallucinated APIs remain possible future corpus additions, not
implemented scenarios. RESEARCH can explicitly benchmark selected local commands
using M6; LEARN does not silently create benchmark or BUILD run records.
