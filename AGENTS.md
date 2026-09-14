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

M0, M1, M2.1, M2.2, and M2.3a are complete. Consult `docs/ROADMAP.md` and `docs/integrations/codex.md`. Do not start live Codex transport automatically.

Do not implement global Claude hook installation, Codex telemetry ingestion, NotebookLM, Repo Map, Context Compiler, Chronicle intelligence, benchmark engine, labs runtime, multi-agent orchestration, or a web UI yet. See `docs/ROADMAP.md`.

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
