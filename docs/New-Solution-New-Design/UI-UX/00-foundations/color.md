# Color

> Structure follows Checklist Design's *Color System* checklist. Decisions follow `../README.md` U7,
> U10, U14, U30.

## The hue budget — read this first

Seven dimensions in this product compete for colour: promise state (4 values), priority (4), ETA
confidence (3), TTL urgency, escalation severity, dock status, and displacement warning. Encoding all
seven in hue produces a rainbow where nothing reads as urgent because everything is coloured.

**So hue is rationed.** Only two things get it:

| Gets hue | Does not get hue | Encoded instead as |
|---|---|---|
| **Promise state** — the one thing that must never be misread (§7.2b) | Priority | Neutral **value** ramp on a left edge marker — CRITICAL darkest, LOW lightest |
| **Danger** — expiry, conflict, displacement, escalation | ETA confidence | Icon (`alert-triangle` for LOW, nothing for MEDIUM/HIGH) |
| | Dock status | Pattern fill + reduced opacity on the dock board |
| | TTL urgency | The state's own hue *warming toward danger* as time runs out (below) |

Priority as a value ramp rather than a hue is the non-obvious call. A planner scans the queue for
CRITICAL, and a dark-to-light bar scans faster than four hues that each also mean something else
elsewhere. It also leaves red exclusively meaning *danger*, so a CRITICAL row never looks like a failing
row.

---

## Primitive palette

Raw material only. **No component may reference a primitive directly** — components consume semantic
tokens (next section), which is what makes theming a single-file change rather than a find-and-replace.

Five ramps and a neutral. Restraint here is the point.

### Neutral — slate-tinted

Carries all structure, text and surfaces. Slightly cool because the product is operational, not warm.

```
neutral-0    #FFFFFF     neutral-500  #64748B
neutral-50   #F8FAFC     neutral-600  #475569
neutral-100  #F1F5F9     neutral-700  #334155
neutral-200  #E2E8F0     neutral-800  #1E293B
neutral-300  #CBD5E1     neutral-900  #0F172A
neutral-400  #94A3B8     neutral-950  #020617
```

### Blue — `PENDING_CONFIRMATION`, and primary action

```
blue-50  #EFF6FF    blue-300 #93C5FD    blue-600 #2563EB    blue-800 #1E40AF
blue-100 #DBEAFE    blue-400 #60A5FA    blue-700 #1D4ED8    blue-900 #1E3A8A
blue-200 #BFDBFE    blue-500 #3B82F6
```

### Amber — `HELD`

```
amber-50  #FFFBEB   amber-300 #FCD34D   amber-600 #D97706   amber-800 #92400E
amber-100 #FEF3C7   amber-400 #FBBF24   amber-700 #B45309   amber-900 #78350F
amber-200 #FDE68A   amber-500 #F59E0B
```

### Green — `CONFIRMED`

```
green-50  #ECFDF5   green-300 #6EE7B7   green-600 #059669   green-800 #065F46
green-100 #D1FAE5   green-400 #34D399   green-700 #047857   green-900 #064E3B
green-200 #A7F3D0   green-500 #10B981
```

### Red — danger only

Expiry, conflict lost, displacement warning, escalation, destructive actions. **Never** priority.

```
red-50  #FEF2F2     red-300 #FCA5A5     red-600 #DC2626     red-800 #991B1B
red-100 #FEE2E2     red-400 #F87171     red-700 #B91C1C     red-900 #7F1D1D
red-200 #FECACA     red-500 #EF4444
```

### Facility accent primitives (U59)

Single-purpose ramps — only the two steps actually used (light-mode 500/600, dark-mode 400/500) are
defined, not full nine-step families, since these hues exist for exactly one job. If a sixth-plus facility
or a new use ever needs more of a given ramp, extend it then rather than pre-building unused shades.

```
violet-400 #A78BFA   violet-500 #8B5CF6
teal-400   #2DD4BF   teal-500   #14B8A6
rose-400   #FB7185   rose-500   #F43F5E
cyan-400   #22D3EE   cyan-500   #06B6D4
lime-500   #84CC16   lime-600   #65A30D
orange-400 #FB923C   orange-500 #F97316
```

