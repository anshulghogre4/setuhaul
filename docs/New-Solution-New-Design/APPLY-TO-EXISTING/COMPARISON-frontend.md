# Frontend comparison — live `frontend/src/` vs. `UI-UX/` + `TECH-STACK/TECH_STACK.md` §9

> Phase 0 scope per `TASKS.md`: `frontend/src/` in full. Read in full: `App.tsx`, `main.tsx`, `App.css`,
> `index.css`, `core/auth/supabase.ts`, `core/http/api.ts`, `layouts/ProtectedLayout.tsx`,
> `features/auth/LoginForm.tsx`, `features/dispatch/DispatchHome.tsx`, `features/operator/OpsHomes.tsx`,
> `features/driver/DriverHome.tsx`, `features/driver/DriverLayout.css` — 12 files, ~17 including assets.
> `features/admin/` has **zero files** (directory does not exist under `frontend/src/features/`).
>
> Design side read: `UI-UX/README.md` (principles, U1–U135 decisions log), `TECH-STACK/TECH_STACK.md` §1/§9/
> §12, `UI-UX/01-driver-chat/screens.md`, `UI-UX/02-ops-exception-console/screens.md`,
> `UI-UX/03-planner-dock-board/screens.md`, `UI-UX/00-foundations/auth-and-scoping.md`,
> `UI-UX/00-foundations/color.md`. `SOLUTION_DESIGN.md` (the FR-*/NFR-* source) was **not** re-read this
> pass — out of this run's assigned scope — so findings below cite `U-*` decisions and `§`-references from
> the UI-UX/tech-stack docs already read, not FR-*/NFR-* ids. See tag 3 on every finding for what's actually
> citable.

---

## Honest sizing — the one fact that matters most for planning Phase 4

**Of the six UI-UX surfaces plus the shared shell, five surfaces and the entire shared shell have zero live
implementation.** Concretely:

| Surface / area | UI-UX spec status | Live implementation |
|---|---|---|
| `01-driver-chat` | Written, mockup-complete (7 files) | **Partial** — a single chat screen exists (`DriverHome.tsx`), but it is a custom hand-rolled implementation, not built on the spec's components (see findings below) |
| `02-ops-exception-console` | Written, mockup-complete | **Not built as specified.** A dashboard exists (`OpsHomes.tsx`) that covers *some* of the same job (escalations) but not the specified three-pane shell, co-pilot, takeover, or stepper |
| `03-planner-dock-board` | Written, mockup-complete | **Zero.** No queue table, no Gantt board, no counter-offer picker, no block-dock form. `OpsHomes.tsx`'s "pending confirmations" list covers a sliver of the confirm job with none of the seven-field row, sort discipline, or TTL countdown |
| `04-gate-yard-kiosk` | Written, mockup-complete | **Zero.** No kiosk code anywhere in `frontend/src/` |
| `05-carrier-portal` | Written, mockup-complete | **Zero.** `TRANSPORT_MANAGER` is routed into the same "ops"/"global" dashboard as Admin (`core/auth/supabase.ts:25-33`, `OpsHomes.tsx:96-101`) — there is no carrier-scoped, read-only, own-fleet-only surface at all |
| `06-admin-console` | Written, mockup-complete | **Zero.** `features/admin/` does not exist. `ADMIN` role also lands on the same generic ops dashboard, not the four-tab (Users/Facility Rules/Policy/Audit) console |
| Shared shell (sign-in, role picker, password reset, user menu, notifications panel, search palette, account/settings — U122–U131) | Mockup-complete (29 artboards), spec markdown still pending per U122 | **Partial sign-in only.** No role picker, no password reset, no notifications panel, no search palette, no account/settings page. The "user menu" exists only as a bare name/role/logout `<details>` popover |

