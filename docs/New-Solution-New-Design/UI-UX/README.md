# SetuHaul UI/UX — design system and surface specifications

## What this is

The interface design for **SetuHaul Dock Command**, specified to buildable depth. The product
specification is [`../SOLUTION_DESIGN.md`](../SOLUTION_DESIGN.md); this folder does not restate it, and
where the two disagree the solution design wins on *what the system does* while this folder wins on *what
it looks like and how it behaves*.

Everything here is grounded in the spec. Where a design choice follows from a product requirement, the
section is cited (§7.2b, §7.3). Where a choice is aesthetic, it says so plainly rather than dressing
preference as necessity.

---

## The six principles

These are not generic design values. Each one falls out of something specific in the solution design, and
each one would change the interface materially if reversed.

### 1. Promise state is the primary visual language

`SHOWN` → `HELD` → `PENDING_CONFIRMATION` → `CONFIRMED` is the spine of the product (§4). A driver who
reads "held for 90 seconds" as "booked" has been mis-promised, and §7.2b is explicit that this is a
business failure, not a wording nit. So state gets **four redundant encodings** — colour, icon, label and
border treatment — and only `CONFIRMED` may use finality language or success visuals.

Border treatment does real work here: **dashed means temporary, solid means committed**. Permanence is
encoded in the shape, so it survives greyscale, colourblindness and a two-second glance.

### 2. Two components expire while you are looking at them

`HELD` burns ~90 seconds. `PENDING_CONFIRMATION` burns 15 minutes (D9). Almost no enterprise UI has a
component whose meaning changes if the user hesitates, and it drives an unusual amount of this system:
tabular numerals so countdown digits do not jitter, urgency escalation as time runs out, haptic warning
before a driver's hold lapses, and a designed expiry state rather than a component that simply vanishes.

### 3. The interface renders receipts; it never reasons

Score terms arrive as structured data — `CRITICAL · 70 min late · exact dock · 0 min wait`. The UI
displays them. It never computes a ranking, never compares options itself, never explains a decision it
inferred (§5, §7.2b). This is why there is a *receipt* component rather than an *explanation* component:
the distinction is load-bearing, and a UI that appears to reason invites a user to argue with it.

### 4. One system, three hostile ergonomic contexts

A driver at the roadside — glare, one hand, cheap Android, poor signal, and a bad day. A gate officer
outdoors in gloves. A planner at a desk under time pressure with a 30-second decision budget (§7.3).
These are not "mobile, tablet, desktop." They are different physical situations, and the same token set
is calibrated three ways rather than fragmented into three design languages.

### 5. Failure paths are the real product

§7.2b names eight negative-path states as mandatory; §12.2 explicitly requires demonstrating what happens
when an option changes or disappears. Hold lapsed, option withdrawn, no same-day slot, conflict lost,
pending expired, escalation raised, human joined — these get more design attention than the happy path,
because the happy path is a driver tapping a card and this product exists for when that does not work.

**Every failure state names a cause and a next action.** A refusal without a route is a dead end (§7.2),
and dead ends are what drive drivers back to phone calls.

### 6. Never move the target under the click

Requests arrive during a spike, TTLs run down, options are withdrawn mid-conversation. Data must stay
live — but a queue that re-sorts while a planner is deciding will cause a wrong confirm, and confirming
the wrong request silently hurts a third party. **Values update live; ordering freezes on focus** and
re-sorts only when the user asks.

---

## Decisions log

Locked with the owner, 2026-08-19. Numbered `U-*` so they can be cited from the surface documents without
colliding with the solution design's `D-*` series.

### Document structure

| # | Decision |
|---|---|
| U1 | All **six v1 surfaces** are specified — driver, ops, planner, gate, carrier, admin |
| U2 | Both **foundations and screen specs**, foundations first |
| U3 | Deliverable is **markdown with ASCII wireframes** — reviewable in-repo, no rendering dependency |
| U4 | Each surface folder decomposes **by concern**: `screens` · `components` · `flows-and-states` · `edge-cases` · `accessibility` |
| U5 | Foundations split by concern under `00-foundations/` |
| U6 | Specified to **buildable depth** — a developer could implement from these files |

### Visual language

| # | Decision |
|---|---|
| U7 | **Light and dark at full parity.** Drivers in glare need light; control rooms prefer dark. Both are real. |
| U8 | **Adaptive density, one token set** — comfortable / compact / spacious calibrations of the same system |
| U9 | **Inter** for UI, **JetBrains Mono** for IDs, timestamps and countdowns |
| U10 | **Hue is reserved for promise state and genuine danger.** Priority encodes as a border marker, ETA confidence as an icon, dock status as pattern. Seven dimensions competing for colour would produce a rainbow; the one that must never be misread wins. |
| U11 | **Lucide** icons |
| U12 | **Intent-based button variants** — constructive / neutral / cautionary / destructive, named by consequence rather than appearance |
| U13 | **Functional motion only.** Every animation carries meaning; nothing is decorative. |
| U14 | State encoded by **colour + icon + label + border treatment** |

### Platform and interaction

| # | Decision |
|---|---|
| U15 | **WhatsApp is out of v1.** The driver surface is a PWA only. See "Spec divergence" below. |
| U16 | **Tappable option cards only — ordinals are eliminated.** §7.2b's ordinal trap is designed out of existence rather than defended against. |
| U17 | Outbound events reach drivers by **web push + in-app inbox**. ~~SMS reserved for capacity-loss events~~ — **SMS dropped from v1 (revised 2026-08-20, U121)**; the four capacity-loss/decision-against events now get high-priority push instead |
| U18 | Driver surface is **chat as the spine with rich cards inside the transcript** |
| U19 | **Live data, sort frozen on focus** |
| U20 | **Per-surface breakpoint targets**, shared token scale — each surface declares the range it actually supports |
| U21 | **Haptics on driver and gate; no audio anywhere.** Warehouses are loud, offices are shared. |
| U22 | Component specs are **implementation-agnostic**; binding to a library is the tech-stack doc's job |

### Surface architecture

| # | Decision |
|---|---|
| U23 | **Ops and planner share one queue component**, differing by scope and permissions — not two separate builds |
| U24 | Planner queue is a **dense table with detail-peek on focus** |
| U25 | Dock board is **read + act via affordances — no free dragging.** A drag that produces an unvalidated schedule contradicts §5.1. |
| U26 | Gate kiosk is **search-then-act, one truck at a time** — only currently-valid actions are offered, so events cannot be recorded out of order |
| U27 | Admin policy editing **simulates against real history before publish** — "under these weights, SHP1014 loses to SHP1009" |
| U28 | Carrier portal shows **own fleet status and own on-time performance** — never cross-carrier comparison (M15) |
| U29 | **Auth is a shared pattern** in foundations, not repeated per surface |

### Quality bar

