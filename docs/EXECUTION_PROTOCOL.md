# Architect OS — Autonomous Milestone Execution Protocol

Canonical authority for autonomous execution behavior. Product scope belongs to
PRODUCT, architecture to ARCHITECTURE, progression and exit criteria to ROADMAP.
Repository files and Git are ground truth for implementation.

## Autonomy levels

| Level | Authority |
|---|---|
| A0 — Manual | Human specifies implementation steps. |
| A1 — Task Autonomy | Agent completes one bounded task. |
| A2 — Milestone Autonomy | Agent selects and completes tasks inside an approved milestone. |
| A3 — Roadmap Autonomy | Agent may move between milestones. |
| A4 — Product Autonomy | Agent may alter product direction or roadmap goals. |

**Current level: A3 — Roadmap Autonomy. A4 remains disabled.** The human
approved the remaining existing roadmap, including M4's explicit deterministic
session-intelligence contract. A3 supersedes the previous milestone-only approval
model: finish and checkpoint each parent milestone, then continue to the next
existing milestone without routine confirmation. Do not redefine product direction,
delete difficult roadmap objectives, or invent new product milestones.

Discover scope from PRODUCT, ARCHITECTURE, ROADMAP, ADRs and implementation.
When these imply one conservative architecture-preserving interpretation, derive
and record bounded exit criteria and proceed. A missing verbose checklist alone
is not a decision gate. Stop at a real Human Decision Gate or the roadmap end.
At the end report `ROADMAP COMPLETE — HUMAN PRODUCT REVIEW REQUIRED` or
`BLOCKED — HUMAN DECISION REQUIRED`. Continue concise progress updates and record
parent milestone evidence without ending execution to request routine approval.

## Execution loop

READ → UNDERSTAND CURRENT STATE → PLAN → SELECT NEXT BOUNDED TASK → IMPLEMENT
→ RUN TARGETED TESTS → SELF-REVIEW → REPAIR IF NEEDED → RUN REGRESSION TESTS
WHEN APPROPRIATE → CHECK EXIT CRITERIA → UPDATE EVIDENCE / DOCS → NEXT TASK OR STOP.

### Read and audit

At milestone start, read AGENTS.md, the current ROADMAP milestone, relevant
ARCHITECTURE and GLOSSARY sections, applicable ADRs, implementation and tests.
Inspect Git status/diffs/history and identify pre-existing working-tree changes.
Verify the next existing roadmap milestone, coherent boundaries and terminology,
prerequisite completion, explained local changes, and no unresolved decision gate.
Run the current regression suite (`.venv/bin/python -m pytest -q` in this repo).
Record the actual result; distinguish environment failures from source failures
and determine whether failures originate in HEAD or pre-existing local changes.
Never rely solely on historical passing counts or mask baseline failures.

### Plan

Identify exit criteria, existing capabilities, missing slices, dependencies,
risks and decision gates before coding. Order bounded tasks by dependency.
Evolve the plan when evidence changes. Do not build speculative subsystems.

### Implement

Choose the smallest correct slice. Prefer existing abstractions, standard Python,
the current storage model, deterministic logic and repository conventions.
Avoid unrelated rewrites. Within approved scope, inspection/search, code/tests,
fixtures, temporary local test projects, deterministic tooling, necessary local
refactors, glossary-consistent naming and relevant docs need no confirmation.
Small obvious, tested, backward-compatible schema additions explicitly required
by the milestone are permitted. Fix routine regressions autonomously.

### Test, review and repair

After each meaningful slice, run the narrowest relevant tests first, for example
`.venv/bin/python -m pytest tests/test_chronicle.py -q`. Inspect the diff for scope
creep, duplicate abstractions, unnecessary dependencies, provider leakage into
core, architecture violations, terminology drift, security/privacy regressions,
stale docs, mock-only tests and unrelated edits. Repair in-scope issues.

A meaningful repair loop is failure → investigation → change → retest. At most
three meaningful loops may address the same blocking problem; trivial typos do
not count separately. If the architectural blocker remains after three loops,
stop at gate H. Report the problem, evidence, attempts, alternatives and a
recommended decision. Do not thrash.

Never delete valid tests, weaken assertions to accept broken behavior, hide
failures or declare completion with unexplained regressions. Broaden regression
testing after shared changes and run the full suite at milestone completion.

### Exit and evidence

