# Data formatting

> How *values* render — numerals, units, durations, truncation. Distinct from `voice-and-tone.md`, which
> governs sentences a person reads; this governs cells a planner scans in three seconds. New file, U81.
> Structure informed by PatternFly's UX-writing numerics/units guidance and Carbon's overflow-content
> pattern — the two mature-system precedents that address this as its own concern.

## Why this earns its own file rather than a section

Voice and formatting have different owners and different failure modes. A wrong *word* reads as an
awkward sentence. A wrong *format* reads as a wrong fact — a genuine `0 min wait` rendered as a blank
looks like missing data; a shipment ID end-truncated to hide its distinguishing suffix looks like a
different, adjacent shipment. These are correctness bugs wearing a formatting costume, and they belong
next to the components that render structured data (`components.md` §4's decision receipt, §6's data
table), not folded into prose-writing guidance.

---

## Numerals and digit grouping

- **Always numerals, never spelled out.** "3 shipments," never "three shipments," anywhere in the
  product — this is operational software, not editorial copy.
- **Locale digit grouping, via `Intl.NumberFormat`, never hand-built.** This project's operating locale is
  `en-IN`, where grouping is `1,00,000` (lakh/crore), not the `100,000` a naive `toLocaleString()` default
  or a hardcoded comma-every-three implementation would produce. This is not a translation concern —
  `typography.md`'s ~30% text-expansion allowance does not cover it — it is a **correctness** concern:
  getting digit grouping wrong in a capacity figure, a weight, or a distance is a misread, not an
  aesthetic flaw. Every count and quantity in the product goes through the same formatter.
- **Tabular numerals wherever numbers appear in a column or update live** — already stated in
  `typography.md`; restated here because it is a formatting rule, not only a type rule.

---

## Units

- **A space between number and unit, except percentages.** `75 kg`, `32 ft`, `18,500 kg` — but `75%`, no
  space. This is the one deliberate exception, and it's deliberate because percentages read as a single
  glued token in nearly every system that specifies this.
- **Never pluralise a unit symbol.** `60 kg`, not `60 kgs`. `25 ft`, not `25 fts`.
- **Prefer the full unit word over a symbol when space allows**, symbol only when genuinely
  space-constrained (a queue-row cell, a chip). `6 seconds ago` in a status line; `6s` only inside a
  countdown chip where `components.md` §3 already governs the format.
- **Weight is always `kg`** — the domain's own unit throughout `SOLUTION_DESIGN.md` (§5's `HEAVY_DOCK_
  REQUIRED_KG`, dock `max_vehicle_weight_kg`) — never converted to tonnes or displayed in mixed units
  within one view.

---

## Duration — two distinct grammars, never mixed

Two genuinely different kinds of duration appear in this product, and using one grammar for both is where
the driver chat and the planner queue would silently diverge on the same underlying fact:

| Kind | Grammar | Example | Where |
|---|---|---|---|
| **Counting down** | `M:SS`, mono, tabular (`components.md` §3) | `1:24`, `0:09` | `HELD`/`PENDING` countdowns |
| **Counting up / elapsed** | Relative-time bands, prose | `70 min late`, `8 minutes ago` | Decision receipt, lateness figures, "last synced" |

**Relative-time bands for counting-up durations** — via `Intl.RelativeTimeFormat`, never raw seconds:

| Actual elapsed | Rendered |
|---|---|
| < 60s | "Just now" — never "12 seconds ago," never milliseconds |
| 1–59 min | `"N minutes ago"` / `"N min late"` as context requires |
| 1–23 hr | `"N hours ago"` |
| ≥ 24 hr | Absolute date, facility-local (`voice-and-tone.md`'s timezone rule, U64) |

- **Never mix units within one range or figure.** `"10 to 75 seconds"`, not `"10 seconds to 1.25
  minutes"` — a range that changes unit mid-expression forces the reader to do a conversion just to
  compare the two ends.
- **A genuine zero renders as zero, never as blank or omitted.** The decision receipt's `0 min wait` is a
  real, meaningful fact — it is the difference between "arrived and waited zero minutes" and "we don't
  know how long they waited." Any renderer treating falsy values as blank silently turns a known fact into
  an unknown one, which is exactly the kind of drift `components.md` §4 already warns against ("render a
  gap, not a zero" — that rule is the mirror image of this one: a *missing* field renders as a gap, a
  *zero* field renders as zero, and the two must never look the same).

---

## Truncation

Governed by position, minimum retained length, and a mandatory disclosure — not by a bare `text-overflow:
ellipsis` left to do whatever it does by default.

| Rule | Detail |
|---|---|
| **Position depends on where the distinguishing characters are** | **End-truncate** free text (facility names, carrier names) where the start carries the identity: `"Rajasthan Roadlines Priv…"`. **Mid-truncate** identifiers whose distinguishing suffix matters: `SHP1015`-style IDs, longer references, anything where two values might share an identical prefix. `SH-2026-0819-00…17`, not `SH-2026-08…` — the latter destroys exactly the part that tells two shipments apart. |
| **An ellipsis stands for 3+ truncated characters** | Truncating one or two characters saves no space and only adds visual noise |
| **At least 4 non-truncated characters remain** | Below that, truncation has removed more information than it preserved |
| **Every truncated value carries a native `title` tooltip with the full string** | Reachable on focus, not hover-only — a keyboard-driven planner (U46) must be able to see the untruncated value without a pointer |
| **Never truncate**: page/section headings, promise-state chip labels, error and validation messages, the displacement warning (`components.md` §6 already states this for the data table specifically — restated here as the general rule it's an instance of) | These are exactly the strings where losing a word changes the meaning, not just the presentation |

**The planner queue is where this rule earns its keep.** Seven fields in a 30-second budget means carrier
names, facility names and driver names *will* overflow their columns. "At least 4 characters remain, plus
a focus-reachable tooltip" is what keeps a truncated row still decidable rather than merely readable.

---

## Absence: zero, unknown, and withheld are three different things

Extending the decision-receipt rule above into a general pattern, because it recurs beyond that one
component:

| State | Render as | Example |
|---|---|---|
| **A real zero** | The number `0`, with its unit | `0 min wait` |
| **Not yet known** | An explicit "—" or "not yet available," never blank | ETA confidence before a driver has declared one |
| **Known but not shown to this viewer** (scope) | The field is **absent from the DOM** (`components.md` §18's Hidden state), not rendered as "—" | A carrier viewing another carrier's aggregate figure — this must never even hint a value exists |

Collapsing any two of these three into the same visual treatment is a correctness bug, not a style choice
— it either fabricates a fact (blank read as zero) or leaks one (a scope-hidden field rendered the same
as a merely-unknown one, inviting the question "why can't I see this specific thing").
