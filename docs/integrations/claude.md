# Claude local hook integration (M2.2)

Status: M2.2 COMPLETE. Automated validation passed (87 tests), and the user performed the real Claude smoke test and supplied terminal output confirming recorded native events.

## Live smoke evidence

Evidence source: user-provided Claude session and `architect inspect`, `architect status`, and `pwd` output, reviewed on 2026-09-15. This is a user-performed test, not an agent-executed Claude session.

- Project: `/tmp/architect-claude-smoke.CPvR9l`
- Architect run: `c7998af3-c6d7-45a2-8441-a9c6ace176c0`
- Claude session: `61778cfc-e9b4-4ed7-87eb-7fada75dcef5`
- FILE_READ: README.md, success, received at `2026-09-14T21:28:25.845864+00:00`.
- TEST_EXECUTION: `pytest -q`, received at `2026-09-14T21:28:30.915360+00:00`; retained tool response reports `1 passed in 0.00s`.

Both events reference the same Claude session, use PostToolUse metadata, and carry synthetic=false. The run is NATIVE and remains RUNNING as designed. TEST_EXECUTION status is unset; the test result is evidence in the retained provider output, not an inferred normalized success status. The temporary path is a historical reference and may not persist.

The opt-in template is [claude-settings.example.json](claude-settings.example.json).
It is not installed by `architect init`. It uses inherited `ARCHITECT_EXECUTABLE`
and Claude's `CLAUDE_PROJECT_DIR` to select the executable and fixed project root,
including paths containing spaces. Payload `cwd` never selects the database.
No global Claude configuration is changed. Do not overwrite an existing project's
settings; the workflow below uses a fresh temporary project.

## Fish smoke test

Prerequisites: installed/authenticated Claude Code, this repository's editable
installation with pytest (`python -m pip install -e '.[dev]'`). Start fish in
the Architect OS repository root. The commands below copy only the small smoke
fixture and the opt-in settings template into a new temporary project.

```fish
set -l architect_repo (pwd)
source "$architect_repo/.venv/bin/activate.fish"
set -gx ARCHITECT_EXECUTABLE "$architect_repo/.venv/bin/architect"
set -l smoke_dir (mktemp -d /tmp/architect-claude-smoke.XXXXXX)
mkdir -p "$smoke_dir/.claude"
cp "$architect_repo/docs/integrations/smoke/README.md" "$smoke_dir/README.md"
cp "$architect_repo/docs/integrations/smoke/test_smoke.py" "$smoke_dir/test_smoke.py"
cp "$architect_repo/docs/integrations/claude-settings.example.json" "$smoke_dir/.claude/settings.json"
cd "$smoke_dir"
architect init
architect run "Claude live observer smoke test" --agent claude --fidelity NATIVE
read -P 'Paste the full Run ID printed above: ' run_id
set -gx ARCHITECT_RUN_ID "$run_id"
claude
```

Accept the smoke folder's normal Claude project trust/hook prompts if requested.
Ask: **Read README.md with Read and run pytest -q with Bash. Do not edit files.**
After Claude finishes, exit Claude and run:

```fish
architect inspect "$ARCHITECT_RUN_ID"
architect status
# Disable the template reversibly after exiting Claude:
mv .claude/settings.json .claude/settings.json.disabled
set -e ARCHITECT_RUN_ID
set -e ARCHITECT_EXECUTABLE
```

Expected: FILE_READ for README.md and TEST_EXECUTION for the direct `pytest -q`
command (or TOOL_EXECUTION if the command uses shell composition). Live-path events
have metadata.synthetic=false, provider=claude, fidelity=NATIVE, and timestamp_source=
hook_received_at. This flag identifies the ingestion path; fixtures can exercise
that path too, so the flag alone is not proof that a real Claude process ran.
Only an actual Claude smoke run closes the milestone.

## Semantics and troubleshooting

SessionStart requires a full existing ARCHITECT_RUN_ID and binds the exact Claude
session ID. Repeats with the same pair succeed; conflicts, prefixes, missing IDs,
and unknown sessions fail. Later tool hooks use the binding without requiring
the environment variable again. No run is inferred or created.

SessionStart produces a binding, not RUN_STARTED: a Claude session can start,
resume, or compact during an existing Architect run. Stop/SessionEnd do not establish
task completion; the live observer ignores them and the template does not install
them. The run remains RUNNING. No automatic closure is implemented.

Read completion records success. Bash events keep status unset because completion
of the tool does not provide a stable, universal test outcome field. Raw tool_response
is retained for audit; output text is not parsed to guess success. PostToolUseFailure
records failed tool_execution with the provider error. Unknown hook names are quiet
no-ops; supported tool events require a known session and valid inputs.

Hook JSON need not contain a timestamp: Architect records UTC receipt time and labels
its origin. Hooks print nothing on success. Ingestion errors print a short stderr
message and exit 1 (not Claude's blocking exit code 2). Errors are not suppressed;
check hook diagnostics if the timeline is empty. The 10-second template timeout can
expire under prolonged database contention; delivery retries are not implemented.

The development checks exercise stdin, storage, and the template shell command but
do not install hooks or need a Claude account. Tool response metadata may include
file content or command output and is stored locally in the project database.

Provider reference checked for implementation: [Claude Code hooks](https://code.claude.com/docs/en/hooks).