---

## Promise-state tokens — the core of the system

Four states, four redundant encodings (U14). Colour is one of four channels, never the only one.

| State | Hue | Icon (Lucide) | Border | Meaning of the shape |
|---|---|---|---|---|
| `SHOWN` | **Neutral** — deliberately uncoloured | `list` | 1px solid neutral | Nothing is reserved, so nothing is signalled |
| `HELD` | **Amber** | `timer` | **2px dashed** | Dashed = temporary. Yours briefly, not committed. |
| `PENDING_CONFIRMATION` | **Blue** | `clock-fade` | **2px solid** | Solid = a real request exists, awaiting a human |
| `CONFIRMED` | **Green** | `circle-check` | **2px solid** | Solid = committed |

**`SHOWN` having no hue is a deliberate design argument.** Nothing is reserved at that stage, so the
interface should not spend colour implying otherwise. Absence of colour reads as absence of commitment —
and it means the first time a driver sees colour on an option is the moment it actually became theirs.

**Dashed vs solid carries permanence independent of colour.** In greyscale, under sunlight, or for a user
with any colour vision deficiency, a dashed border still says *temporary*. That is why it is in the system
rather than a border colour change.

### Semantic tokens

```
                              LIGHT              DARK
state-shown-bg                neutral-50         neutral-800
state-shown-border            neutral-300        neutral-600
state-shown-text              neutral-700        neutral-200
state-shown-icon              neutral-500        neutral-400

state-held-bg                 amber-50           #3A2C10
state-held-border             amber-500          amber-500
state-held-text               amber-700          amber-400
state-held-icon               amber-600          amber-400

state-pending-bg              blue-50            #122040
state-pending-border          blue-500           blue-500
state-pending-text            blue-600           blue-400
state-pending-icon            blue-600           blue-400

state-confirmed-bg            green-50           #0B2F26
state-confirmed-border        green-600          green-500
state-confirmed-text          green-700          green-400
state-confirmed-icon          green-600          green-400
```

### The dark chip backgrounds are opaque hex, not an alpha composite (corrected 2026-08-26)

These three used to read `amber-900 @ 25%`, `blue-900 @ 25%`, `green-900 @ 25%` — and so did six more tokens
further down this file. **That notation was the error, and it was caught during the M5/E5.0 translation
pass.** Two reasons it had to be resolved before implementation rather than left as shorthand:

1. **The notation and the rendered mockup disagreed, and neither derived from the other.** `amber-900`
   `#78350F` at 25% over `neutral-900` composites to `#291E23`; `mockup-shared-shell.html` shipped `#3A2C10`.
   The computed composite is markedly duller — a chip that barely reads as amber, which undercuts the
   background's job as one of U14's four redundant channels.
2. **Alpha vs. opaque is not a cosmetic distinction.** A promise-state chip renders on cards, table rows,
   dock-board bars and inside popovers — four different backdrops. A translucent token is a *different
   colour* on each; an opaque one is identical everywhere. For the one component in this product that must
   never be misread, identical everywhere is the requirement.

**Resolution: the mockup's hexes are authoritative and the tokens are opaque.** Verified against their own
foreground text, computed not assumed:

| Pairing | Ratio | Verdict |
|---|---:|---|
| `amber-400` #FBBF24 on `#3A2C10` | **8.1:1** | AAA |
| `blue-400` #60A5FA on `#122040` | **6.3:1** | AA, AAA for large |
| `green-400` #34D399 on `#0B2F26` | **7.5:1** | AAA |
| `red-400` #F87171 on `#3A1414` | **5.9:1** | AA |

The six other affected tokens resolve to the same six hexes and are corrected in place below:
`surface-selected` and `interactive-selected-bg` → `#12203C`; `feedback-warning-bg` → `#3A2C10`;
`feedback-info-bg` → `#122040`; `feedback-success-bg` → `#0B2F26`; `feedback-danger-bg` → `#3A1414`.

