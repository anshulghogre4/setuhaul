# AI chat primitives

> Documents the U56 adoption of assistant-ui as the binding target for chat rendering. Read alongside
> `components.md` for chat-adjacent surfaces (`01-driver-chat`, `02-ops-exception-console`).

## What's adopted, and why

**assistant-ui** (assistant-ui.com), MIT-licensed. Adopted for the same reason as shadcn/ui (U51) and
Kibo UI Gantt (U52): it composes as source through a CLI rather than as an opaque runtime dependency, so
it inherits our tokens and both themes instead of imposing its own. Confirmed React 18/19 compatible,
which matches the existing frontend stack exactly (`frontend/package.json` — read only as a compatibility
fact, not as scope to redesign).

The alternative — hand-building thread management, message rendering, tool-call display, and a composer
from scratch — means re-deriving problems this library has already solved well: message virtualization at
scale, accessible composer behaviour, and a clean seam between "structured tool output" and "free text,"
which is precisely the seam this product's correctness depends on (README principle 3: *the interface
renders receipts; it never reasons*).

**This file names the fit. It does not choose a backend.** assistant-ui bundles runtime/adapter options
(LangGraph, Vercel AI SDK, custom `LocalRuntime`/`ExternalStoreRuntime`, Data Stream Protocol). Which one
connects to our backend is the tech-stack document's decision — `SOLUTION_DESIGN.md` §9.3 already
describes a custom LangChain `bind_tools` + bounded manual loop, and reconciling that against assistant-ui's
adapter options belongs there, not here.

---

## Primitive-to-decision map

The concrete payoff of this file. Every chat decision already locked in the README binds to a specific
assistant-ui primitive — nothing here is a new decision, this is where existing ones land.

| assistant-ui primitive | Binds to | Decision |
|---|---|---|
| `ThreadListPrimitive` / `ThreadListItemPrimitive` | Thread-list-to-conversation home screen; resolved threads stay in the list, visually muted | Locked in the driver-chat architecture round |
| `MessagePrimitive` | The three-tier sender attribution (driver / assistant / operations) | U47 |
| `MessagePartPrimitive` | **Option cards** and the **decision receipt**, rendered as tool-call output — never as free text the model composed | U48, `components.md` §4 |
| `SuggestionPrimitive` | The composer's contextual quick replies | U49 |
| `ComposerPrimitive` | The free-text input itself | U49 |
| `ErrorPrimitive` | `CONNECTION_LOST` and load/write-failure copy | `voice-and-tone.md` |
| `AssistantSidebar` | **The ops co-pilot** — summarise-thread, fetch-context, draft-reply-for-approval | U57 |

### Why tool-call rendering is the load-bearing mechanic

`MessagePartPrimitive` distinguishes text parts from tool-call parts. **Every option set, every decision
receipt, and every system-initiated state change renders as a tool-call part, never as generated text
that happens to look structured.** This is what turns "the assistant narrates the receipt, it never
invents the reasoning" (§7.2b) from a discipline someone has to remember into an architectural property:
`find_feasible_slots`, `request_slot`, and `confirm_held_slot` results flow into the transcript as typed
tool results, and the rendering component for each is fixed in advance — an option card, a promise-state
chip transition, a receipt. There is no code path where the model free-types what a slot looks like.

The same mechanic is what U50 (system events mutate the affected card in place) relies on: the withdrawn
option's card doesn't get a new bubble, its existing tool-call-rendered part updates state, exactly the
way `MessagePartPrimitive` is built to be re-rendered on data change rather than re-sent as a new message.

---

## The ops co-pilot (U57)

Newly in scope this checkpoint, grounded directly in §7.4:

> *"The assistant stays available to the human as a co-pilot — summarise the thread, fetch context, draft
> a reply for approval. That is the ops-side assistant use case, and it is where the LLM adds the most
> value per token in this whole product."*

Built on `AssistantSidebar`, with three capabilities and one hard scope boundary:

| Capability | Behaviour |
|---|---|
| **Summarise thread** | On-demand, not automatic. Condenses the active takeover thread's history into a few lines an ops coordinator can act on without re-reading a long transcript. |
| **Fetch context** | Pulls shipment, appointment, and ETA history into the sidebar without the coordinator leaving the console — the same data a driver-facing tool call would return, surfaced for the human instead. |
| **Draft reply for approval** | The LLM proposes a reply; the human edits or sends. **Never auto-sends.** This extends D6's "no rules-based auto-confirm" logic to co-pilot output — a drafted message is a suggestion, not an action, until a human commits it. |

**Scope boundary: available only on threads under human takeover** (`chat_threads.thread_status =
'ESCALATED'`). This is deliberately not a general "chat with the AI" feature bolted onto the ops console —
it activates exactly where §7.4 says it earns its value, on the threads a human has already taken over,
where drafting and context-fetching save real time. Outside takeover, ops coordinators work the queue
(`02-ops-exception-console/`), not a chat interface.

---

## Explicitly not adopted for v1

Stated so a later reader doesn't wonder whether these were missed rather than declined.

| Capability | Why not now |
|---|---|
| **Voice controls** (realtime bidirectional voice, TTS/dictation) | Maps to `SOLUTION_DESIGN.md`'s COULD-item C6 (voice intake) — real value, no dependency, explicitly deferred there |
| **Message branching / regeneration** | Doesn't fit this domain. A general chatbot regenerates a response the user didn't like; this assistant's option ranking is server-side, deterministic, and never re-rolled on request (§5) — there is nothing to "regenerate" without breaking the determinism guarantee (M4) |
| **MCP tool-catalog integration** | A backend/tool-surface concern, not a rendering concern — belongs with the §7.5 tool-contract work, not the UI layer |
| **File attachments** | Nothing in the driver conversation model involves the driver sending files; if a future case needs a photo (e.g. proof of a breakdown), it's a new product requirement first, a UI primitive second |
| **Slash commands / @-mentions** | Would reopen the exact ordinal-style shortcut problem U16 deliberately closed — a hidden syntax a driver could get wrong under stress |

---

## Styling

assistant-ui's pre-built components ship in a "shadcn-style" flavour — consistent with U51. **None of its
default visual styling is used.** Every colour, spacing, radius and type value comes from
`00-foundations/{color,typography,spacing-and-layout}.md`; assistant-ui supplies behaviour and
accessibility (focus management, keyboard interaction within the composer, virtualization for long
threads), not appearance.
