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
```

For product intent, architecture, terminology, and development order, see [`docs/`](docs/).