Note `state-held-text` and `state-confirmed-text` use the **700** step in light mode while blue uses
**600**. That is not inconsistency — see *Contrast* below. Amber and green need one step darker than blue
and red to clear 4.5:1 on white.

---

## TTL urgency — the state hue warming toward danger

`HELD` (~90s) and `PENDING_CONFIRMATION` (15 min) expire while being watched. Rather than giving urgency
its own hue, the countdown **warms the state's existing colour toward red** as time runs out. The
component never changes identity; it changes temperature.

| Remaining | `HELD` countdown | `PENDING` countdown | Additional signal |
|---|---|---|---|
| > 50% | `amber-600` | `blue-600` | — |
| 20–50% | `amber-600` | `amber-600` | — |
| < 20% | `red-600` | `red-600` | Countdown switches to `font-weight: 600` |
| < 10s (HELD only) | `red-600` | — | Haptic pulse on driver device (U21) |
| Expired | `neutral-500` on `neutral-100` | same | Struck through; state chip replaced by the expiry message |

**Never animate the colour transition.** The value change should be perceptible as a *state* change, not
a gradual fade a user might not notice. Motion rules in `motion.md`.

---

## Priority — value ramp, no hue

Rendered as a 3px left edge marker on queue rows and cards, plus a text label. Neutral throughout.

```
                              LIGHT              DARK
priority-critical-marker      neutral-900        neutral-0
priority-high-marker          neutral-600        neutral-300
priority-normal-marker        neutral-400        neutral-500
priority-low-marker           neutral-200        neutral-700
```

Contrast against the row background is what makes CRITICAL scannable — near-black against white, or
near-white against near-black. The ramp inverts wholesale between themes rather than being remapped.

---

## Facility accent (U59) — hue that is safe to spend

Six facilities need a distinguishable identity in the app shell (the rail-edge stripe and the facility
switcher, `components.md` §7). This looks like it breaks the hue budget stated at the top of this file —
it doesn't, because **position makes it safe, not restraint.**

The four semantic hues (blue, amber, green, red) carry meaning *wherever they appear* — a chip, a border,
a banner. Facility accent is different: it is confined to **exactly two locations**, and those two
locations never render a promise state, a feedback colour, or anything else that could be confused with
it. A colour that only ever appears on the rail edge and in the switcher cannot be misread as a state,
because no state-bearing component ever borrows that position.

```
                              LIGHT              DARK
facility-1 (violet)           violet-500         violet-400
facility-2 (teal)             teal-500           teal-400
facility-3 (rose)             rose-500           rose-400
facility-4 (cyan)             cyan-500           cyan-400
facility-5 (lime)             lime-600           lime-500
facility-6 (orange)           orange-500         orange-400
```

Assigned by creation order, not by any operational meaning — a facility does not "deserve" a particular
hue, and the mapping must stay stable once assigned so a coordinator's spatial memory of "Jaipur is
violet" doesn't get invalidated by a later facility's onboarding.

**Rule, stated plainly because it is the whole safety argument:** facility accent renders **only** as the
4px rail-edge stripe (`spacing-and-layout.md`) and as a small swatch beside the facility name in the
switcher. It never appears on a chip, a card border, a table row, or any content surface. The moment it
does, this section's safety argument no longer holds and the hue budget has genuinely been broken.

---

## Escalation severity

The SLA clock inside the escalation stepper (`components.md` §16, U60) is the **only** element in the
escalation lifecycle permitted to carry danger colour — the four lifecycle steps themselves are neutral,
because "where is this in its process" and "is this in trouble" are different questions and conflating
them (e.g. colouring every step red once one deadline is close) would blur both.

```
                              LIGHT              DARK
escalation-sla-ok              text-secondary     text-secondary     (no colour — normal state)
escalation-sla-warning         amber-600          amber-400          (< 25% of SLA window remaining)
escalation-sla-breach          red-600            red-400            (SLA missed)
```

Uses the existing `red`/`amber` ramps — this is not a new primitive, just a new semantic assignment,
consistent with the rule that danger always reads as danger regardless of which specific thing is wrong.

---

## Feedback colors