Two feature folders (`dispatch`, `operator`) contain code with **no corresponding surface in the six-persona
design at all** — `DispatchHome.tsx` is a shipment-creation/driver-assignment console that doesn't map to
any of the six `UI-UX/` folders (closest conceptual match is the TMS boundary the design explicitly puts
out of scope — see `01-driver-chat/screens.md` line 284, "No editing of driver, vehicle or carrier data —
TMS-owned"). This is flagged explicitly rather than forced into a surface it doesn't belong to.

**Net**: roughly 1 of 6 personas has partial coverage, the shared shell has partial coverage of one of its
seven screens, and one live feature (`dispatch`) has no design counterpart to compare against at all. Phase
4 of `TASKS.md` is not "extend existing surfaces" — for five of six surfaces it is "build from nothing,"
and even the one surface with code needs re-architecture, not incremental extension, to match the spec (see
`01-driver-chat` findings below).

---

## Tech-stack conformance — `TECH_STACK.md` §9 vs. `frontend/package.json`

| §9 decision | package.json reality | Verdict |
|---|---|---|
| React 19 + Vite + TypeScript | `react` `^19.2.8`, `react-dom` `^19.2.8`, `vite` `^8.2.0`, `typescript` `~6.0.2` | **Matches on major-version intent.** React 19 confirmed. |
| Tailwind | **Absent.** No `tailwindcss` package, no `tailwind.config`, no `@tailwindcss/*` plugin. Live styling is hand-written CSS (`App.css`, `index.css`, `DriverLayout.css`) with hardcoded hex values and CSS custom properties (`--bg: #0b1326`, `--accent: #4edea3`, etc.) | **Does not match.** No trace of Tailwind adoption anywhere in the read files. |
| shadcn/ui (U51) | **Absent.** No `components.json` (shadcn's CLI marker), no Radix packages (`@radix-ui/*`) in dependencies | **Does not match.** Every interactive control (`<details>` profile menu, the custom `BoundedLOVSelect` combobox in `DispatchHome.tsx:32-174`, the escalation-decision modal in `OpsHomes.tsx:467-598`) is hand-built from scratch rather than the Radix-backed primitives U51 specifically chose for their focus-trap/`aria-modal`/scroll-lock/roving-tabindex behavior. The modal at `OpsHomes.tsx:467` has no visible focus trap, no `role="dialog"`/`aria-modal`, and no Escape-to-close handler — exactly the "expensive and dangerous parts" U51 says shadcn/Radix exists to not reinvent. |
| assistant-ui (U56) | **Absent.** No `@assistant-ui/*` package | **Does not match.** `DriverHome.tsx` renders chat manually: a hand-rolled `renderFormattedText()` markdown-lite parser (lines 124-165), a plain `<div>`-based message list, and a raw `fetch`-via-`apiPost` call per turn — not `MessagePartPrimitive` (`01-driver-chat/screens.md` line 251: "Cards render through `MessagePartPrimitive` as tool-call output, never as parsed text"). |
| Kibo UI Gantt (U52) | **Absent** | **N/A — no board exists to render.** `03-planner-dock-board` has zero live code. |
| Driver surface = installable PWA | **Absent.** No `vite-plugin-pwa`, no manifest, no service worker in the files read | **Does not match.** Nothing found and nothing checked for a `public/manifest.json`/service worker outside the assigned scope, but no PWA tooling is in `package.json`'s dependency list at all. |
| SSE streaming (§9 "Frontend latency decisions") | **Absent.** `DriverHome.tsx` uses `apiPost<ChatResponse>('/api/v1/chat/message', …)` — a single request/response call, not `EventSource`/SSE | **Does not match.** The whole chat turn is one blocking POST; no token-by-token rendering, no TTFT optimisation path exists client-side regardless of what the backend does. |
| Vitest + Playwright (§1 testing) | **Absent** from `devDependencies`. Only `oxlint` (a Rust linter, not in §1's stack) is present | **Does not match** on the testing tooling; `oxlint` itself is a reasonable, undocumented substitution for a lint step (§1 doesn't name a linter at all, so this isn't a contradiction, just unrecorded). |

**Summary**: only the framework triad (React 19 / Vite / TypeScript) is actually in place. Every other §9
decision — Tailwind, shadcn/ui, assistant-ui, Kibo Gantt, PWA installability, SSE streaming — has no trace
in `package.json` or the code read. This is the same picture as the surface-by-surface sizing above, seen
from the dependency graph instead of the folder tree.

---

## `core/http/api.ts` and `core/auth/supabase.ts`

**What exists**: a typed `ApiEnvelope<T>` wrapper (`api.ts:5-12`), `apiGet`/`apiPost` helpers that attach a
Supabase-issued bearer token per call (`api.ts:26-36`), an idempotency-key option on `apiPost`
(`api.ts:50-59`), and a `formatUserFriendlyError` mapper (`api.ts:74-105`). `supabase.ts` wraps
`@supabase/supabase-js`, exposes `signIn`/`signOut`/`getSession`, and a client-side `roleToPortal` map used
only for **navigation convenience**, not access control (`supabase.ts:35-39`).

1. **Keep as-is.** `getSession()` → bearer token → backend `/api/v1/auth/me` is the correct shape for
   `TECH_STACK.md` §4's identity/scope model: the frontend never decides scope itself, it asks the backend
   (`api.ts:26-36`, consumed by `layouts/ProtectedLayout.tsx:72-79`). `roleToPortal` is explicitly a routing
   hint, not an authorization decision — `ProtectedLayout.tsx:73-78` re-derives the *actual* portal from the
   verified `/me` response and blocks on mismatch rather than trusting the URL or the client-side map. This
   matches `auth-and-scoping.md`'s governing rule verbatim: "The interface never decides what a user may
   see" (line 8).
2. **Keep as-is.** The idempotency-key plumbing (`api.ts:50-59`) is actually used on both capacity-affecting
   calls found in this pass — `OpsHomes.tsx:170` (confirm appointment) and `DriverHome.tsx:462` (ETA write)
   — which is exactly U70's rule ("Idempotency key on every capacity-affecting button," `README.md` line
   244).
3. **Functional requirement mapping**: `auth-and-scoping.md` "The governing rule" (no §/FR id in the docs
   read this pass); U70 for the idempotency plumbing. No FR-*/NFR-* id available without re-reading
   `SOLUTION_DESIGN.md`, which was out of this pass's scope.
4. **Wrong optimisation flag**: none found here — this is the one area of the four reviewed that is sized
   right for what it does and doesn't reach for machinery the spec doesn't ask for.

---

## `layouts/ProtectedLayout.tsx`

**What exists**: a shared chrome — sticky top bar with title, a `<details>`-based profile popover
(`ProtectedLayout.tsx:18-52`), and, only for the `ops` portal, two inline-styled tab links ("Dock Command" /
"Dispatch Console", lines 112-155).

1. **Needs improvement.** The design's shared-shell decision is an **icon rail (56px) + thin top bar**
   (U39), not a labelled top-tab-bar — U39's own stated reason is that the planner's 7-field row needs the
   horizontal space a sidebar would cost, and the top-bar tabs here (lines 112-155) eat that same horizontal
   budget from the other direction. There is no facility switcher (U40), no notifications bell, no help
   affordance, no search palette entry point (U129), and no status bar (U43: "connection, last sync, active
   facility, pending count, policy version") — none of the seven shared-shell pieces beyond a bare profile
   menu exist.
2. **Functional requirement mapping**: U39 (icon rail), U40 (facility switcher), U43 (status bar), U127
   (user menu popover). No FR-*/NFR-* id available this pass.
3. **Wrong optimisation flag**: the inline `style={{...}}` blocks for the tab links (lines 113-155, ~40
   lines of inline CSS objects for two links) are a maintenance cost for something the design already
   specifies as a rail item, not a top-bar tab — this is effort spent building UI the spec doesn't call for,
   while the UI the spec does call for (rail, switcher, status bar) doesn't exist yet.
4. **Keep as-is**: the loading/error live-region pattern (`sr-live` + `aria-live="polite"`, lines 157-164)
   is a reasonable, if minimal, precursor to `accessibility-behaviour.md`'s announcement contract — not
   read in full this pass, but the shape (a dedicated live region, not an ad hoc alert) is the right
   instinct.

---

## `features/auth/LoginForm.tsx` — mapped to the shared shell's sign-in (U123, ambiguous by design)

The task brief names auth → "the shared shell's sign-in" as the best-guess mapping; that mapping is used
here, but it is worth stating plainly that the live app splits sign-in by portal URL (`/driver/login`,
`/ops/login`) while the design specifies **one shared sign-in screen for all six roles** (U123) — so the
comparison is against a design that structurally rejects the live app's split-by-URL approach.

**What exists**: two `<LoginForm>` instances (`App.tsx:12-31`) differing only by copy and hero image, each
with a plain email + password form, inline error text, and a redirect-on-role-mismatch (lines 66-70).

1. **Needs improvement.** U123 specifies a **combined email-or-phone field** ("drivers know their phone
   number; office staff know their email... disambiguate server-side"), one shared screen, and identical
   error copy regardless of which field was wrong ("Those details don't match" — never confirms which).
   The live form has an `email`-typed input only (`LoginForm.tsx:106-115`, `autoComplete="username"` but
   `type="email"`), no phone option, and is split into two URL-addressed screens rather than one. Error
   copy also diverges: `signIn` surfaces Supabase's own auth error message directly (`LoginForm.tsx:56-57`)
   rather than the design's deliberately non-disclosing "Those details don't match" (`auth-and-scoping.md`
   line 45) — Supabase's stock messages ("Invalid login credentials," etc.) do not, on inspection of this
   code path, appear to be filtered before display, which risks the account-enumeration leak U123 exists to
   prevent (a wrong-password vs. wrong-user Supabase error can differ).
2. **Needs improvement.** No role picker (U124), no forgotten-password link/flow (U125 — the design's
   password-reset is two screens; live has none), no "Not now"-style progressive disclosure — this form is
   a single, complete-in-one-step credential box with no shell-chrome integration at all.
3. **Functional requirement mapping**: U123 (combined field, generic error), U124 (role picker), U125
   (password reset). No FR-*/NFR-* id available this pass.
4. **Wrong optimisation flag**: the per-portal hero image/copy/metrics block (`LoginForm.tsx:25-48`, ~25
   lines of marketing-style hero content with fabricated-looking metrics like "Daily loads 280-360") is
   presentation effort spent on content the design doesn't call for at all — U123 describes a plain,
   utilitarian card, not a two-pane marketing split-screen. This is exactly the kind of over-building the
   persona brief's "wrong optimisation flag" tag exists to catch: polish on an unspecified surface while the
   specified surface (role picker, generic error copy, phone-number support) is entirely missing.

---

## `features/driver/DriverHome.tsx` + `DriverLayout.css` — mapped to `01-driver-chat`

**What exists**: a single fixed two-pane layout — chat on the left, an operational-context rail on the
right (`DriverHome.tsx:515-806`) — with free-text chat, three static quick-action buttons, and an ETA
confirmation banner.

1. **Needs improvement.** The spec's screen map is **thread list → conversation → profile** with a
   single-thread shortcut (`01-driver-chat/screens.md` lines 17-24, 106-111). The live app has **no thread
   list at all** — it always renders the single conversation view, permanently, with no way to see resolved
   history or multiple active loads. This happens to coincide with the single-thread shortcut's *end state*
   for a driver with one load, but the mechanism doesn't exist — there's no code path that would show a
   list if a second thread existed, and no `Profile` screen (only the shared `ProtectedLayout` popover).
2. **Needs improvement.** No promise-state chip anywhere (`color.md` lines 99-108: four states, four
   redundant encodings — colour/icon/label/border). The context rail's `DataField` components
   (`DriverHome.tsx:256-271`) render appointment status as plain text with an optional green/amber tone
   class, not the specified chip with icon + border-style (dashed-for-temporary vs. solid-for-committed,
   `color.md` line 114). This is the design's single most load-bearing visual rule (`README.md` principle
   1, line 21) and it is entirely absent from the live UI.
3. **Needs improvement.** No option cards (U16/U48). Slot options, if the backend's `find_feasible_slots`
   tool returns them, are logged to the browser console (`logSchedulingEngine`, lines 63-122) but never
   rendered as tappable cards in the transcript — they only ever reach the driver as prose inside
   `res.data.response` (line 420), which reopens exactly the risk U16 was written to close ("Tappable
   option cards only — ordinals are eliminated"). A driver reading free-text prose from the model has no
   structural guarantee against the ordinal-trap failure mode §7.2b names.
4. **Needs improvement.** No countdown/TTL component for `HELD`/`PENDING_CONFIRMATION` states — nothing in
   `DriverHome.tsx` renders a live countdown anywhere, despite this being called out as "almost no
   enterprise UI has [this]" and specifically engineered (`README.md` principle 2, tabular numerals,
   1Hz tick, `Intl.RelativeTimeFormat`).
5. **Keep as-is / defensible**: the local-storage-backed conversation/session-id persistence
   (`getDriverConversationIds`/`saveDriverConversationIds`, lines 222-254) is a reasonable, undocumented-but-
   compatible mechanism for restoring a thread across reloads — it doesn't contradict any U-decision found
   this pass, and Redis's 24h TTL (per `AGENTS.md`/`TECH_STACK.md` §3) is respected by re-fetching server
   history on mount rather than trusting the local cache as authoritative (lines 331-370).
6. **Functional requirement mapping**: `README.md` principles 1–2, U16, U18, U47–U50 (chat surface
   decisions), U56 (assistant-ui). No FR-*/NFR-* id available this pass.
7. **Wrong optimisation flag**: `logSchedulingEngine` (lines 63-122) is a substantial, well-built
   developer-debugging feature (console-table rendering of ranking factors, rejected reasons, escalation
   detail) that has no user-facing design counterpart at all — it's effort spent on an internal tool while
   the driver-facing option card it's inspecting the data *for* was never built. Reasonable as a temporary
   debug aid, but worth flagging before it's mistaken for product functionality.
8. **Wrong optimisation flag**: the inline markdown-lite parser (`renderFormattedText`, lines 124-165)
   duplicates a slice of what assistant-ui/`MessagePartPrimitive` would provide for free (U56) — it's not
   wrong to have built it, but it's exactly the kind of bespoke primitive the tech-stack doc chose a library
   specifically to avoid rebuilding.

---

## `features/operator/OpsHomes.tsx` — mapped ambiguously to `02-ops-exception-console` and/or `03-planner-dock-board`

Stated explicitly, per the task brief's instruction: **this mapping is genuinely ambiguous.** `OpsHomes.tsx`
is one flat dashboard that mixes a shipment-status summary, an exceptions feed, a "pending confirmations"
list (closer to planner's confirm job, §7.3), and an "escalation queue" with a decision modal (closer to
ops's escalation job, §7.4). Neither design surface's shape is what's built; the comparison below checks it
against both.

1. **Needs improvement**, against `02-ops-exception-console`. The spec is a **persistent three-pane shell**
   — queue / detail+thread / co-pilot (U89) — with an explicit escalation-lifecycle stepper (Open → Ack →
   In-Progress → Resolved, U92/`components.md` §16), a takeover mechanism with a driver-visible divider
   (U47/U94), and a scoped co-pilot (U57/U90: summarise, fetch-context, draft-reply-for-approval, with an
   Approve gate before anything reaches the composer). The live implementation has **none of these**: a flat
   list with cards (`OpsHomes.tsx:405-464`) and a single decision **modal** (lines 467-598) offering only
   "Mark Resolved" — no Acknowledge, no Take-over-thread, no Hand-back, no Reassign, no thread rendering at
   all (there is no visible driver conversation anywhere in this file), and no co-pilot. `resolve_escalation`
   is called with a hardcoded default note and a `status` param (`handleTakeDecision`, lines 184-199) that
   doesn't correspond to the design's typed reason-code enum (U98: `ISSUE_FIXED`/`SHIPMENT_CANCELLED`/
   `DUPLICATE`/`CREATED_IN_ERROR`) or the ops console's actual §7.5.5 tool set.
2. **Needs improvement**, against `03-planner-dock-board`. The "pending confirmations" list
   (`OpsHomes.tsx:330-390`) is the closest live analogue to the planner queue's confirm job, but it is a
   plain unstyled list with one action (Confirm) — none of the seven specified fields (driver·carrier,
   interval, condensed receipt, displacement check, ETA confidence, driver's own limit, TTL countdown —
   `03-planner-dock-board/screens.md` lines 85-97), no urgency-composite sort (TTL · priority · queue
   state), no single-key row actions (U46: `C`/`R`/`O`/`H`/`E`), no counter-offer, no board/Gantt tab at
   all. There is also no `block_dock` affordance and no bulk "Select all eligible" entry point (U63).
3. **Needs improvement.** `escalations.slice(0, 8)` and `pendingConfirmations.slice(0, 8)`
   (`OpsHomes.tsx:349, 406`) hard-cap the visible rows at 8 with no pagination, no "show more," and no
   indication that more rows exist beyond the header count — both designs treat the small-scale queue
   (15–35 rows, §7.3's own arithmetic) as something the operator works *live, in full*, not a truncated
   top-8 preview. This silently hides rows a coordinator needs to see.
4. **Functional requirement mapping**: U89, U90, U92, U94, U98 (ops console); §7.3's seven-field row,
   U46, U63 (planner queue). No FR-*/NFR-* id available this pass.
5. **Wrong optimisation flag**: the escalation-decision modal (`OpsHomes.tsx:467-598`) is a reasonably
   built custom overlay (~130 lines) for a job the design explicitly does **not** want handled as a modal —
   U41 states "no confirmation modals, a 5-second undo window instead" as a product-wide pattern, and
   `02-ops-exception-console/screens.md` specifies inline detail-pane editing (U89's whole reason for
   existing is to avoid exactly this kind of overlay-based workspace for a multi-minute takeover task). This
   is effort invested in the one interaction pattern (modal-based decisions) the design goes out of its way
   to rule out.
6. **Wrong optimisation flag**: the escalation-reason extraction logic (`extractEscalationReason`, lines
   47-65) reconstructs a human-readable "why" from raw payload fields with several fallback heuristics and
   two hardcoded type-specific sentences (`NO_SLOT`, `DRIVER_BREAKDOWN`). This is the interface *inferring*
   a reason from loosely-typed data rather than rendering a structured receipt the backend already
   produces — which runs directly against principle 3 in `README.md` ("The interface renders receipts; it
   never reasons," line 38-43). Whether this reflects a real backend gap (no structured reason field) or a
   frontend choice not to use one is outside this pass's scope, but as written, the pattern is exactly the
   one the design calls out as a load-bearing distinction.

---

## `features/dispatch/DispatchHome.tsx` — no design counterpart

1. **Gap report, not a keep/needs-improvement finding.** `DispatchHome.tsx` builds a full shipment-creation
   and driver/facility-assignment console (`BoundedLOVSelect` custom combobox, lines 32-174; the assignment
   form and result panel, lines 176-506) that has no matching screen, flow, or component anywhere in the
   six `UI-UX/` surface folders or the shared shell. The closest the design gets is explicitly ruling this
   kind of functionality **out of scope** for the driver surface ("No editing of driver, vehicle or carrier
   data — TMS-owned," `01-driver-chat/screens.md` line 284) — implying this is TMS territory the redesign
   deliberately doesn't cover, not a surface that was simply missed.
2. **Functional requirement mapping**: none. This screen sits outside the six-persona design entirely; no
   `U-*` decision or `§`-reference in the docs read this pass addresses it.
3. **Wrong optimisation flag**: real, non-trivial effort went into this screen — a searchable, filterable
   custom select component built from scratch (`BoundedLOVSelect`, ~140 lines, duplicated conceptually
   across driver/facility/priority/category/dock-type fields) for a feature that isn't part of the
   redesign's scope at all. If dispatch/load-assignment is still a needed capability going forward, it
   needs its own design decision (a seventh surface, or folded into an existing one) before Phase 4 work
   continues on it — right now it's unspecified surface area accumulating unspecified UI.

---

## `features/admin/` — zero files

Per the assignment brief: admin has 0 live files, and the honest output here is a gap report, not a forced
"keep as-is."

1. **Gap report.** `06-admin-console`'s four tabs (Users · Facility Rules · Policy · Audit — U117) have no
   live counterpart. The `ADMIN` role is routed into the same generic `ops` dashboard as every other
   ops-portal role (`core/auth/supabase.ts:25-33`, `OpsHomes.tsx:96-101` treats `role_name === 'ADMIN'` as
   just another trigger for `global = true`), meaning an admin today sees the same flat exceptions/
   escalations dashboard as an Operations Executive — not policy simulation (U118), not the fairness-term
   danger-zone gate (U119), not user/role/scope management (U120), not an audit trail.
2. **Functional requirement mapping**: U117–U120. No FR-*/NFR-* id available this pass.
3. **Wrong optimisation flag**: none applicable — there's no code to over- or under-build.

---

## Cross-cutting observations

- **Theming**: `index.css:1-18` hardcodes `color-scheme: dark` and a single dark palette
  (`--bg: #0b1326`, etc.) with no light-mode variables and no toggle. This contradicts U7 ("Light and dark
  at full parity") and U69 ("Light is the default theme everywhere... dark at full parity") directly — the
  live app is dark-only, and the token names (`--bg`, `--panel`, `--accent`, `--muted`) don't correspond to
  `color.md`'s semantic-token naming (promise-state tokens, neutral/blue/amber/green/red ramps) at all.
  **Functional requirement mapping**: U7, U69, `color.md`'s semantic-token section. **Needs improvement.**
- **Density**: the design assigns `compact` density to ops/planner and `comfortable` to driver
  (`spacing-and-layout.md`, referenced but not read in full this pass); nothing in the CSS read this pass
  implements a density system — spacing values are ad hoc pixel literals throughout (`App.css`).
- **No forced-colors/high-contrast handling** (U87) and no reduced-motion handling were found in any CSS
  file read, though the surface area that would need them (chips, countdowns) doesn't exist live yet either
  — noted as a gap that will matter the moment the promise-state chip is actually built.

---

## What Phase 4 of `TASKS.md` actually requires, restated plainly

Given the sizing above, Phase 4's per-surface tasks (4.1–4.6) are **not** "wire an existing screen to real
data" for five of six surfaces and the shared shell — they are first builds. Even 4.1 (`01-driver-chat`,
the one surface with any live code) is closer to a rewrite than an extension: the current `DriverHome.tsx`
has no thread list, no option cards, no promise-state chip, no countdown, and is built on hand-rolled chat
rendering rather than the assistant-ui binding `TASKS.md` 4.1 and `TECH_STACK.md` §9 both assume as the
starting point. The shared queue component (`TASKS.md` 4.0, blocking 4.2/4.3) also has no live precursor —
`OpsHomes.tsx`'s lists are one-off, not the shared U23/`components.md` §19 component two surfaces are
supposed to consume.