| # | Decision |
|---|---|
| U30 | **WCAG 2.2 AA baseline, plus a deliberate AAA overlay on field surfaces.** Precisely: SC 2.5.8 Target Size (Minimum) is **24×24px at AA** — the **44×44px** target used on driver and gate is SC 2.5.5 Target Size (Enhanced), which is **AAA**. We are choosing to exceed AA there because of gloves and glare, not because AA requires it. Written this way so nobody later "optimises" the kiosk to 24px believing it still conforms to our stated bar. Plus: sunlight-tested contrast on driver and gate, full keyboard operation for planner, never colour alone for state. |
| U31 | **English UI, i18n-ready structure** — copy externalised, layouts tolerate ~30% expansion, locale-formatted dates and numbers |
| U32 | **Every empty, loading and error state names a cause and a next action** |
| U33 | **Charting is minimal** — carrier on-time sparkline and planner queue-depth only. Full KPI analytics defers with its personas (§2). |

### App shell and interaction patterns

| # | Decision |
|---|---|
| U39 | **Icon rail (56px) + thin top bar**, not a labelled sidebar — the planner's 7-field row needs the horizontal space |
| U40 | **Persistent facility switcher + a per-facility accent stripe.** Spends one non-semantic colour slot deliberately: confirming into the wrong facility is exactly the error worth ambient signalling. |
| U41 | **No confirmation modals. A 5-second undo window instead**, during which the driver notification is queued and unsent. The irreversible act is the message to the driver, not the database write — so we delay that rather than interrupt a 30-second decision. |
| U42 | **Reject = pick typed reason → preview the driver's exact message → send.** Nobody sends copy they haven't read. Optional internal note the driver never sees. |
| U43 | **A status bar, not a footer** — connection, last sync, active facility, pending count, policy version |
| U44 | **Inline row expansion** for detail, never an overlay — the planner never loses their place in the queue |
| U45 | **Toasts bottom-left**, stacked max 3. Undo persists its full countdown; errors persist until dismissed. |
| U46 | **Single-key actions on the focused row** — `C`/`R`/`O`/`H`/`E`, no modifiers |

### Chat surface

| # | Decision |
|---|---|
| U47 | **Three visual tiers + an explicit takeover marker.** When `OPERATIONS` first posts, a divider announces a person joined — §7.4 requires takeover be visible, not silent. |
| U48 | **Option cards carry dock, dated time range, and one differentiator** drawn from `score_terms` ("soonest", "no waiting") — full receipt one tap away |
| U49 | **Composer = free text + 2–3 contextual quick replies.** Keeps the conversation genuinely open while making the common answer one tap on a bad connection. |
| U50 | **System events render as inline notices that also mutate the affected card** — the withdrawn option greys and strikes through in place, so the driver sees what happened *and* which thing it happened to |

### Design references and tooling

Researched 2026-08-19. The survey's most useful outcome was ruling things *out* — see the notes below.

| # | Decision |
|---|---|
| U34 | **`checklist-design` is the structural spine, used twice** — its matching checklist derives each surface's spec headings before writing, then re-runs as a completeness audit after |
| U35 | **`tasteskill.dev` is not adopted.** It self-excludes: *"Not dashboards, not data tables, not multi-step product UI"* |
| U36 | **`plugin87/ux-ui-agent-skills` is mined as reference, not installed** — its token tiers and component-anatomy shape are borrowed; its repo-wide "Senior Design Architect" persona would conflict with the root `AGENTS.md` |
| U37 | ~~**`ui-ux-pro-max` applies to driver and gate only**~~ — **corrected 2026-08-22**: this skill was confirmed **absent** from this session's available list during the `04-gate-yard-kiosk/` work (line ~393). It never applied to anything; there was nothing to ignore its palette/style database from. Kept struck-through rather than deleted so the correction is visible, not silently backfilled. |
| U38 | **`web-design-guidelines` and `dataviz` are post-write audit gates**, not generative inputs |

**Why `tasteskill.dev` was rejected despite being requested.** It is genuinely popular (77.7k stars,
actively maintained, MIT) and the rejection is not a quality judgement — its own skill file states it
covers "landing pages, portfolios, and redesigns," explicitly not dashboards, data tables or multi-step
product UI. That is every surface in this product. Its machinery targets hero sections and aesthetic
families; adopting it would cost 87KB of context to import guidance that does not apply. Its one
transferable idea — a table mapping briefs to real design systems (Carbon, Fluent, GOV.UK) with an
honesty rule against hand-recreating official systems — is noted and does not require installation.

### Templates and libraries

Researched 2026-08-19. **The headline finding: there is no template for four of our five surfaces.**
Admin consoles are a commoditised template category. Live triage queues, gate kiosks, carrier portals and
dock boards are domain products — every "logistics dashboard template" on the market is a marketing-grade
analytics page with fabricated KPI cards, not an operational surface. What genuinely transfers is the
shell, the primitives, and one real buy decision (the timeline).

| # | Decision |
|---|---|
| U51 | **shadcn/ui is the primitive layer.** Copy-in source over CSS variables — no runtime dependency, no lock-in. Its Radix-backed focus trap, `aria-modal`, scroll lock and roving tabindex are the expensive-and-dangerous parts; its styling is disposable and gets replaced by our tokens. Component specs stay implementation-agnostic (U22); this records what they bind to. |
| U52 | **Kibo UI Gantt (MIT) for the dock board**, installed as source via the shadcn CLI so it inherits our tokens and both themes. **Verify zoom presets and virtualisation before committing** — its docs mention neither, and we have 25 docks. Fallbacks in order: `react-calendar-timeline` v0.30 (MIT, React 19, still beta), then build it ourselves. |
| U53 | **`satnaing/shadcn-admin` as shell reference only** — MIT, 13.9k stars, and notably Vite + React + TS rather than Next.js. Take the shell and page scaffolds; discard its visual choices. |
| U54 | **No paid UI products.** Tailwind Plus ($249) skipped — free sources cover it and our surfaces are domain-specific enough that a pattern catalogue mostly confirms decisions already derived from the product spec. |
| U55 | **Reject flow follows the UK DfE "reasons for rejection" pattern** (GOV.UK lineage): category → sub-category → mandatory detail. Its documented iteration lesson is adopted verbatim — every reason is worded to tell the recipient *how to improve*, not merely what was wrong, because the text is shown to the rejected party. |

**Licensing hazard, recorded so nobody re-treads it.** Resource-timeline is the freight-scheduling
industry's monetisation line: FullCalendar (from $480/dev), Schedule-X (€479/yr), MUI X Premium, Bryntum
(~$2,040 for 3 devs), Syncfusion (quote-only) and DHTMLX all paywall *specifically* the view we need.
**DHTMLX's free build is GPL v2** — incompatible with a proprietary product, *and* it excludes timeline
view anyway. Only Kibo UI, `vis-timeline` and `react-calendar-timeline` give resource lanes under a
permissive licence.

**Nothing off-the-shelf exists for:** the gate kiosk (searches return kiosk *hardware* vendors — gloved
operation is a touch-controller spec, not something CSS solves), the carrier portal, the status bar, the
dense-table keyboard model, or **countdown/expiry primitives**. That last one is a bespoke primitive with
its own tests: a shared 1 Hz tick, `Intl.RelativeTimeFormat`, and `aria-live="polite"` throttled to avoid
screen-reader spam. It drives consequential actions, so it is specified and tested like logic, not styling.