Distinct from promise state. These are system feedback about an *action*, not the state of a promise.

```
                              LIGHT              DARK
feedback-success-bg           green-50           #0B2F26
feedback-success-text         green-700          green-400
feedback-success-border       green-600          green-500

feedback-warning-bg           amber-50           #3A2C10
feedback-warning-text         amber-700          amber-400
feedback-warning-border       amber-500          amber-500

feedback-danger-bg            red-50             #3A1414
feedback-danger-text          red-700            red-400
feedback-danger-border        red-600            red-500

feedback-info-bg              blue-50            #122040
feedback-info-text            blue-700           blue-400
feedback-info-border          blue-500           blue-500
```

**The collision risk is real and must be designed around.** `feedback-success` and `state-confirmed` share
green; `feedback-warning` and `state-held` share amber. They are distinguished by *shape and placement*,
not colour: promise state always appears as a bordered chip with its icon, in a fixed position within a
card or row. Feedback always appears as a toast, banner or inline form message. A green chip in the state
slot means CONFIRMED; a green banner across the top means an action succeeded. Never render feedback in
the state slot.

---

## Surface and text tokens

**Default theme is light, everywhere, for every role (U69).** Both themes are fully specified at parity
(U7) and every user can switch and have the choice persisted — but the shipped default is one consistent
choice, not per-surface. Two reasons: light is the only safe default on the two field surfaces (glare,
`components.md` §2's filled-chip rule), and a single global default means two planners sitting side by
side see the same thing unless one of them has deliberately chosen otherwise — which matters for support
and for screenshots used in training. Following `prefers-color-scheme` per surface was considered and
rejected for the same reason: it would let two internal screens disagree with each other by accident.

```
                              LIGHT              DARK
surface-base                  neutral-50         neutral-950
surface-raised                neutral-0          neutral-900
surface-floating              neutral-0          neutral-800
surface-overlay               neutral-0          neutral-800
surface-sunken                neutral-100        neutral-950
surface-hover                 neutral-100        neutral-800
surface-selected              blue-50            #12203C
surface-inverse               neutral-900        neutral-200
surface-inverse-fg            neutral-50         neutral-900

text-primary                  neutral-900        neutral-50
text-secondary                neutral-600        neutral-300
text-tertiary                 neutral-500        neutral-400
text-disabled                 neutral-400        neutral-600
text-inverse                  neutral-0          neutral-900
text-link                     blue-600           blue-400

border-subtle                 neutral-200        neutral-800
border-default                neutral-300        neutral-700
border-strong                 neutral-400        neutral-600
border-floating               neutral-200        neutral-700
border-focus                  blue-600           blue-400
```

**`surface-sunken` is deliberately identical to `surface-base` in dark, and that is not an oversight.**
`neutral-950` is the floor — there is nothing darker to recess into. Sunken therefore expresses itself in
dark mode the same way `elevation-and-depth.md`'s Level 1 already does: **through a 1px `border-subtle`, not
a fill step.** Any sunken container (the segmented control's track, a code block, an inset panel) carries
that border unconditionally, in both themes, which is why the segmented control reads correctly in dark
despite its fill matching the page. A sunken surface with no border is a bug in the component, not a gap in
this table. Added 2026-08-26 during the M5/E5.0 pass, where mapping shadcn's `--muted` onto this token
surfaced the collision.

`surface-inverse` exists for exactly one thing today — the tooltip ground, which is intentionally the
opposite polarity of everything around it. It was found missing when the shared-shell mockup's tooltip was
caught reaching `neutral-900` directly (U85). It is a *functional* token rather than a component-scoped one
because a second inverted surface is plausible (a toast on a light ground, a keyboard-shortcut key cap);
if it stays single-use for long, demote it.

Dark mode raises surfaces by *lightening* (`neutral-950` base → `neutral-900` raised) rather than by
shadow, since shadow is nearly invisible on dark grounds. Full treatment in `elevation-and-depth.md`.

---

## Interactive state colors

Applied consistently to every interactive element. Button-specific mappings are in `components.md`.

```
                              LIGHT              DARK
interactive-default           blue-600           blue-500
interactive-hover             blue-700           blue-400
interactive-pressed           blue-800           blue-300
interactive-on                neutral-0          neutral-950
interactive-disabled-bg       neutral-200        neutral-800
interactive-disabled-text     neutral-400        neutral-600
interactive-focus-ring        blue-600           blue-400
interactive-selected-bg       blue-50            #12203C

destructive-bg                red-600            red-500
destructive-on                neutral-0          neutral-950
```

**`interactive-on` is the fix for a real bug, so it is worth naming rather than assuming.** It is the
foreground that sits *on* `interactive-default` — white in light, `neutral-950` in dark. Until 2026-08-26
this existed only as prose inside `components.md` §1's variant table ("text white" / "text neutral-950"),
which meant components had nothing to reference and hardcoded `neutral-0`. The shared shell's notification
count badge did exactly that, and in dark mode rendered **white on `blue-500` at 3.7:1 — below AA** for its
10px label. Referencing `interactive-on` yields `neutral-950` on `blue-500` at **5.5:1** and passes. Any
filled interactive surface uses this token for its foreground; `destructive-on` is the same idea for the
`destructive` variant's red fill.

**Focus ring is 2px solid with a 2px offset**, never a subtle glow. Planners operate the queue by keyboard
(§7.3), so focus must be unambiguous at a glance — and a glow disappears against a coloured row background.

---

## Control-support tokens (added 2026-08-26)

Small, unglamorous tokens that existed only inside the shared-shell mockup's CSS or as prose in
`components.md`, and were therefore being hardcoded to primitives by the components that needed them. Every
one is here because a real component reached a tier too deep for lack of a name (U85), not because the
palette needed enriching.

```
                              LIGHT              DARK
switch-track-off              neutral-300        neutral-700
switch-knob                   neutral-0          neutral-50
marker-unmet                  neutral-500        neutral-400
avatar-bg                     neutral-600        neutral-400
avatar-fg                     neutral-0          neutral-950
skeleton                      neutral-200        neutral-800
scrim                         rgba(15,23,42,.5)  rgba(0,0,0,.65)
urgent                        red-600            red-400
```

**`switch-track-off` is the other bug this batch fixed.** `components.md` §12 lists the toggle as a standard
control but never gave its track a colour, so the mockup hardcoded `neutral-300` with no dark override — a
light-grey pill on a near-black card, and because it reached a primitive, **no theme override could reach
it.** That is the failure mode `tokens.md` exists to prevent, caught in the one place it had already
happened. The disabled knob deliberately reuses `interactive-disabled-text` rather than getting a fifth
token: low contrast against `interactive-disabled-bg` is the correct appearance for a disabled control.

`marker-unmet` is the neutral dot on an unmet password requirement (`components.md` §12's "a check when met,
a neutral dot when not"). The *shape* carries the meaning, so the dot is not required to clear 3:1 — but it
matches `text-tertiary`'s value so the marker and its label read as one unit.

`avatar-bg`/`avatar-fg` are a pair rather than a reuse of `surface-inverse`, on purpose: reusing the inverse
pair would have turned the avatar from a mid-grey circle into a near-black one, and this pass was correcting
tier violations, not changing rendered colours. Both pairings clear 8:1.

---

## Contrast

Target is **WCAG 2.2 AA**: 4.5:1 for normal text, 3:1 for large text and UI components (U30).

### Verified pairings — light mode on `neutral-0`

Computed, not assumed:

| Foreground | Ratio | Verdict |
|---|---:|---|
| `neutral-900` #0F172A | **17.9:1** | Passes AAA comfortably |
| `blue-600` #2563EB | **5.2:1** | Passes AA for normal text |
| `red-600` #DC2626 | **4.8:1** | Passes AA for normal text |
| `green-700` #047857 | **5.6:1** | Passes AA for normal text |
| `green-600` #059669 | **3.8:1** | ✗ Fails normal text — UI/large only |
| `amber-700` #B45309 | **5.1:1** | Passes AA for normal text |
| `amber-600` #D97706 | **3.2:1** | ✗ Fails normal text — UI/large only |

**This is why the token table uses 700 for amber and green text but 600 for blue and red.** Amber and
green are perceptually lighter at equivalent steps. Using `green-600` for body text would fail — a real
trap, since it looks fine to a designer with good vision on a good monitor.

### Verified pairings — dark mode on `neutral-900`

| Foreground | Ratio | Verdict |
|---|---:|---|
| `blue-400` #60A5FA | **7.0:1** | Passes AAA |
| `green-400` #34D399 | **9.3:1** | Passes AAA |
| `amber-400` #FBBF24 | **10.7:1** | Passes AAA |
| `red-400` #F87171 | **6.5:1** | Passes AAA |

Dark mode is comfortably clear throughout — the constrained theme is light, which is where verification
effort belongs.

### Still to verify with a tool

Every token pair against every surface it can land on, in both themes — particularly coloured text on
`surface-selected` and `surface-hover` rather than on base. The ratios above cover the common cases;
the combinatorial set needs a checker in CI, not a spreadsheet maintained by hand.

### Field-condition contrast — beyond AA

Driver and gate surfaces are used in direct sunlight, where effective contrast collapses (U30).

- **Light theme is the default on both**, and dark theme carries an explicit warning that it is hard to
  read outdoors.
- Body text on those two surfaces uses `text-primary` only — `text-secondary` is reserved for genuinely
  secondary content and never for anything operational.
- Promise-state chips on driver and gate use the **filled** variant (coloured background, not just a
  border) so state survives glare.

---

## Colour blindness

Colour never carries meaning alone anywhere in this system (U14, U30). The specific risks:

| Risk | Mitigation |
|---|---|
| **Amber vs green** (deuteranopia/protanopia) — `HELD` vs `CONFIRMED` is the dangerous confusion in this product | Different icons (`timer` vs `circle-check`), different borders (dashed vs solid), different labels. Three channels survive. |
| **Red vs green** — danger vs confirmed | Same three channels, plus they rarely co-occur in one view |
| **Blue vs neutral** at low saturation — `PENDING` vs `SHOWN` | `PENDING` always carries a countdown; `SHOWN` never does. Presence of a timer is itself the signal. |

**Test protocol:** every screen containing promise states must be checked in greyscale and under
deuteranopia simulation, with the pass criterion being that all four states remain distinguishable. If a
screen fails, the fix is an additional non-colour channel, never a hue adjustment.

---

## Forced-colors mode (U87)

Windows High Contrast (`forced-colors: active`) overrides author colours system-wide with a small
user-chosen palette, and it is a real concern here specifically because **planner and admin are Windows
desktop surfaces.** The right posture, per platform guidance: make small surgical adjustments for
legibility, never attempt a bespoke forced-colors re-theme.

**What survives untouched, and why it's worth naming:** the promise-state chip's "never colour alone"
rule (U14) means all four states remain distinguishable under forced-colors with zero extra work — icon,
label and border shape carry the meaning regardless of what palette the OS substitutes. That is a direct
dividend of a decision made for an unrelated reason.

**What breaks, and needs the adjustment:** forced-colors strips `box-shadow` entirely. Our light-theme
elevation model is shadow-based (`elevation-and-depth.md`), so the entire layer hierarchy — which panel is
"above" which — flattens to nothing under this mode, and the dock board's depth encoding for
sequencer-proposal-vs-current-state goes with it. See `elevation-and-depth.md`'s border-fallback addition,
which is the actual fix; this section exists so the *reason* for that fallback is recorded next to the
palette it protects rather than only in the file that needed patching.

---

## Brand colour

There is no brand palette supplied for SetuHaul, and this system does not invent one. Blue-600 acts as the
primary action colour and carries whatever brand identity exists by default.

If a brand colour arrives later: map it into `interactive-*` and decorative surfaces only. It **must not**
be mapped onto any promise state, because those four hues are load-bearing for correctness and cannot be
reassigned for identity reasons. If the brand colour fails contrast, it is restricted to decorative
contexts and the accessible token continues to carry text and interactive roles.
