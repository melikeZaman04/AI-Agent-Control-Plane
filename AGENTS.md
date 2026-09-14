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

M0 through M2.3b and M3–M6 are complete. Continue the existing M7 roadmap under
A3; M2.4 remains deferred. Live observation remains explicit and foreground.

## Roadmap Execution

Current autonomy level: **A3 — Roadmap Autonomy**; A4 is disabled. Read
`docs/EXECUTION_PROTOCOL.md`. Complete parent milestones, record evidence, create
local checkpoint commits and continue automatically across existing milestone
boundaries. Derive conservative exit criteria from the canonical contract.
Human Decision Gates remain active for material decisions; missing checklists
alone do not require approval. Stop at a real gate or the documented roadmap end.
Push only under the protocol's verified-safe conditions; otherwise continue locally.

Do not introduce unrelated milestones, global hooks, passive/background observation,
automation scheduling, multi-agent runtime orchestration or a web UI. Optional
NotebookLM and handoff remain deferred unless the canonical scope requires them.
Implement Context Economy, benchmarking and labs only in their roadmap order.

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