**Why `checklist.design` needs no integration work.** The site is a client-rendered SPA with no sitemap
and no API; it returns a 2KB empty shell to any non-browser fetch. The local `checklist-design` skill
already bundles the content offline — the website adds a human browsing UI and nothing machine-readable.
No scraping or fetching layer should be built against it.

---

## AI chat primitives and closing the gaps

A checkpoint pass, 2026-08-19: research assistant-ui.com as a component source, and — the more consequential
half — **actually diff every existing foundations file against `SOLUTION_DESIGN.md`** rather than only
adding new files. That diff found real gaps: concepts three files *referenced* (facility accent, U40) but
none *defined*; product requirements with zero design coverage (the §7.4 ops co-pilot); and, prompted
directly by the owner, generic app-level states a "buildable spec" (U6) can't omit — loaders, 404, error
boundaries, maintenance, help, first-run emptiness.

### From the assistant-ui research

| # | Decision |
|---|---|
| U56 | **Adopt assistant-ui as the binding target for chat rendering** — same treatment as shadcn/ui (U51) and Kibo Gantt (U52). MIT, React 18/19, Tailwind-integrated, composes via the same source-through-CLI pattern. Full primitive-to-decision map lives in `00-foundations/ai-chat-primitives.md`. |
| U57 | **The §7.4 ops co-pilot is in scope now** — *"the assistant stays available to the human as a co-pilot... it is where the LLM adds the most value per token in this whole product."* Built on `AssistantSidebar`, specified inside `02-ops-exception-console/`: summarise-thread, fetch-context, draft-reply-for-approval. Scoped **only** to threads under human takeover (`ESCALATED`) — never a general chat-with-the-AI feature. |
| U58 | **Two new foundation files**: `iconography.md`, `ai-chat-primitives.md`. Notification patterns fold into `components.md` as one entry, not a standalone file. |

### From diffing existing files against the spec

| # | Decision |
|---|---|
| U59 | **Facility accent (`color.md`) uses hue safely, because position — not presence — disambiguates it.** Six accents from hues *outside* the five semantic ones (violet, teal, rose, cyan, lime, orange), rendered **only** as the rail-edge stripe and the facility switcher swatch. A location where no semantic colour ever appears cannot be misread as one — the U40 reference now has a real definition. |
| U60 | **Escalation lifecycle is a neutral progress stepper + owner + SLA clock** (`components.md` §16), with the SLA clock as the *only* element permitted to go red on breach. Deliberately doesn't reuse the priority ramp or promise-state hues — lifecycle position, urgency and promise state are three different facts. |
| U61 | **Full reviewed templates for all five §7.2 refusal patterns** (`voice-and-tone.md`), as a fifth message family alongside state, negative-path, clarification and reject-reason. Two (safety, off-manifest cargo) are liability-adjacent and specifically warrant reviewed wording. |
| U62 | **Staleness is reactive, not proactive.** No age indicator on option cards; a stale tap fails honestly into `SLOT_CONFLICT` or a fresh re-ranked set. A proactive freshness badge would make good options look untrustworthy for no operational gain. |
| U63 | **Bulk eligibility = "Select all eligible (N)" + disabled checkboxes naming their failing predicate** (`components.md` §6). One click for the fast path; the rule is taught inline rather than hiding the rows that most need individual attention. |
| U64 | **Times render facility-local always; the zone label appears only when it differs from the viewer's** (`voice-and-tone.md`). Rendering in the viewer's zone was rejected — a driver reading a dock time in the wrong zone is a missed appointment. |
| U65 | **Capacity incidents occupy one queue row that expands to affected shipments** (`components.md` §17). Directly encodes §7.4's "one incident, not N escalations" as an interface property. |
| U66 | **One stat-tile component** (`components.md` §14) — label, value, optional delta, optional inline sparkline — covers the status-bar count, planner queue-depth, and carrier on-time trend. |
| U67 | **The countdown gets an explicit paused state** (`components.md` §3), visually distinct from a healthy running countdown — pause icon, frozen and hidden value, neutral colour, one-shot. |
| U68 | **Driver offline = read-only cache + queued outbound text, option cards disabled** (`auth-and-scoping.md`). Committing to capacity that can't be validated at the moment of commit is exactly the promise this system must not break. |
| U69 | **Light is the default theme everywhere** (`color.md`), user-switchable, dark at full parity (U7). One consistent default rather than per-surface or system-following defaults. |
| U70 | **Idempotency key on every capacity-affecting button** (`components.md` §1), stated as an explicit rule rather than left implicit in the loading/disabled state — covers a client timeout on a request that actually succeeded server-side (M9). |
| U71 | **Route loading is a per-destination skeleton; the shell never unmounts** (`components.md` §13). No global progress bar — route transitions are already instant (`motion.md`). |
| U72 | **Three new full-page states: 404, a per-region error boundary, and maintenance** (`components.md` §13). The error boundary is scoped so a crashed dock board can't take the pending queue down with it; maintenance is a real need given §9.3's live-database migration. |
| U73 | **Help is contextual only — no FAQ surface** (`components.md` §15). An info affordance explains the specific state or field it's attached to; no separate content surface to write, translate (U31) and keep accurate. |
| U74 | **Empty states distinguish "nothing yet" from "nothing right now"** (`components.md` §13). Same visual emptiness, opposite meaning — getting this wrong makes a working system look broken. |

### External research checkpoint — SmoothUI, getdesign.md, and mature-system gaps (2026-08-20)

