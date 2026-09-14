# Architect OS

Architect OS is a local-first control plane for observing AI coding-agent runs and preserving project history. It sits above coding agents; it does not replace them.

M0 provides local SQLite storage for projects, runs, and events, plus the `architect` CLI.

## Installation

Architect OS requires Python 3.11 or newer.

```bash
python -m pip install -e '.[dev]'
```

## Usage

Run these commands from the project you want Architect OS to track:

```bash
architect init
architect run "Describe the task" --agent codex --fidelity NATIVE
architect status
architect chronicle
architect chronicle --json
architect chronicle --run <full-run-id>
architect chronicle --run <full-run-id> --event <evidence-event-id> --json
```

`chronicle` reads the initialized current project's history without changing it.
Run and evidence IDs are exact, full identifiers. JSON listing returns an array
of episodes; `--event` returns one original normalized event, including its
stored metadata. Evidence IDs appear in both text and JSON listings.
An initialized project without runs returns `[]` in JSON mode. Errors go to
stderr with a nonzero exit status and no partial JSON on stdout.

For product intent, architecture, terminology, and development order, see [`docs/`](docs/).

## Historical views (M3)

```bash
architect chronicle --view changes --json
architect chronicle --view decisions --revision HEAD --json
architect chronicle --view receipts --run <full-run-id> --json
architect chronicle --view automations --json
architect chronicle --view failures --json
```

Changes and ADR revisions come from committed Git history, independently of
run observations. For pinned queries, use a full commit ID with `--revision`.
Merge paths compare against the first parent; deleted ADR records cite prior
content. Source files can be resolved with
`GitHistory(root).file(source_commit_id, path)` or inspected directly in Git.
Receipts/failures cite source runs and events; use the existing `--run ... --event
... --json` command for event evidence. Empty results are valid: no observed
failure or explicit automation must not be invented. Current providers do not
emit the optional automation declaration described in ADR-005.

## Session reports (M4)

```bash
architect session status --json
architect session changes --since <baseline-commit> --json
architect session day --date 2026-09-15 --timezone Europe/Istanbul --json
architect session resume --run <full-run-id> --json
architect session explain --run <full-run-id> --event <event-id> --json
```

These commands only read evidence; resume does not launch an agent and explain
does not invent causes or recommendations. Omit `--run` on resume to select the
latest recorded start (unknown starts first, full run ID breaks ties).

## Local context (M5)

```bash
architect context index
architect context map
architect context search --query recorder --limit 5
architect context read --path src/architect/recorder/recorder.py --start 1 --end 20
architect context bootstrap --query recorder --max-chars 12000
```

Only regular tracked UTF-8 source files up to 1 MiB are indexed; newly staged files
qualify, untracked files do not. Reads reject stale content or removed Git index
membership. Index metadata stays in `.architect`; full file bodies remain in the
repository. Bootstrap budgets/estimates count source text only and disclose omissions.

### Local research benchmarks (M6)

Run only trusted commands: the POSIX runner provides fresh Git workspaces, not a
security sandbox. Initialize the project and commit tracked changes first.
Create a suite JSON, for example:

```json
{"version":1,"cases":[{"id":"smoke","task":"local-smoke","agent":"fixture",
"model":"python","argv":["python3","-c","print('OK')"],"repeats":2,
"timeout_seconds":10,"expected_exit":0,"stdout_contains":"OK",
"context":{"strategy":"none"}}]}
```

```sh
architect benchmark run suite.json
architect benchmark compare .architect/benchmarks/<receipt-id>.json
```

Use context strategy `bootstrap` with optional `query` and `max_chars`;
argv placeholder `{context_file}` receives a temporary JSON bundle path.
Each repetition uses the same pinned committed regular-file snapshot. Keep the
original suite to resolve its recorded hash. Agent/model labels are declarations.
Optional stdout JSON `{"usage":{"input_tokens":11,"output_tokens":3}}` supplies
command-reported counts; absent counts stay unknown. Predicates check expected
exit and optional substring (stdout at most 1 MiB). A successfully recorded suite
exits zero even when trials fail; inspect each `passed` value. Comparison keeps
distinct suite/source/case/agent/model/strategy groups; elapsed time is measured,
not deterministic, and synthetic smoke results are not real model benchmarks.

### Controlled learning labs (M7)

```sh
architect lab list
architect lab start retry
architect lab check <lab-id>
architect lab progress <lab-id>
```

Edit the returned workspace to repair the exercise. Checks use real temporary
copies and record explicit pass/failure evidence; progress flags subsequent edits.
The bundled `retry` and `cache` scenarios run trusted local Python, with user
permissions. See [Labs](labs/README.md) for contracts and limits.
