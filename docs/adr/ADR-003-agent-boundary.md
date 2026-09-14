# ADR-003: Agent boundary

## Decision

Architect OS does not reimplement agent-native capabilities unless required.

## Reason

Agent providers retain ownership of conversations, sandboxes, permission mechanisms, and native tool execution. Architect focuses on observation, normalization, project memory, audit, and evaluation.
