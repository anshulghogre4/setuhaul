---
title: SetuHaul LLMWiki Maintainer Schema
type: schema
status: authoritative
scope: wiki/
last_updated: 2026-08-07
---

# SetuHaul LLMWiki maintainer schema

This wiki follows the LLMWiki pattern used by Slicematic.

## Layer model

1. **Source evidence:** code, SQL, migrations, tests, configuration, plans, and authored project documentation. Wiki-only work must not alter evidence to make a summary appear correct.
2. **Compiled wiki:** `wiki/*.md`. Agents maintain synthesis, links, provenance, current state, and contradictions here.
3. **Schema:** this file and root `AGENTS.md`. These define the operating loop.

## Required startup sequence

1. Query the Memory MCP for the SetuHaul project context when the server is available.
2. Read [[index]] and [[handoff]].
3. Read [[current-state]] and [[contradictions]] when correctness or risk matters.
4. Read the Living sprint status in `plans/implementation-master-plan.md` and note Sprint 1 vs Sprint 2 vs Sprint 3 before new work (canonical cross-IDE scoreboard; see root `AGENTS.md`).
5. Use [[source-map]] to select topic pages and verify implementation-critical claims against source evidence.
6. Inspect `git status --short` and preserve teammate changes.

If Memory MCP is unavailable, continue from the checked-in wiki and record the degraded state; never pretend memory was loaded.

## Ingest operation

When source evidence changes:

1. Identify affected concepts and existing pages.
2. Read the evidence; do not infer behavior from names alone.
3. Merge facts into existing pages instead of creating duplicates.
4. Add or repair related wiki links.
5. Update verification metadata.
6. Record conflicts in [[contradictions]].
7. Update [[index]] only when navigation changes.
8. Append a parseable entry to [[log]].
9. Refresh [[handoff]].

## Query operation

1. Search [[index]] and relevant topic pages first.
2. Use compiled synthesis for orientation.
3. Verify security, database, migrations, auth, current test/build status, and other high-risk claims against source or a fresh command.
4. Cite repository paths.
5. Write durable new analysis back to the relevant page and [[log]].

## Lint operation

Check for stale or contradictory claims, orphan/duplicate pages, missing provenance, unresolved contradictions, broken wiki links, missing reciprocal links, and secrets copied into Markdown.

## Page conventions

- One concept per page; synthesize across files instead of mirroring them.
- New pages use YAML frontmatter with title, type, status, scope, and last verification/update date.
- Use Obsidian-style concept links (for example, `[[architecture]]`) and repository paths for evidence.
- Label claims as verified, inferred, historical, or unresolved when ambiguity matters.
- Never copy credentials or secret values.
- `log.md` and root `CHANGELOG.md` are append-only.

## Memory MCP loop

- **Start:** query the `memory` MCP for entities/relations relevant to SetuHaul and the current task.
- **During:** store only durable decisions, verified architecture facts, blockers, and stable team preferences. Never store credentials, raw sensitive records, or speculative claims as facts.
- **End of every prompt:** run the context-sync check. For any durable prompt, append/update concise project memory covering outcome, key decisions, verification, blockers, and next action before the final response.
- Checked-in source and wiki win when Memory MCP is stale or contradictory; correct memory and record the reconciliation in [[log]].

## Per-prompt context sync

A durable prompt changes files, implementation state, requirements, decisions, blockers, research conclusions, or verification status. Before answering it:

1. Update the affected concept pages.
2. Refresh [[handoff]].
3. Append [[log]].
4. Append root `CHANGELOG.md`.
5. When implementation progress changed, update `plans/implementation-master-plan.md` Living sprint status and checklist strikethrough with dated evidence (never strike an exit gate without full gate proof).
6. Synchronize Memory MCP when available.

Pure read-only conversation that produces no durable context does not create empty entries. Memory MCP complements rather than replaces the checked-in wiki.

## Definition of done

A material task is not complete until affected topic pages, [[handoff]], [[log]], root `CHANGELOG.md`, the master-plan Living checklist (when progress changed), and Memory MCP (when available) agree with the resulting source state.
