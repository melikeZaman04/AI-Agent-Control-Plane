# Architect OS Glossary

This document defines the canonical language used across Architect OS.

## Agent

An external coding agent—such as Codex, Claude Code, Gemini, or Qwen—that owns its conversation, native tools, permissions, sandbox, and provider session behavior.

## Architect OS

The local-first control plane above coding agents. Architect observes and normalizes available evidence, maintains project-level history, and supports future context and evaluation workflows.

## Project

A repository or working directory registered with Architect OS. Its local runtime state lives under `.architect/`.

## Run

A tracked unit of agent work with an agent name, task, fidelity level, status, and timestamps. A run may contain many events.

## Session

A provider-owned interaction context between a user and an agent. A session and an Architect run are not necessarily the same unit or duration.

## Provider-session binding

A project-local mapping from the exact `(provider, provider_session_id)` pair to an existing full Architect run ID. Rebinding the pair to another run is a conflict. Separate provider namespaces may use the same session ID.

## Event

A timestamped observation associated with a run, such as a tool call, file activity, test result, or error. An event records evidence; it must not claim activity that was not observed.

`ArchitectEvent` is the M1 normalized contract. It has an event ID, run ID, timezone-aware timestamp, event type, optional provider/fidelity/actor/tool/target/status/duration, and JSON metadata. Its vocabulary is `run_started`, `run_finished`, `tool_execution`, `file_read`, `file_changed`, `test_execution`, `approval_requested`, and `error`. Event IDs identify normalized observations; SQLite insertion IDs break timestamp ties. Event status (pending/success/failed/blocked) is distinct from run status.

## Observer

A provider-specific or passive mechanism that collects available evidence and translates it into Architect's normalized event form.

## Observer Fidelity

The strength of evidence available to an observer:

- **NATIVE** — provider-supported hooks or telemetry.
- **SESSION_LOG** — provider-local transcripts or session files.
- **PASSIVE** — Git, filesystem, or process-output observations.

## Flight Recorder

The subsystem that accepts normalized events and stores an auditable record of agent runs and observable activity.

## Project Chronicle

The evidence-backed project timeline built from runs, changes, decisions, failures, automations, and test history.

M3.1 implements a **Chronicle Episode**: a deterministic run-scoped piece of
project history derived from local run metadata and normalized events.
An **Observation Fact** counts observations with the same normalized type,
status, provider and fidelity, preserving all supporting ArchitectEvent IDs.
These counts describe observed events, not unique tool invocations or inferred outcomes.
**Evidence inspection** resolves an episode's supporting ArchitectEvent ID within
its project and run to the original normalized source record; it adds no facts.

## Change history

Deterministic committed Git history: commit identity, committer time and changed
paths, with provenance to the corresponding Git trees. It does not imply a run
caused a commit and excludes uncommitted working-tree content.

## Durable decision history

Version-controlled ADR document revisions with commit/path/blob evidence. Tool
approval events remain operational observations; no durable decision is inferred
from ordinary activity or an ADR's acceptance status guessed from its existence.

## Work receipt

A structured, query-time record of a terminal or observed run, retaining run-row
and event provenance. It preserves known outcomes and unknowns; existence of a
receipt alone does not imply success or completion.

## Automation receipt

A work receipt explicitly identified as automated by the lifecycle metadata
contract in ADR-005. Provider identity and agent activity do not establish this.

## Failure record

An explicit failed run, normalized error observation or failed tool/test event,
linked to its source. It records no inferred cause or explanatory narrative.

## Context Economy

The practice of reducing repeated repository rediscovery and unnecessary context usage without sacrificing correctness.

## Autonomy Level

The scope of decisions delegated to an agent: **A0 Manual** (human specifies
steps), **A1 Task Autonomy** (one bounded task), **A2 Milestone Autonomy** (tasks
inside an approved milestone), **A3 Roadmap Autonomy** (move between milestones),
**A4 Product Autonomy** (alter product direction). Current level is A3; A4 remains disabled.

## Milestone Autonomy

Agent-controlled decomposition, implementation and validation inside human-approved
scope and exit criteria. Execution behavior belongs to `EXECUTION_PROTOCOL.md`.

## Human Decision Gate

A documented condition requiring the agent to stop affected work for a human
decision; canonical triggers are in `EXECUTION_PROTOCOL.md`.

## Exit Criteria

Observable conditions that must all be satisfied before declaring a milestone complete.

## Repair Loop

One meaningful failure → investigation → change → retest cycle for a blocking problem.

## Context Compiler

The M5 local context assembly capability combines canonical bootstrap files and targeted source retrieval with provenance and explicit budgets. More advanced selection strategies remain experiments, not accepted capabilities.

## Repository Ground Truth

The current working tree and Git history. Runtime state and future knowledge providers may supplement but never override it.

## BUILD

The product mode for developing real projects with coding agents.

## LEARN

The product mode for controlled engineering labs and deliberate failure scenarios.

## RESEARCH

The product mode for comparing agents, context strategies, and architectural decisions.

## Session Intelligence

Deterministic evidence-backed status, changes, day, resume and explain reports.
A resume report preserves recorded state; it does not execute a provider resume
or invent a plan. An explain report exposes evidence, not an inferred cause.

## Repo Map and Context Bootstrap

A Repo Map is a deterministic inventory of tracked working-tree paths, content
hashes and available symbol locations. A Context Bootstrap combines canonical
entry files and targeted source ranges with hashes, budget metrics and omissions.
Token estimates are labeled approximations, never reported provider usage.

## Knowledge Provider

A source interface for targeted search and exact evidence-linked reads. The local
repository implementation is authoritative; optional external sources cannot
replace current Git/source evidence.

- **Benchmark suite:** Explicit RESEARCH cases with declared agent/model labels,
  argv, bounded repetitions/timeouts and deterministic exit/output predicates.
- **Benchmark receipt:** Observed trial metrics and hashes, not a claim of model
  quality. Token usage is command-reported; context token counts are estimates.

- **Lab scenario:** Versioned LEARN instructions, faulty source fixture and
  deterministic success criteria, separate from real BUILD work.
- **Hidden lab check:** Acceptance code withheld from the initial learner workspace;
  inspectable in the corpus, not a security secret.
- **Lab progress:** Ordered explicit check receipts and current-source match flags;
  historical success does not establish current correctness or learner mastery.