Completion requires every documented exit criterion, passing relevant tests and
full regression, no
unexplained architecture violation or unresolved gate, current canonical docs,
and observed behavior matching claims. Code written alone is insufficient.
Ground claims in pytest, actual CLI output, database state, source event IDs,
Git diff, deterministic queries or provider smoke evidence. Synthetic fixtures
cannot establish live provider capability when live validation is required.

At exit inspect `git status`, `git diff --check` and relevant diffs, including new
files. Record capability, limitations, tests and any gates; suggest a commit
message and create a local checkpoint commit. Continue to the next documented milestone
automatically; stop at roadmap end for human product review.

## Human Decision Gates

Stop affected work and ask the human when any of these applies. Existing explicit
authorization remains valid; implementing a documented approved boundary is not
itself a request to change that boundary.

| Gate | Trigger |
|---|---|
| A — Architecture | An existing durable boundary must change, agent/Architect ownership changes, or an unapproved core subsystem is required. |
| B — Major schema | Database redesign or migration has non-trivial trade-offs; obvious additive changes within approved scope are exempt as above. |
| C — External dependency | A new non-trivial runtime dependency, service, daemon, database, queue, framework or network service is required. Small protocol dependencies may be proposed under existing dependency policy. |
| D — Security/privacy | A change affects credentials, tokens, secrets, permissions, sandbox policy, external accounts, prompt capture or potentially sensitive telemetry. |
| E — External/irreversible effect | Push, deploy, production API mutation, external messages, destructive database operations or deletion of user data. |
| F — Product/roadmap | The milestone appears wrong or insufficient, or product/roadmap scope must change. |
| G — Material ambiguity | Two or more unresolved interpretations change product behavior, architecture boundaries, persistence, security/privacy, external effects or roadmap scope. Missing checklists alone do not trigger this gate; derive conservative criteria when the canonical contract supports one interpretation. |
| H — Failed repairs | The same architectural blocker survives three meaningful repair loops. |
| I — Conflicting truth | Canonical sources materially contradict one another; do not silently choose one. |

Gate reports specify the decision required, evidence and attempts, viable
alternatives and recommendation. Routine implementation choices are not gates.

## Git policy

Inspect status, diffs and history freely. Preserve unrelated working-tree changes.
After each successfully completed parent milestone: run full regression, inspect
status/diff, run `git diff --check`, update evidence and create a concise local
milestone checkpoint commit. This commit authorization is explicit under A3.
Do not rewrite history, force push, reset hard, delete branches or discard user work.

Push only if the remote/branch is clearly a non-protected development branch and
there is no production deployment or unsafe external effect. If protection,
ownership, CI/CD or deployment behavior is uncertain, keep commits local and
continue development. Never push secrets or through an unresolved decision gate.
An uncertain push is not a blocker for local development.

## Verification and workflow extraction

Use self-review plus full regression for normal bounded features. Independent
verification is justified for architecture, schema/migrations, concurrency,
provider integration, security/privacy, external effects and new autonomy
mechanisms; do not spawn verifiers mechanically at every milestone.

Extract a skill or agent workflow only when repetition and stability demonstrate
its value. Report the concrete repeated workflow, keep the extraction concise,
reference canonical policy rather than duplicate it, and validate it. Do not
create specialized skills or agents speculatively. This records the human's
extraction guidance; no separate extraction policy existed before A3.

## Documentation ownership and context economy

| Source | Canonical responsibility |
|---|---|
| AGENTS.md | Operational entry point |
| docs/PRODUCT.md | Product intent |
| docs/ARCHITECTURE.md | System architecture |
| docs/ROADMAP.md | Milestone progression and exit criteria |
| docs/GLOSSARY.md | Terminology |
| docs/EXECUTION_PROTOCOL.md | Autonomous execution behavior |
| docs/adr/ | Durable architecture decisions |
| docs/integrations/ | Provider instructions and acceptance evidence |

Reference canonical owners; do not copy large sections between documents.
Use progressive discovery: task → relevant docs → relevant symbols/files → exact
source. Do not repeatedly load the entire repository or unchanged long docs on
repair iterations. Context savings must not reduce correctness.

## Optional runner skill

The protocol and AGENTS.md are sufficient without a skill. The concise
`architect-milestone-runner` skill references this protocol. On 2026-09-15,
local `codex --version` reported `0.154.0-alpha.6.1`; help did not document skill
paths. The fetched [official skills documentation](https://learn.chatgpt.com/docs/build-skills)
explicitly supports repository `.agents/skills/<name>/SKILL.md`. This is the
supported location used here; no global configuration is required.