| # | Decision |
|---|---|
| U75 | **The promise-state chip hard-swaps between states — no morph animation** (`components.md` §2). SmoothUI's AI Tool Call argues a single morphing element for continuity; U14's "never confusable" principle wins over that argument, since a mid-morph chip risks reading `HELD` as a lead-up to `CONFIRMED` rather than a distinct, revocable state. One exception: a single non-celebratory settle on entry to `CONFIRMED`. |
| U76 | **Motion-budget allocation rule** (`motion.md`): only the row currently changing animates; settled rows shift back and lose contrast. The single highest-value idea out of the SmoothUI research — converts U13 from a pure prohibition into a positive allocation rule that protects a planner's ability to spot a CRITICAL arrival in a live queue. |
| U77 | **Threshold-only escalation, confirmed explicitly** (`motion.md`): colour/urgency escalates only at fixed thresholds (50/20/10s), never continuously. Mostly a naming of a rule the countdown table already embodied. |
| U78 | **Skeleton implementation technique documented** (`components.md` §13): invisible children hold real layout dimensions, a pulsing overlay sits on top — zero deps, zero `ResizeObserver`, inherits tokens automatically. Taken from SmoothUI's Skeleton component. |
| U79 | **Safer-action-first DOM order** (`components.md` §1): destructive/reject actions sit before constructive ones in source order, so keyboard tab traversal reaches the safer action first regardless of visual layout. Taken from SmoothUI's AI Diff component. |
| U80 | **getdesign.md format: skipped.** Its schema has no motion, no theming, and flattens component states to a naming convention rather than a structure — would lose more than it would gain. **Kept from the research**: if/when machine-readable tokens are wanted, write DTCG JSON directly (it's what design.md itself exports *into*, and it has the `shadow`/`duration`/`cubicBezier` types design.md lacks); its `broken-ref`/`contrast-ratio`/`orphaned-tokens` lint-rule ideas are worth encoding as our own checks independent of adopting the format. |
| U81 | **New file `data-formatting.md`** — numerals, units, duration grammar (counting-down vs. counting-up are different grammars), truncation position and minimum-retained-length rules, and the zero/unknown/scope-hidden distinction. Closes the gap where a genuine `0 min wait` in the decision receipt could collapse into the same rendering as an unknown value. |
| U82 | **New file `accessibility-behaviour.md`** — announcement politeness matrix, focus-management contract, an AT testing pairing matrix. Resolves a real, previously-unstated collision: U41's 5-second undo toast is not reliably reachable to a screen-reader user in that window, so undo also gets a keyboard shortcut that doesn't require racing the toast. |
| U83 | **Unavailability taxonomy** (`components.md` §18): Disabled / Inactive / Read-only / Hidden are four different things, not one "disabled" state. **Scope-denied is always Hidden, never Disabled** — a greyed-out cross-facility action would leak that the facility exists, which is exactly the class of leak `auth-and-scoping.md`'s inference-risk rule already forbids for data. |
| U84 | **Latency bands** (`motion.md`) + **a degradation policy** (`auth-and-scoping.md`, extending the offline section): primary regions (dock-board occupancy) go Inactive-with-reason on staleness; secondary regions (the U66 sparkline) just disappear. Retry copy for idempotency-keyed actions (U70) states explicitly that retrying is safe. |
| U85 | **New file `tokens.md`** — a three-tier naming grammar (base → functional → component-scoped) that makes U51 structurally enforceable rather than a rule to remember, and makes the facility accent's "exactly two render locations" (U40/U59) a fact about which token names exist rather than a sentence someone has to keep honouring. |
| U86 | **Shared queue interaction conventions** (`components.md` §19): a selection/bulk-action model, a 3-tier destructive-action model (low/moderate/high — U41 resolves exactly the moderate tier, not a blanket "no confirmation modals" rule), and a product-wide keyboard map, specified once ahead of `02-ops-exception-console/` and `03-planner-dock-board/` so both inherit the same model per U23 rather than converging on it independently. |
| U87 | **Forced-colors mode** (`color.md`, `elevation-and-depth.md`): Windows High Contrast strips `box-shadow`, flattening the light-theme elevation model on planner/admin's Windows desktop surfaces. Fix is a `CanvasText` border fallback restoring panel separation (not relative depth, which the mode has no concept of). The promise-state chip survives untouched — a direct dividend of "never colour alone." |
| U88 | **Evidence-status convention, going forward only**: new decisions citing an empirical number (a duration, a threshold, a count) state `Source: §X` / `Source: observed operations` / `Source: assumption, untested`. Not applied retroactively to U1–U74 — disproportionate effort for a documentation habit; can be swept later if it turns out to matter. Full definition in `tokens.md`. |

Full findings — including what SmoothUI's ~130 components were individually judged against and the
complete "where we're already ahead of every published system studied" account — are preserved in the
planning record; this log carries the decisions, not the research trail.

---

### `02-ops-exception-console/` — cross-facility triage and takeover (2026-08-20)

The second surface, and the first to carry a requirement no other surface has: the §7.4 ops co-pilot
(U57). Boundary against `03-planner-dock-board/`: this surface owns escalations, capacity incidents and
thread takeover — not pending requests, the 30-second row, or the five planner affordances.

| # | Decision |
|---|---|
| U89 | **Three-pane persistent layout** — escalation queue (left), detail + thread (centre), co-pilot (right); the queue never leaves the screen. **Deliberate, scoped divergence from U44** (inline expansion, never an overlay): U44 was written for a planner's 3-second detail peek, and a takeover thread is a workspace a coordinator can spend minutes in. Recorded as an exception, not a reversal of U44. |
| U90 | **Co-pilot draft → Approve → composer → Send** — two deliberate gates before a co-pilot-drafted message reaches a driver. Extends U42's "preview the driver's exact message → send" pattern to generated prose, where the read-gate matters more since there's no controlled vocabulary behind it. |
| U91 | **"All facilities" is the default scope**; rail accent goes neutral, facility renders as plain text per row. Keeps U59's facility accent at exactly two render locations intact — a per-row accent dot was considered and rejected as reopening the leak `tokens.md` (U85) exists to close. |
| U92 | **Acknowledge = claim to self**, owner named in the same click as the stepper's first advance; reassignment available afterwards. Auto-assignment was rejected — it names owners who never looked, recreating §7.4's "just a list" with names attached. |
| U93 | **Capacity incidents: ops triages and requests the sequencer proposal; the planner applies it** in `03-planner-dock-board/` — faithful to D5 ("it proposes, the planner applies") and to ops being cross-facility, so it must not itself mutate capacity at a facility it doesn't work. |
| U94 | **Takeover is an explicit act, separate from escalation, with hand-back available.** Several §7.4 reasons (e.g. `NOTIFICATION_UNROUTABLE`) never touch the driver conversation at all — auto-takeover would post "a person has joined" for escalations the driver has no stake in. |
| U95 | **Escalation queue sorts by time-to-SLA-breach ascending, unowned pinned above owned** — one continuous ordering driven by what actually hurts (a breach), reusing U19's frozen-sort-on-focus. |
| U96 | **Mockup convention, generalised**: one `mockup.html` per surface, covering that surface's key states, tokens traced verbatim to every relevant `00-foundations/` file — not just `color.md`. |

**Constitution Check** (first application of the habit — see *Spec-kit evaluation*, below): U89's divergence
from U44 is the one item in this batch that touches an existing binding decision. Checked against
AGENTS.md's delivery rules and the existing UI-UX decisions log — no violation found; U89 is scoped
explicitly to this surface's three-pane shell and does not relax U44's rule for `03-planner-dock-board/` or
any other queue-bearing surface, where U44 continues to apply unchanged.

### Recompare audit — `02-ops-exception-console/` against `SOLUTION_DESIGN.md`, and skills actually run (2026-08-20)

The owner asked directly whether `01-driver-chat/` and `02-ops-exception-console/` were checked against
the spec, and separately, whether the design-review skills this project committed to (U34, U38) were
actually being invoked rather than cited from memory. Neither had been done rigorously enough — both are
now closed.

**Spec recompare found a real gap one level below the UI-UX layer**: `SOLUTION_DESIGN.md` §7.5 had tool
catalogs for planner, gate/yard, sequencer and driver, but none for ops — every action
`02-ops-exception-console/` specified (Acknowledge, Take over, Hand back, Reassign, Resolve, Cancel,
Request sequencer proposal) sat on a backend contract that didn't exist. Closed by adding **§7.5.5 Ops
console** to `SOLUTION_DESIGN.md` itself, same treatment as §7.5.1–7.5.4.

**`checklist-design` was actually invoked** (previously only cited by name) against the Data Table and Chat
checklists. Found one genuine gap (no stated decision on bulk actions for the escalation queue) and two
minor ones (filter chips, an unconfirmed timestamp-rule cross-reference) — all closed below. Also caught,
separately, that the mockup's icon rail carried two placeholder icons with no defined destination —
resolved down to the two destinations this surface actually has.

| # | Decision |
|---|---|
| U97 | **`SOLUTION_DESIGN.md` gains §7.5.5 Ops console** — `get_escalation_queue`, `acknowledge_escalation`, `reassign_escalation`, `take_over_thread`, `hand_back_thread`, `resolve_escalation`, `cancel_escalation`, `request_sequencer_proposal` (delegates to §7.5.3's `propose_facility_schedule`, keeping D5 intact across the ops→planner handoff). Same three cross-cutting principles as the rest of §7.5. |
| U98 | **Resolve/Cancel reason-code enum**, `Source: assumption, untested` (U88): `ISSUE_FIXED` (Resolve) · `SHIPMENT_CANCELLED` / `DUPLICATE` / `CREATED_IN_ERROR` (Cancel). Inferred from what §7.4 already distinguishes, not drawn from a seeded example — flagged accordingly. |
| U99 | **All nine §7.4 reasons now explicitly covered** in `02-ops-exception-console/`, not just five. `WAREHOUSE_REPLY_CONFLICT` gets a stated "never auto-reconcile" rule (edge-cases.md #10); `SAFETY_OR_REGULATED` suppresses the co-pilot's draft-reply action specifically — summarise/fetch-context stay available (edge-cases.md #11, `components.md` §3). |
| U100 | **No bulk actions on the escalation queue, stated explicitly** — found missing (not just undecided) by a real `checklist-design` audit against the Data Table checklist. Every escalation needs individual judgment; §7.4 never describes a bulk need the way §7.3 has `bulk_confirm`. If an acknowledgment spike ever becomes real, bulk-*claim* (narrower than bulk-confirm, no capacity mutation) is the addition to make — not bulk resolve/cancel. |
| U101 | **Ops rail: two destinations, Escalations + Profile** — the two placeholder icons in the mockup's rail were never defined; resolved to mirror `01-driver-chat/`'s minimal two-destination nav rather than inventing a metrics/history screen `SOLUTION_DESIGN.md` doesn't describe. |

**Process correction, not a design decision**: `.claude/agents/ui-ux-designer.md`'s "Process reminder" now
states plainly that skills must be invoked via the `Skill` tool on every UI-UX read or update — citing a
checklist by name is not the same as running it, and running it for real is what caught U100.

### `03-planner-dock-board/` — the throughput-critical surface, §7.3 (2026-08-20)

The third surface, and the biggest single write so far — not one view but two: the §7.3 pending-request
queue and the dock/Gantt occupancy board (U25, U52 Kibo Gantt). A first planning pass was rejected for
being too shallow (architecture questions asked off §7.3 alone, no persona-table/schema check, the
matching `checklist-design` checklist not read before drafting structure) — redone properly, and the
redone version found a second real spec-level gap the same session found one for ops.

**§2's persona table names the planner's jobs as "Confirm/reject requests, block docks, re-sequence, see
conflicts."** Re-sequence already had tools (§7.5.3). **Block docks had none anywhere in §7.5** — closed by
adding `block_dock`/`end_dock_block` to §7.5.1, writing `dock_status_events`, D1's declared single
authority for availability and the direct trigger for `CAPACITY_EVENT_CASCADE` escalations.

| # | Decision |
|---|---|
| U102 | **Two tabs, Queue default** — Queue is the full-width throughput home (matches U39's own reasoning); Board is a separate tab for occupancy context, not a permanent split that would cost the 7-field row its room. |
| U103 | **Counter-offer: click a slot on the board.** Selecting it switches to the Board tab with the request pinned in a context banner; clicking an open interval on an eligible dock revalidates through Stage 1 and returns to the Queue tab. U25's "act via affordances, no dragging" applied literally — the click *is* the affordance. |
| U104 | **Sequencer proposal review: a before/after diff overlaid on the board**, using §5.1's own vocabulary (unchanged/moved/newly placed/unplaceable) as outlined delta bars, Apply calling `apply_schedule_proposal`. This is where `02-ops-exception-console/`'s Flow 4 handoff lands. |
| U105 | **Bulk confirm stays queue-only** — no board interaction, no preview gate. §7.3 frames it as explicitly the fast path; a board-preview step would reintroduce the friction it exists to remove. |
| U106 | **`SOLUTION_DESIGN.md` §7.5.1 gains `block_dock`/`end_dock_block`** — closes the persona-table gap above. The tool's response names any stranded appointments; that's exactly how a `CAPACITY_EVENT_CASCADE` starts. |
| U107 | **Blocking a dock is a form, opened from the board — not a drag-to-select range.** A drag-defined outage window sits right on the line U25 draws against dragging, even though the outcome differs in kind from a reschedule. |

**Schema-grounded, not invented**: the board's task bars colour by `dock_occupancy.state` (D1's actual
schema — 9 states) using the *existing* promise-state chip tokens, not a new Gantt palette; the 5 terminal
non-confirmed states (`COMPLETED`/`CANCELLED`/`EXPIRED`/`NO_SHOW`/`REJECTED`) render as no bar at all on
this forward-looking board rather than inventing tokens for states that no longer occupy capacity.
`IN_PROGRESS` reuses the confirmed token with an icon distinction rather than spending a new hue.

**`checklist-design`'s Timeline/Gantt checklist read before writing, not after** (the process correction
from the ops recompare, applied properly this time): Drag-to-reschedule and Dependencies are stated as
explicitly Not Needed Here, with reasons, rather than silently absent.

**Constitution Check**: U103's board-click affordance and U107's form-not-drag both checked against U25
("no free dragging") — neither introduces a drag gesture; U103's click-to-select and U107's explicit
form-over-drag choice are both consistent with it, not exceptions to it.

**`checklist-design` run post-write, in audit mode, against both tabs** (Data Table for Queue, Timeline/
Gantt for Board) — Board came back clean; Queue had three real 🟡s, all closed directly (not forks): the
five affordance buttons render always-visible rather than hover-revealed (a hover-only reveal would cost a
mouse user a discovery step the 30-second budget can't spare), a priority/ETA-confidence filter was added
(missing entirely before), and the empty state got a concrete stated line instead of a bare cross-reference.

### `04-gate-yard-kiosk/` — the most physically hostile surface (2026-08-20)

The fourth surface, and the first written under the owner's new 5-step standing rule (read spec → decide
skills → read foundations → decide files → ask questions), applied in full before any file content existed.

**§7.5.2's tool catalog was already complete** — cross-checked every persona-table job (gate-in, yard
queue, call-to-dock, dock-in, unload start/end, gate-out) against the five existing tools and found no gap,
unlike ops and planner. **Foundations resolved an apparent spec ambiguity**: `SOLUTION_DESIGN.md` only ever
references `facility_checkins.queue_state` by pattern (`WAITING_*`); `iconography.md`'s Queue state table
already had the full enum (`NOT_QUEUED`/`WAITING_EARLY`/`WAITING_LATE`/`WAITING_DOCK_UNAVAILABLE`/
`CALLED_TO_DOCK`/`IN_DOCK`/`COMPLETED`), used directly as the state machine driving the whole surface.

| # | Decision |
|---|---|
| U108 | **Two device contexts, same tools and interaction model** — a mounted gate-booth kiosk (gate-in/gate-out) and a handheld yard tablet (call-to-dock/dock-in/unload). The split is physical layout, not a different tool contract. |
| U109 | **Search is typed entry** (shipment ID or plate) — no scan/camera dependency invented, since nothing in the schema or seed data establishes a scannable code exists. |
| U110 | **One dominant full-width button** presents the single valid next action, derived purely from the truck's current `queue_state`. No button menu, ever — the purest reading of U26. |
| U111 | **Shared kiosk session, officer identity set once per shift**, stamped on every event that shift rather than re-authenticated per truck. |

**Skill assessment, decided explicitly before reading foundations** (per the new rule's step 2): no
`checklist-design` checklist matches a single-purpose field kiosk — checked the full 122-item index rather
than forcing a poor fit. `web-design-guidelines` is the real gate here, more than on any prior surface,
given the physical operating conditions. `ui-ux-pro-max` (U37 cites it as governing driver+gate touch
targets) is confirmed still absent from the available skill list this session — same finding as
`01-driver-chat/`, stated again rather than silently assumed fixed.

**Constitution Check**: U110's no-second-button rule checked against U41 (no confirmation modals) — fully
consistent, taken to its logical extreme for a surface where every action is a factual record rather than a
reversible commitment. `DOCK_MISMATCH`/unload-overrun framed as `feedback-warning`, never `feedback-danger`
— checked against the product-wide rule that danger tone implies user error, which neither outcome is.

### `05-carrier-portal/` — the scoped read-only surface (2026-08-20)

The fifth surface. Before starting it, a genuine internal contradiction in `SOLUTION_DESIGN.md` surfaced:
§2's persona table marks both this role and the admin console ✅ (v1), but §9's roadmap lists "carrier
portal" and "policy admin UI" under **Phase 5 — Scale-out**. Resolved with the owner: this is a design
exercise, not a build-order commitment — both remaining surfaces get designed at full v1 depth, matching
the other four, not a thinned-down treatment. Recorded here rather than silently picked either way.

**§7.5.6 was missing entirely** — the third instance of this project's now-familiar gap class (after
§7.5.5 for ops, §7.5.1's `block_dock` for planner). Closed with a read-only tool catalog, `carrier_id`-
scoped throughout, with no mutating tool by design — the persona table lists no write job for this role.

| # | Decision |
|---|---|
| U112 | **`SOLUTION_DESIGN.md` gains §7.5.6 Carrier portal** — `get_fleet_overview`, `list_fleet_shipments`, `get_shipment_detail`, `list_fleet_exceptions`, `get_carrier_on_time_performance`. Every scope derived from the caller's own `carrier_id`; `get_shipment_detail` refuses server-side on a cross-carrier id rather than trusting the client. |
| U113 | **Always cross-facility, no filter** — carriers aren't facility-scoped the way every other role is; the fleet is shown whole, facility renders as a row value, not a switcher. |
| U114 | **One sectioned dashboard, not tabs** — the content (fleet overview, shipments, exceptions) is light enough, per U33's own minimal-charting stance, to fit one scannable page. |
| U115 | **On-time sparkline: rolling 30-day window**, `Source: assumption, untested` (U88) — nothing in `SOLUTION_DESIGN.md` specifies a window; chosen for enough points to show a real trend without diluting into stale history. |
| U116 | **Shipment rows open a read-only detail screen** — the persona table's own "own fleet's shipments, exceptions" framing implies more than a bare list; stays fully read-only, no affordance added to the shared chip/history components it reuses. |

**`checklist-design`'s Analytics checklist** (the closest match — read before drafting, per the standing
rule) found the surface's shape mostly right on the first pass; the post-write audit caught one real gap
— the "last updated" indicator's own refresh control was implied in `flows-and-states.md` but never
actually drawn in `screens.md`'s wireframe or the mockup. Closed directly.

**Constitution Check**: U113 (no facility filter) checked against every prior surface's facility-scoping
pattern — consistent divergence, not an oversight, since carriers are the only role whose scope unit is
`carrier_id` rather than `facility_id`. U116 checked against `components.md` §18's Read-only contract — the
detail screen adds no interactive affordance, only a second read-only screen, so it doesn't reopen the
"substantially Read-only" characterisation this surface already carries.

### `06-admin-console/` — the sixth and final surface (2026-08-20)

Broadest single surface written: four genuinely distinct areas (users/roles, facility rules, policy
weights, audit trail) where every prior surface had one or two. The v1-vs-Phase-5 contradiction already
resolved for carrier portal (see that subsection) applies identically here — designed at full depth.

**§7.5.7 was missing entirely** — the fourth and final instance of this project's gap class. Closed with
ten tools spanning all four areas, each grounded in a principle already established elsewhere in the spec
rather than invented fresh: user/role changes as scope-assignment writes (M15), policy changes versioned
and simulated before publish (D7, U27), facility-rule changes through the typed rule-type registry (§0.9
issue 10's resolution), every write here itself an audited event (M14).

| # | Decision |
|---|---|
| U117 | **Four tabs — Users · Facility Rules · Policy · Audit** — each area substantial enough (policy editing alone is a multi-step simulate→publish flow) that one dashboard page would bury each behind the others, unlike carrier portal's lighter single-page treatment. |
| U118 | **Policy simulation shows aggregate impact first, examples second** — "N of M decisions would flip" as the headline, individual before/after cases (U27's own original example) as expandable detail. An admin needs to see scale before committing something every future decision gets stamped with. |
| U119 | **The fairness term (`w_fairness`) gets Danger-zone treatment** — visually separated, typed-confirmation gate to enable — distinct from every other weight field in the same editor. `SOLUTION_DESIGN.md`'s own language ("if the data turns ugly") frames this as a business-risk decision, not routine tuning. |
| U120 | **Role and scope are set in one invite/edit flow**, never a two-step "create then scope" sequence — closes the exact gap window M15's "foundational architecture, not an auth requirement" framing exists to prevent. |

**Three matching checklists** (Web app: *User Management*, *Admin Panel*, *Audit Log*) read in full before
drafting — a first for this project, no prior surface matched more than one. Several Admin Panel items
explicitly excluded with reasoning rather than silently dropped: *Organisation settings* and *Billing/plan
management* don't apply to an operator-facing product managing its own account branding/subscription.
Post-write audit came back cleanest of any surface so far — one cosmetic gap (a pending-invitation example
row missing from the wireframe, though the state itself was already specified in `components.md`), fixed
directly.

**Constitution Check**: U119's Danger-zone asymmetry (one weight field gated, the rest routine) checked
against the editor's own internal consistency — deliberate, and stated as deliberate, not an oversight to
later "fix" into uniformity. U120 checked against every other surface's role-scoping pattern (ops's
"All facilities" default, carrier's single-`carrier_id` scope, planner/gate's facility scope) — consistent
with the principle that scope shape follows role, just newly stated explicitly since this is the first
surface where an admin sets *someone else's* scope rather than operating within their own.

**All six persona surfaces of the UI/UX phase (roadmap step 2) are spec-written and mockup-complete.**
**Corrected 2026-08-22**: this line previously read as the phase being fully closed. It wasn't — the
cross-cutting shell screens below have a complete mockup gallery but, as of this correction, still no spec
markdown of their own; see U122 for exactly what that means and doesn't mean.

### Revision from the tech-stack phase — SMS dropped (2026-08-20)

Writing `TECH-STACK/TECH_STACK.md` surfaced a constraint the UI/UX phase had assumed away: **SMS is not
free, and in India it is not merely a paid feature — it requires DLT registration with TRAI (entity +
message templates) before a single message can be sent.** That is a multi-step regulatory precondition with
real lead time, not a config flag.

| # | Decision |
|---|---|
| U121 | **SMS dropped from v1. Web push + in-app only.** The four capacity-loss / decision-against events that previously warranted SMS (pending expired, planner rejected, dock down, option withdrawn) now get **high-priority push** instead. The outbox keeps a pluggable channel adapter so adding SMS later is not a rewrite. |

**The accepted limitation, stated rather than glossed**: a driver who never granted push permission — or is
on iOS without adding the PWA to their home screen — now has **no second channel**. Nothing is lost (the
thread list shows current promise state on open), but nothing is pushed either. This makes
`auth-and-scoping.md`'s push-denied status line load-bearing rather than informational.

**Synced in the same pass** (the WhatsApp divergence taught this lesson — an approved change that sits
unapplied rots): `SOLUTION_DESIGN.md` §1 and §6 module 10 · `00-foundations/auth-and-scoping.md` ·
`01-driver-chat/flows-and-states.md` (notification table) · `01-driver-chat/edge-cases.md` · U17 above.

### Cross-cutting shell screens (2026-08-21/22) — found stale in a consistency sweep, backfilled here

**What happened**: seven screens shared by all six roles — sign-in, role picker, password reset, the user
menu, the notifications panel, the search palette, and the account/settings page — were designed, mocked
up (`00-foundations/mockup-shared-shell.html`, 29 artboards), and gated through `web-design-guidelines`
exactly like every persona surface. But the decisions themselves were only ever numbered 1–9 inside
`00-foundations/stitch-prompts-shared-shell.md`, a file that **explicitly disclaims being a spec** — so for
a day and a half these were real, implemented, owner-approved decisions with no citable home. Assigned
U-numbers here, closing that gap.

| # | Decision |
|---|---|
| U122 | **The shell screens exist as a mockup gallery, not yet as spec markdown.** `00-foundations/mockup-shared-shell.html` is real and gate-checked; there is no `screens.md`/`flows-and-states.md`/etc. for this cross-role chrome the way each persona surface has. Recorded so the next reader knows exactly what "written" means here — mockup-complete, spec-pending — rather than assuming parity with the six surfaces. |
| U123 | **Sign-in**: one shared screen for all six roles, combined email-or-phone field, show/hide password toggle. Error copy is identical whether the email or the password was wrong ("Those details don't match") — never confirms which. |
| U124 | **Role picker**: shown only to accounts with more than one role, between password submit and landing. A single-role account skips it entirely — never a screen most users see once and never again. |
| U125 | **Password reset**: two screens sharing one card chassis, one continuous flow with no shell chrome between them (splitting them into separate prompts risked the two drifting apart visually). **Amended 2026-08-22: email-only for v1** — a phone-registered account (the driver role) has no self-service path; defensible because the driver session is already long-lived with silent refresh (U-driver-offline principles), so re-entering a password at all is rare. Fallback if ever needed: admin-assisted reset, not a new phone-OTP flow. |
| U126 | **Explicitly not built on sign-in**: "Remember me" (session length is already role-determined server-side, not user-chosen — a gate-kiosk device staying signed in longer would undermine its own device-bound model), SSO/social login (no third-party identity provider exists in this stack), self-service sign-up (accounts are admin-invited only). Recorded as a decision *not* to build, the same way U15/U16 record WhatsApp's ordinal trap as eliminated rather than merely absent — so none of the three get re-proposed later as an oversight. |
| U127 | **User menu popover**: identity header, role switcher (only if >1 role), appearance toggle (client-only, no server round-trip), settings link, sign out, and **sign-out-everywhere as an explicit second action** — never collapsed into the same button as plain sign-out. |
| U128 | **Notifications panel** (the feed) is a distinct component from notification **preferences** (what generates into that feed) — built as two separate popovers/pages even though both were found missing at the same audit pass, specifically so neither gets treated as a duplicate of the other. |
| U129 | **Search palette**: a command-palette modal (⌘K), not a search-results page — results grouped by entity type, recent searches on empty focus, a no-results state with a suggestion. **Facility-scoped by default for v1; no cross-facility toggle** — deferred, since only ops exec/manager and admin have the cross-facility scope that toggle would even apply to. |
| U130 | **Help is a contact-link popover, never a self-serve help centre or article library.** This protects U73 ("no FAQ surface exists in this product") rather than quietly reopening it through the back door of a top-bar icon that needed *some* destination. |
| U131 | **Account/settings page**: one continuous scrolling route, not five separate screens — sectioning it would produce five headers and no page. Five sections: personal info (read-only — Supabase Auth is the identity source, no edit path exists), appearance, notification preferences (grouped-category model, not per-event — sized for ~5 concurrent internal users), email digest-vs-real-time toggle, and read-only "Your access" (role + scoped facilities). No security section (MFA evaluated and declined this session), no Danger Zone (account lifecycle is admin-managed). |
| U132 | **New shared component: segmented control** (`components.md` §12) — found missing when two of the shell screens needed one and had to build it ad hoc. `role="radiogroup"`/`role="radio"` + roving tabindex; explicitly for 2–4 mutually exclusive views of the same data, never a form field's value (that's `radio`) and never navigation between destinations (that's tabs). |
| U133 | **New icon: `info`** (`iconography.md`) — a "link sent" panel had borrowed `circle-alert`, which this inventory reserves for errors. `info` is distinct from both `circle-alert` (something is wrong) and `circle-help` (explains a specific ambiguous element per `components.md` §15). |
| U134 | **`radius-full` extended to toggle switches** (`spacing-and-layout.md`) — previously scoped to "avatars, count badges only"; a switch's fully-rounded shape is its identity, not decoration, the same category as the two uses already permitted. |
| U135 | **The "not sloppy" bar, adopted as a process rule alongside U34/U38's skill gates**: every genuinely new screen gets a `web-design-guidelines` pass run for real (not cited from memory) before being called done, because a markdown spec can hide a control that's correct on paper and sloppy on screen. Applied to all seven shell screens and confirmed real findings in every one that got the gate (missing `aria-hidden`, absent focus-visible states, non-tabular numerals, and — on two of the six persona surfaces re-audited the same way — a quirks-mode-triggering missing `<!doctype>`). |

**Corrected in the same pass**: U37's claim that `ui-ux-pro-max` "applies to driver and gate only" — the
`04-gate-yard-kiosk/` work (line ~393) already found the skill absent from this session's available list.
U37 asserted it as active for a day and a half after that finding contradicted it; see the skill availability
note at that line for the actual state.

### Spec-kit evaluation (2026-08-20) — not a UI-UX decision, recorded for continuity

Evaluated `github/spec-kit` against first-party sources (repo README + raw `spec-template.md`,
`plan-template.md`, `tasks-template.md`, `constitution-template.md`). Not installed — its per-feature
`spec.md` slicing structurally mismatches this whole-product design system, and its Constitution artifact
is redundant with `AGENTS.md`. Two of its document *shapes* are borrowed by hand, applied at later roadmap
steps, not here: the Technical Context field list for the tech-stack markdown (roadmap step 3), and a
phased/file-path-mapped `tasks.md` shape for apply-to-existing-project (roadmap step 5). Its **Constitution
Check gate** is adopted now, as the lightweight habit applied just above — a short table on every new
doc's binding decisions, checked against AGENTS.md and the existing decisions log, going forward only.

---

## Spec divergence — WhatsApp (resolved)

**U15 contradicted `SOLUTION_DESIGN.md` as originally written**, which described the driver surface as
"Mobile-first chat (PWA + WhatsApp adapter)" (§2), listed a WhatsApp channel adapter as a SHOULD item, and
justified `chat_messages.external_message_id` / `is_duplicate` by reference to WhatsApp specifically (§7).

**This has been fixed — `SOLUTION_DESIGN.md` was updated 2026-08-20** to remove WhatsApp from all seven
locations, reconciled as follows:

1. **The ordinal trap became eliminable.** It existed because a text-only channel can only carry ordinals.
   With tap targets bound to `recommendation_id`, the bug is unreachable (U16).
2. **Outbound notification uses a different carrier.** §7.1's system-initiated message class — pending
   expired, planner rejected, dock down mid-conversation — now rides web push (U17), not WhatsApp.
   *(SMS was also part of U17 at the time of this note; it was subsequently dropped in U121 — web push is
   now the only outbound channel to drivers.)*
3. **Idempotent intake on `external_message_id` was kept**, reframed around PWA connectivity rather than
   WhatsApp specifically — retries, duplicate submissions and any future channel all still need it, and the
   seeded THR001/THR009 duplicate case remains a valid test unchanged.

Both documents now agree. This section is kept as a record of the divergence and its resolution, not as a
live discrepancy.

---

## Folder map

```
UI-UX/
├── README.md                     ← you are here: principles, decisions, map
├── 00-foundations/               ← the design system
│   ├── color.md                  · palette, semantic tokens, light/dark parity, the hue budget
│   ├── typography.md             · Inter + JetBrains Mono, scale, tabular numerals
│   ├── spacing-and-layout.md     · 4px base, density scale, grids, per-surface breakpoints
│   ├── elevation-and-depth.md    · layering, borders, shadow in both themes
│   ├── motion.md                 · functional motion, countdown behaviour, reduced-motion
│   ├── components.md             · shared inventory: buttons, chips, receipt, countdown, stat tile,
│   │                                escalation stepper, capacity-incident row, full-page states
│   ├── voice-and-tone.md         · templated state messages, refusals, banned phrasings, error copy
│   ├── auth-and-scoping.md       · sign-in, role landing, session expiry, offline, degradation, what
│   │                                roles never see
│   ├── iconography.md            · canonical icon inventory, naming convention, per-domain mapping
│   ├── ai-chat-primitives.md     · assistant-ui adoption, the ops co-pilot, primitive-to-decision map
│   ├── data-formatting.md        · numerals, units, duration grammar, truncation, absence handling
│   ├── accessibility-behaviour.md· announcement politeness, focus management, AT testing matrix
│   ├── tokens.md                 · token naming grammar/tiers, evidence-status convention
│   ├── mockup-shared-shell.html  · 29-artboard gallery for the cross-cutting shell screens (U122–U131)
│   │                                — sign-in, role picker, reset, user menu, notifications, search,
│   │                                account/settings. No spec markdown yet — mockup-complete only (U122)
│   └── stitch-prompts-shared-shell.md · generation prompts for the gallery above — explicitly not a
│                                    spec; a value with no foundation source there is a gap to close,
│                                    never a decision made in that file
├── 01-driver-chat/               ← PWA, phone-first, hostile conditions — written
├── 02-ops-exception-console/     ← cross-facility triage and thread takeover — written
├── 03-planner-dock-board/        ← the throughput-critical surface (§7.3) — written
├── 04-gate-yard-kiosk/           ← tablet, gloves, outdoors — written
├── 05-carrier-portal/            ← scoped read-only — written
└── 06-admin-console/             ← users, rules, policy weights, audit — written
```

Each surface folder contains **seven** files (the original five per U4, plus two added later in the
project — corrected 2026-08-22, this table previously said five and had drifted):

| File | Contents |
|---|---|
| `screens.md` | Layouts with ASCII wireframes, information hierarchy, responsive behaviour |
| `components.md` | Components specific to this surface — anatomy, variants, states |
| `flows-and-states.md` | Task flows, plus loading / empty / partial / success states |
| `edge-cases.md` | The failure paths this surface owns, and what the user sees |
| `accessibility.md` | Ergonomics for this surface's physical context, keyboard model, targets |
| `mockup.html` | The value-swept visual reference for this surface (U96) — added after U4, never folded back into this table until now |
| `stitch-prompts.md` | Generation prompts derived from the five spec files above, not a spec of their own — same convention as the shared-shell prompts file |

---

## How to read this

- **Building a component?** Start in `00-foundations/components.md`, then the surface's `components.md`
  for local variants. Need an icon? `00-foundations/iconography.md` is the only source — don't pick one
  ad hoc.
- **Building a screen?** The surface's `screens.md` for layout, then `flows-and-states.md` for behaviour,
  then `edge-cases.md` — which is where the genuinely hard requirements live.
- **Building `01-driver-chat/` or `02-ops-exception-console/`?** Read `00-foundations/ai-chat-primitives.md`
  alongside `components.md` — it's where the option cards, decision receipt, and (for ops) the co-pilot
  bind to assistant-ui's primitives, and skipping it means re-deriving decisions already made there.
- **Reviewing the design?** This README, then `00-foundations/color.md` and
  `00-foundations/voice-and-tone.md`. Those two carry most of the load-bearing decisions.
- **Checking a claim against the product spec?** Section references throughout point into
  [`../SOLUTION_DESIGN.md`](../SOLUTION_DESIGN.md).
- **App-level states — 404, loading, maintenance, help, first-run emptiness?** These live once in
  `00-foundations/components.md` §13–15 because they apply to every surface identically. Don't respecify
  them per surface; cross-reference instead.
- **Sign-in, the user menu, notifications, search, or account/settings?** These are cross-role shell
  chrome, not part of any one persona surface. `00-foundations/mockup-shared-shell.html` is the mockup;
  U122–U131 above are the decisions; there is **no spec markdown for these yet** (U122) — the mockup and
  the decisions log are the only two places this currently lives.
- **Rendering a number, a duration, or a long identifier?** `00-foundations/data-formatting.md` — before
  inventing a format inline, especially for anything derived from `score_terms` or an ID that might get
  truncated.
- **Wiring up a live-updating region, or anything a screen reader needs to hear about?**
  `00-foundations/accessibility-behaviour.md` for the announcement and focus-management contract — this is
  cross-cutting and is not repeated in each surface's `accessibility.md`, which covers physical ergonomics
  only.
- **Naming a new token?** `00-foundations/tokens.md` for the tier model before reaching for a value file
  directly — a component should almost never reference a base primitive.
