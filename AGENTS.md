# Architect OS — Agent Instructions

## What this project is

Architect OS is a local-first AI Agent Control Plane. It does not replace Codex, Claude Code, Gemini, Qwen, or other coding agents. It will observe agent runs, preserve project history, manage project context, explain changes, resume interrupted work, and benchmark agents and context strategies.

Read `docs/ARCHITECTURE.md` before architectural changes.

## Product Modes

- BUILD — develop real projects with coding agents.
- LEARN — run controlled engineering labs.
- RESEARCH — benchmark models, context strategies, and architecture decisions.

Do not mix these responsibilities without an explicit reason.

## Current Milestone

M0 through M2.3b and the entire M3 Project Chronicle milestone are complete.
M2.4 remains deferred. No M4 implementation is authorized; await human approval.
See `docs/ROADMAP.md` and `docs/milestones/M3.md`. Live Codex observation remains
explicitly started in the foreground.

## Milestone Execution

Current autonomy level: **A2 — Milestone Autonomy**. For milestone work, read
`docs/EXECUTION_PROTOCOL.md`. Routine implementation decisions do not require
human confirmation. Its Human Decision Gates require stopping affected work.
The approved boundary is the M3 parent milestone. Do not stop for routine approval
between M3.x tasks. Stop before M4. Do not commit or push.

Do not implement global Claude hook installation, background telemetry services, passive observation, NotebookLM, Repo Map, Context Compiler, Chronicle intelligence, benchmark engine, labs runtime, multi-agent orchestration, or a web UI yet. See `docs/ROADMAP.md`.

## Engineering Rules

1. No overengineering.
2. Git is ground truth.
3. Prefer deterministic methods.
4. Preserve observer fidelity.
5. Context economy must not reduce correctness.
6. Prefer SQLite and JSONL to external infrastructure.
7. Do not duplicate agent-native capabilities.

## Sources of Truth

- Current code: repository and Git
- Product intent: `docs/PRODUCT.md`
- Architecture: `docs/ARCHITECTURE.md`
- Roadmap: `docs/ROADMAP.md`
- Terminology: `docs/GLOSSARY.md`
- Architecture decisions: `docs/adr/`
- Labs: `labs/README.md`

## Before Changing Code

1. Identify the current milestone.
2. Read the relevant specifications.
3. Inspect the existing implementation.
4. Make the smallest viable change.
5. Add or update tests.
6. Run affected tests.
7. Explain what changed and why.
