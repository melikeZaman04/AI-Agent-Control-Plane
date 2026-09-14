# Architect OS Roadmap

## M0 — Foundation

Deliver the repository contract, architecture/product/roadmap documentation, package metadata, SQLite projects/runs/events storage, CLI foundation, `architect init`, tests, and documentation. Exit criteria: `architect init`, `architect run`, and `architect status` work; tests pass; architecture is documented.

**Status:** COMPLETE.

## M1 — Flight Recorder Core

Define the provider-independent normalized event contract before provider integrations.

**Status:** COMPLETE. Implementation includes normalized events, atomic lifecycle recording, deterministic timelines, and `architect inspect` with full ID or unique prefix lookup. M0 regressions and M1 tests pass; isolated CLI validation succeeded. Do not begin M2 automatically.

## M2 — Observer Integration

Add Claude, Codex, and passive observers that translate provider evidence into normalized Architect events.

**Status:** IN PROGRESS.

- M2.1 Observer Foundation — COMPLETE: synthetic Claude normalization, session/run bindings, synchronous ingest, and isolated pipeline tests.
- M2.2 Live Claude Integration — COMPLETE: stdin CLI, live-format normalization, opt-in hook template and automated tests implemented. User-performed live smoke test confirmed FILE_READ and TEST_EXECUTION in Architect inspect; see `docs/integrations/claude.md` for evidence.
- M2.3a Codex Observer Foundation — COMPLETE: synthetic OTel-style normalization, Codex session/run correlation, privacy filtering, end-to-end SQLite inspection, and transport design. Live transport is not included; see `docs/integrations/codex.md`.
- M2.3b Live Codex Transport — PLANNED: validate the native OTLP envelope and implement the approved receiver option.
- M2.4 Passive Observer — LATER, if still justified.

M2.2 installation is explicit and project-local. Do not start M2.3 automatically.

## M3 — Project Chronicle

Build project timelines, change and decision history, automation receipts, and failure records.

## M4 — Session Intelligence

Build status, changes, day, resume, explain, and later optional handoff workflows.

## M5 — Context Economy

Build bootstrap memory, Git HEAD tracking, incremental indexing, a repo map, targeted retrieval, context metrics, and a knowledge-provider boundary. NotebookLM remains optional; the repository remains ground truth.

## M6 — Research / Benchmark

Build evaluation suites, repeatable runs, model and context-strategy comparisons, and token/context metrics.

## M7 — Learn / Labs

Build a failure corpus, controlled scenarios, hidden failures, success criteria, and progress tracking.

Do not implement M1–M7 during M0.
