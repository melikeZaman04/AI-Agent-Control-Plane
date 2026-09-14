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

## Context Economy

The practice of reducing repeated repository rediscovery and unnecessary context usage without sacrificing correctness.

## Context Compiler

A future deterministic-first subsystem that will assemble task-relevant context from bootstrap information, repository maps, targeted retrieval, and exact source. It is not part of M0.

## Repository Ground Truth

The current working tree and Git history. Runtime state and future knowledge providers may supplement but never override it.

## BUILD

The product mode for developing real projects with coding agents.

## LEARN

The product mode for controlled engineering labs and deliberate failure scenarios.

## RESEARCH

The product mode for comparing agents, context strategies, and architectural decisions.
