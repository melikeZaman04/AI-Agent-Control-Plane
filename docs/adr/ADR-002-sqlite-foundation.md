# ADR-002: SQLite foundation

## Decision

SQLite is the primary MVP metadata store, with foreign keys enabled and WAL journaling.

## Reason

The current single-user, local-first architecture does not justify external infrastructure.
