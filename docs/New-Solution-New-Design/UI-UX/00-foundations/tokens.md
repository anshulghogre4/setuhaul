# Token architecture

> A naming grammar and tier model, separate from the actual values — which live in `color.md`,
> `typography.md`, `spacing-and-layout.md`, `elevation-and-depth.md` and `motion.md`. This file indexes
> those five and states the discipline that makes U51 ("shadcn consumed through our tokens, never its
> defaults") mechanically enforceable rather than a rule someone has to remember per component. New file,
> U85. Grammar and tier model adapted from Primer's published token-naming convention — the clearest
> first-party precedent found in research.

## Why architecture is a separate concern from values

The five value-holding files answer "what is `blue-600`." This file answers a different question: **which
things are allowed to reference `blue-600` directly, and which must go through an intermediate name.**
Without that discipline, "consumed through our tokens" degrades into per-component vigilance — every new
component either does it right by habit or doesn't, and nothing catches the drift. With it, a component
that reaches for a primitive instead of a functional token is visibly doing something wrong, structurally,
not just stylistically.

**U40/U59's facility accent is the concrete case this file exists to protect.** "Renders in exactly two
places — the rail-edge stripe and the facility switcher swatch — never on a chip, card, or row" is
currently *prose*, in `color.md` and `spacing-and-layout.md`. It already drifted once before this
checkpoint's audit caught it — referenced across three files before `color.md` defined it at all. Expressed
as a **component-tier token that exists only as `rail-stripe-borderColor` and
`facilitySwitcher-swatch-bgColor`, with no functional-tier alias**, the constraint becomes structural: there
is simply no token name available for a fourth place to reach for. That is a stronger guarantee than a
sentence anyone could reasonably forget while adding a fifth surface eight months from now.

---

## The three tiers

| Tier | Answers | Example | Who may reference it |
|---|---|---|---|
| **Base / primitive** | "What is this raw value?" | `blue-600`, `space-4`, `duration-base` | Only the functional tier. **Never a component directly.** |
| **Functional / semantic** | "What role does this play?" | `interactive-default`, `surface-raised`, `text-danger` | Any component, freely |
| **Component-scoped** | "What does *this specific thing* look like?" | `button-constructive-bg`, `rail-stripe-borderColor`, `promiseChip-held-borderStyle` | Only that component's own implementation |

This mirrors the structure already implicit across the five value files — `color.md`'s primitive ramps
versus its semantic tokens versus `components.md`'s per-component specs — but none of those files states
the *rule that the tiers exist and may not be skipped*. That rule is this file's entire content.

**The rule, stated once:** a component reaches for a functional token (`interactive-default`) or, where
one exists, its own component-scoped token (`button-constructive-bg`). It never reaches for a base
primitive (`blue-600`) directly. If a component needs a colour and no functional token fits, the fix is to
add a functional token — not to reach one tier deeper because it's faster this once.

---

## Naming grammar

`[namespace]-[pattern]-[variant]-[property]-[state]`, kebab-case. Only `property` is mandatory; the rest
apply as needed. Consistent with the dash/dot split already used informally across the foundation files
(dashes in the value tables, dots in prose cross-references like `color.md`'s `state-held-border`).

Examples already in use, retrofitted to this grammar for consistency going forward:

| Existing token | Reads as |
|---|---|
| `state-held-border` | `[pattern: state]-[variant: held]-[property: border]` |
| `interactive-disabled-bg` | `[pattern: interactive]-[variant: disabled]-[property: bg]` |
| `escalation-sla-breach` | `[pattern: escalation]-[variant: sla]-[state: breach]` |

**New component-scoped tokens follow `[component]-[variant]-[property]`**: `promiseChip-held-borderStyle`,
`rail-stripe-borderColor`, `button-constructive-bg`. camelCase within a segment, dashes between segments —
this keeps component-scoped tokens visually distinct from the functional tier's flatter kebab-case at a
glance, which is a second, free signal for which tier something belongs to.

**Modifier vocabularies, standardised** so every new token doesn't invent its own scale:

- Colour emphasis: `default | muted | emphasis`
- Density: `compact | comfortable | spacious` (already `spacing-and-layout.md`'s scale — restated here as
  the vocabulary any *new* density-aware token should reuse, rather than inventing e.g. `dense`/`loose`)

---

## What this does NOT change

- **The five value files stay markdown tables, reviewable prose-first**, per the deliberate choice
  recorded when `getdesign.md` was evaluated and skipped (`README.md`) — this file adds a naming
  discipline on top of that choice, it does not reverse it or propose a machine-readable token pipeline.
  If/when this system needs generated CSS variables or a Tailwind theme, the path is DTCG JSON as its own
  artifact, kept in sync with these tables — not a replacement for them.
- **Existing token names are not retroactively renamed.** The tier model applies to *new* tokens from this
  point forward, consistent with the evidence-status convention below being adopted the same way (U88) —
  a full renaming sweep across five files and every cross-reference is disproportionate effort for a
  naming-consistency gain, and can happen later in one dedicated pass if drift becomes a real problem
  rather than a theoretical one.

---

## Evidence-status convention (U88)

Adopted **going forward only** — the 74 decisions already in `README.md`'s log are not retroactively
tagged; this applies from this checkpoint's decisions onward.

Every new locked decision that cites an empirical number — a duration, a threshold, a count — states its
source in one line:

- **`Source: SOLUTION_DESIGN.md §7.2b`** — derived from the product spec
- **`Source: observed operations`** — drawn from real usage data, once any exists
- **`Source: assumption, untested`** — a number someone chose because it felt right, not yet validated

This product carries several load-bearing empirical numbers already — the 90-second hold, the 15-minute
pending TTL, the 30-second planner decision budget, the 7-field row, the 35-request spike. Right now
nothing in the decisions log distinguishes a number that traces to `SOLUTION_DESIGN.md` from one that was
a reasonable guess. Without a marker, they harden into folklore at equal strength, and the first person to
question the 90-second figure has no way to know from the doc alone whether it's negotiable or load-bearing.
The tag costs one clause per decision and answers that question permanently.
