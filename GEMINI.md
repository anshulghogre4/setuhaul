# SetuHaul instructions for Gemini CLI and Google Antigravity

@./AGENTS.md

Gemini CLI and Google Antigravity must treat the imported root `AGENTS.md` as the canonical repository policy. At session start, complete its required startup sequence before material work, including reporting Living sprint status from `plans/implementation-master-plan.md`.

At the end of every user prompt, run the root context-sync check. Before answering any prompt that changed files or durable project context, atomically update `CHANGELOG.md`, affected LLMWiki pages, `wiki/handoff.md`, `wiki/log.md`, the Memory MCP, and—when implementation progress changed—the master-plan Living sprint checklist (strike verified items with dated evidence). If memory is unavailable, record that degradation in the handoff. Pure no-op conversation does not create empty log entries.

Use nested `GEMINI.md` files only for genuinely narrower directory rules. Never duplicate or weaken the root safety, verification, memory, or writeback requirements.
