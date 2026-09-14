---
name: architect-milestone-runner
description: Advance an explicitly approved Architect OS milestone using the repository execution protocol, from state audit through implementation and exit validation.
---

Read the repository's `AGENTS.md` and [execution protocol](../../../docs/EXECUTION_PROTOCOL.md).
Discover the approved current milestone and exit criteria in `docs/ROADMAP.md`;
completion of the previous milestone is not approval for a new one.
Execute the protocol's bounded task, test, self-review and repair loop without
routine confirmation. Obey its Human Decision Gates and preserve existing changes.
Verify exit criteria against actual evidence and update canonical docs. When the
human approves a parent milestone, continue through its submilestones without
routine confirmation and stop at the parent boundary. Read the current approved
boundary from AGENTS.md, ROADMAP and the user's instructions; never cross into
the next major milestone automatically. Do not commit or push without explicit
authorization.
