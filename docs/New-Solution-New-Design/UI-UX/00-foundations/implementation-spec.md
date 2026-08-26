# Implementation spec — shared shell and design-system foundation

> **M5 / E5.0 (issue #35).** A translation of the existing foundations into buildable config. **This file
> defines no new design decisions.** Every value below is copied from a foundations file or from
> `mockup-shared-shell.html`, with its source named. Where a value has no source, or where two sources
> disagree, it is listed in §4 as a decision the owner has to make — not resolved here.
>
> Sources read for this pass, and only these: `tokens.md`, `color.md`, `typography.md`,
> `spacing-and-layout.md`, `elevation-and-depth.md`, `motion.md`, `components.md`,
> `accessibility-behaviour.md`, `mockup-shared-shell.html`, `stitch-prompts-shared-shell.md`,
> `TECH_STACK.md` §9, and the current `frontend/` config.
>
> **Read in the second pass** (2026-08-26, scope opened by the coordinator to close the two blockers):
> `SOLUTION_DESIGN.md` §2 and §7.5.1–§7.5.8, `iconography.md`, `auth-and-scoping.md`.
>
> **Still not read, deliberately**: `data-formatting.md`, `voice-and-tone.md`, `ai-chat-primitives.md`, and
> the six surface folders. The first two are needed by later epics, not E5.0 — see §4.4.
>
> **Status: build-ready, nothing open.** The mockup is at **32 artboards** (section G added: rail, status
> bar, facility switcher), rail destinations are derived per role (§4.1.2), the nine `"@ N%"` token
> notations are corrected to opaque hex, the U69-violating auto-dark switch is removed, both live
> accessibility bugs are fixed, eight functional tokens were added, all six §4.3 decisions are locked into
> the files that own them, and two rendering defects found by measuring a real render are fixed (§4.7).
> **Both forks are resolved: Tailwind v4** (no `tailwind.config.ts` — see §Tailwind version) and
> **theme persistence is client-only `localStorage`** (§4.5). Eight foundations files were amended; each
> edit is dated and reasoned inline.

---

## 0 · Starting point — what `frontend/` actually is today

Verified, not assumed:

| Fact | Consequence for E5.0 |
|---|---|
| `package.json`: React 19.2, Vite 8.2, TS 6.0, `react-router-dom` 7.18, `@supabase/supabase-js` 2.112, `oxlint`. **No Tailwind, no shadcn, no Radix, no `class-variance-authority`, no `clsx`/`tailwind-merge`.** | The whole styling layer is a green field. Nothing to migrate, nothing to keep. |
| `vite.config.ts` is 7 lines — `react()` plugin only. No path alias. | `@/*` must be added to **both** `vite.config.ts` (`resolve.alias`) and `tsconfig.app.json` (`paths`), or the shadcn CLI cannot write components. |
| `tsconfig.app.json` has no `baseUrl`/`paths`. | Same. This is the first blocking setup step, before any `shadcn init`. |
| `src/index.css` imports **Hanken Grotesk** from Google Fonts. | Delete. `typography.md` locks Inter + JetBrains Mono and nothing else. |
| `src/App.css` is **20 KB of hand-written CSS**, `:root { color-scheme: dark }`, palette `#0b1326`/`#b4c5ff`/`#4edea3`. | Retire wholesale. It is dark-only (contradicts U69's light default), uses a different neutral ramp, and a different accent. Do **not** layer Tailwind over it. |
| `src/` layout: `core/{auth,http}`, `features/{admin,auth,driver,operator}`, `layouts/`, `shared/ui/`. | The six-surface structure from the design phase does not match `features/` today (`operator` vs. the spec's separate ops / planner / gate / carrier). Renaming is an E5.0 call, not a design decision. |

**The delta is a replacement, not an extension.** Say that out loud in the epic, because "add Tailwind to
the frontend" and "replace the frontend's entire visual layer" are different-sized tasks.

---

## Tailwind version — **LOCKED: v4** (owner decision, 2026-08-26)

The original brief asked for "exact `tailwind.config.ts` values." **Tailwind v4 removed that file**, so this
was surfaced as a fork; it is now closed in v4's favour. **There is no `tailwind.config.ts` in this project.**
Theme values live in a `@theme` block in CSS, compile to real custom properties, and the legacy config is
only reachable via an explicit `@config` escape hatch we do not use. shadcn/ui fully supports v4 and its CLI
initialises v4 by default. ([shadcn/ui — Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4))

Why it was the right call for *this* product specifically, recorded so it is not relitigated:

| Concern | Why v4 |
|---|---|
| Two themes at full parity (U7) | Tokens are runtime CSS custom properties — `.dark` redefines them with no rebuild. Under v3 they compile into utilities and cannot change at runtime |
| `Light / Dark / System` control (prompt 4) | Same reason — a runtime switch, not a build variant |
| **Three densities** (U8) | `compact`/`comfortable`/`spacious`/`auth` are one variable set switched by a `data-density` attribute. v3 would need four compiled variants or a pile of `data-*` overrides |
| Enforcing the tier rule (U85) | `--color-*: initial` clears Tailwind's default palette so `bg-blue-600` **does not exist** — a component physically cannot reach a primitive through a class name. §1.0 |
| Vite 8 | `@tailwindcss/vite` plugin, no PostCSS chain |

The v3 `tailwind.config.ts` object that previously sat in §1.10 has been **deleted** rather than left as a
dormant alternative — a config file nobody should create is worse than no config file, because someone will
eventually create it. §1 is now the single source.

---

## 1 · The theme

### 1.0 The tier rule, made mechanical (U85)

`tokens.md` says a component may never reference a base primitive. In Tailwind that rule has a
**structural** enforcement, and it is worth taking:

- **Base primitives go in a plain `:root` block, NOT in `@theme`.** Only `@theme` entries generate
  utilities. If `neutral-500` is not in `@theme`, then `bg-neutral-500` **does not exist** — a component
  physically cannot reach a primitive through a class name.
- **Tailwind's own default colour palette must be cleared** with `--color-*: initial;` as the first line of
  `@theme`, otherwise `bg-blue-600` and `text-red-500` remain available from Tailwind's built-ins and the
  tier rule is unenforceable by inspection.
- **Functional tokens go in `@theme`** and are the only colour utilities that exist.
- **Component-scoped tokens** stay in the component's own CSS or as a local var; they never enter `@theme`.

This is not a stylistic preference. `mockup-shared-shell.html` contains **eleven** places where a component
reached a primitive because no functional token existed, and one of them is a live dark-mode defect — see
§4.2. Clearing the default palette is what stops that recurring in code.

### 1.1 Base primitives — `:root`, outside `@theme`

Verbatim from `color.md`. Not utility-generating.

```css
/* src/styles/primitives.css — tier 1. Referenced ONLY by the functional layer below. */
:root {
  /* neutral — slate-tinted */
  --neutral-0:#FFFFFF;  --neutral-50:#F8FAFC;  --neutral-100:#F1F5F9;
  --neutral-200:#E2E8F0; --neutral-300:#CBD5E1; --neutral-400:#94A3B8;
  --neutral-500:#64748B; --neutral-600:#475569; --neutral-700:#334155;
  --neutral-800:#1E293B; --neutral-900:#0F172A; --neutral-950:#020617;

  --blue-50:#EFF6FF;  --blue-100:#DBEAFE; --blue-200:#BFDBFE; --blue-300:#93C5FD;
  --blue-400:#60A5FA; --blue-500:#3B82F6; --blue-600:#2563EB; --blue-700:#1D4ED8;
  --blue-800:#1E40AF; --blue-900:#1E3A8A;

  --amber-50:#FFFBEB;  --amber-100:#FEF3C7; --amber-200:#FDE68A; --amber-300:#FCD34D;
  --amber-400:#FBBF24; --amber-500:#F59E0B; --amber-600:#D97706; --amber-700:#B45309;
  --amber-800:#92400E; --amber-900:#78350F;

  --green-50:#ECFDF5;  --green-100:#D1FAE5; --green-200:#A7F3D0; --green-300:#6EE7B7;
  --green-400:#34D399; --green-500:#10B981; --green-600:#059669; --green-700:#047857;
  --green-800:#065F46; --green-900:#064E3B;

  --red-50:#FEF2F2;  --red-100:#FEE2E2; --red-200:#FECACA; --red-300:#FCA5A5;
  --red-400:#F87171; --red-500:#EF4444; --red-600:#DC2626; --red-700:#B91C1C;
  --red-800:#991B1B; --red-900:#7F1D1D;

  /* facility accent — only the steps color.md actually defines (U59) */
  --violet-400:#A78BFA; --violet-500:#8B5CF6;
  --teal-400:#2DD4BF;   --teal-500:#14B8A6;
  --rose-400:#FB7185;   --rose-500:#F43F5E;
  --cyan-400:#22D3EE;   --cyan-500:#06B6D4;
  --lime-500:#84CC16;   --lime-600:#65A30D;
  --orange-400:#FB923C; --orange-500:#F97316;
}
```

### 1.2 Functional colour tokens — `@theme`

Naming convention: **where shadcn already has a name for the role, use shadcn's name** (`--color-card`,
`--color-muted-foreground`) so its primitives theme correctly with zero patching; **where shadcn has no
name for the role** (promise state, priority, facility accent, escalation, feedback), use our own
`color.md` name. Full shadcn mapping table in §2.

```css
/* src/styles/theme.css — tier 2. The only colour utilities that exist. */
@import "tailwindcss";

@custom-variant dark (&:where(.dark, .dark *));   /* class-based, NOT prefers-color-scheme — see §4.1.4 */

@theme {
  --color-*: initial;                              /* kill Tailwind's default palette (see §1.0) */

  /* ---- surfaces (color.md · Surface and text tokens) ---- */
  --color-background:        var(--neutral-50);    /* surface-base */
  --color-card:              var(--neutral-0);     /* surface-raised */
  --color-popover:           var(--neutral-0);     /* surface-floating, elevation tier 3 */
  --color-overlay:           var(--neutral-0);     /* surface-overlay, elevation tier 4 */
  --color-sunken:            var(--neutral-100);   /* surface-sunken — sunken surfaces ALWAYS carry a 1px border-subtle, both themes (color.md) */
  --color-hover:             var(--neutral-100);   /* surface-hover — same value as sunken in light; that is why §12's segmented hover is a text change */
  --color-selected:          var(--blue-50);       /* surface-selected */

  /* ---- text ---- */
  --color-foreground:        var(--neutral-900);   /* text-primary */
  --color-muted-foreground:  var(--neutral-600);   /* text-secondary */
  --color-subtle-foreground: var(--neutral-500);   /* text-tertiary */
  --color-disabled-foreground:var(--neutral-400);  /* text-disabled */
  --color-inverse-foreground:var(--neutral-0);     /* text-inverse */
  --color-link:              var(--blue-600);      /* text-link */

  /* ---- borders ---- */
  --color-border:            var(--neutral-200);   /* border-subtle  → shadcn --border */
  --color-input:             var(--neutral-300);   /* border-default → shadcn --input  */
  --color-strong:            var(--neutral-400);   /* border-strong */
  --color-ring:              var(--blue-600);      /* border-focus   → shadcn --ring   */

  /* ---- interactive (color.md · Interactive state colors) ---- */
  --color-primary:            var(--blue-600);     /* interactive-default */
  --color-primary-hover:      var(--blue-700);     /* interactive-hover */
  --color-primary-pressed:    var(--blue-800);     /* interactive-pressed */
  --color-primary-foreground: var(--neutral-0);    /* interactive-on */
  --color-disabled:           var(--neutral-200);  /* interactive-disabled-bg */

  /* ---- control support (color.md §Control-support tokens) ---- */
  --color-switch-track-off: var(--neutral-300);
  --color-switch-knob:      var(--neutral-0);
  --color-marker-unmet:     var(--neutral-500);
  --color-avatar:           var(--neutral-600);
  --color-avatar-foreground:var(--neutral-0);
  --color-skeleton:         var(--neutral-200);
  --color-inverse:          var(--neutral-900);    /* surface-inverse — tooltip ground */
  --color-inverse-foreground:var(--neutral-50);

  /* ---- promise state (color.md · the core of the system) ---- */
  --color-state-shown-bg:      var(--neutral-50);
  --color-state-shown-border:   var(--neutral-300);
  --color-state-shown-text:     var(--neutral-700);
  --color-state-shown-icon:     var(--neutral-500);
  --color-state-held-bg:        var(--amber-50);
  --color-state-held-border:    var(--amber-500);
  --color-state-held-text:      var(--amber-700);
  --color-state-held-icon:      var(--amber-600);
  --color-state-pending-bg:     var(--blue-50);
  --color-state-pending-border: var(--blue-500);
  --color-state-pending-text:   var(--blue-600);
  --color-state-pending-icon:   var(--blue-600);
  --color-state-confirmed-bg:     var(--green-50);
  --color-state-confirmed-border: var(--green-600);
  --color-state-confirmed-text:   var(--green-700);
  --color-state-confirmed-icon:   var(--green-600);

  /* ---- priority — neutral VALUE ramp, never a hue (U10) ---- */
  --color-priority-critical: var(--neutral-900);
  --color-priority-high:     var(--neutral-600);
  --color-priority-normal:   var(--neutral-400);
  --color-priority-low:      var(--neutral-200);

  /* ---- TTL urgency (color.md · TTL urgency) ---- */
  --color-urgent:      var(--red-600);
  --color-urgent-mid:  var(--amber-600);
  --color-expired-fg:  var(--neutral-500);
  --color-expired-bg:  var(--neutral-100);

  /* ---- feedback — never rendered in a state slot (color.md) ---- */
  --color-success-bg:  var(--green-50);  --color-success-fg: var(--green-700);  --color-success-border: var(--green-600);
  --color-warning-bg:  var(--amber-50);  --color-warning-fg: var(--amber-700);  --color-warning-border: var(--amber-500);
  --color-danger-bg:   var(--red-50);    --color-danger-fg:  var(--red-700);    --color-danger-border:  var(--red-600);
  --color-info-bg:     var(--blue-50);   --color-info-fg:    var(--blue-700);   --color-info-border:    var(--blue-500);
  --color-destructive: var(--red-600);   --color-destructive-foreground: var(--neutral-0);

  /* ---- escalation SLA — the only danger colour in the stepper (U60) ---- */
  --color-sla-ok:      var(--neutral-600);   /* = text-secondary, i.e. no colour */
  --color-sla-warning: var(--amber-600);
  --color-sla-breach:  var(--red-600);

  /* ---- facility accent (U59) — see §1.3 for the two-place restriction ---- */
  --color-facility-1: var(--violet-500);
  --color-facility-2: var(--teal-500);
  --color-facility-3: var(--rose-500);
  --color-facility-4: var(--cyan-500);
  --color-facility-5: var(--lime-600);
  --color-facility-6: var(--orange-500);
}

/* ---- dark theme: same token names, different primitives (elevation-and-depth.md) ---- */
.dark {
  --color-background:        var(--neutral-950);
  --color-card:              var(--neutral-900);
  --color-popover:           var(--neutral-800);
  --color-overlay:           var(--neutral-800);
  --color-sunken:            var(--neutral-950);   /* identical to background by design — the border carries it */
  --color-hover:             var(--neutral-800);
  --color-selected:          #12203C;              /* opaque (color.md) */

  --color-foreground:        var(--neutral-50);
  --color-muted-foreground:  var(--neutral-300);
  --color-subtle-foreground: var(--neutral-400);
  --color-disabled-foreground:var(--neutral-600);
  --color-inverse-foreground:var(--neutral-900);
  --color-link:              var(--blue-400);

  --color-border:            var(--neutral-800);
  --color-input:             var(--neutral-700);
  --color-strong:            var(--neutral-600);
  --color-ring:              var(--blue-400);

  --color-primary:            var(--blue-500);
  --color-primary-hover:      var(--blue-400);
  --color-primary-pressed:    var(--blue-300);
  --color-primary-foreground: var(--neutral-950);  /* NOT neutral-0 — see color.md's interactive-on note */
  --color-disabled:           var(--neutral-800);

  --color-switch-track-off: var(--neutral-700);
  --color-switch-knob:      var(--neutral-50);
  --color-marker-unmet:     var(--neutral-400);
  --color-avatar:           var(--neutral-400);
  --color-avatar-foreground:var(--neutral-950);
  --color-skeleton:         var(--neutral-800);
  --color-inverse:          var(--neutral-200);
  --color-inverse-foreground:var(--neutral-900);

  --color-state-shown-bg:      var(--neutral-800);
  --color-state-shown-border:   var(--neutral-600);
  --color-state-shown-text:     var(--neutral-200);
  --color-state-shown-icon:     var(--neutral-400);
  --color-state-held-bg:        #3A2C10;           /* opaque, verified 8.1:1 vs amber-400 (color.md) */
  --color-state-held-border:    var(--amber-500);
  --color-state-held-text:      var(--amber-400);
  --color-state-held-icon:      var(--amber-400);
  --color-state-pending-bg:     #122040;           /* opaque, verified 6.3:1 vs blue-400 */
  --color-state-pending-border: var(--blue-500);
  --color-state-pending-text:   var(--blue-400);
  --color-state-pending-icon:   var(--blue-400);
  --color-state-confirmed-bg:     #0B2F26;         /* opaque, verified 7.5:1 vs green-400 */
  --color-state-confirmed-border: var(--green-500);
  --color-state-confirmed-text:   var(--green-400);
  --color-state-confirmed-icon:   var(--green-400);

  --color-priority-critical: var(--neutral-0);
  --color-priority-high:     var(--neutral-300);
  --color-priority-normal:   var(--neutral-500);
  --color-priority-low:      var(--neutral-700);

  --color-urgent:      var(--red-400);
  --color-urgent-mid:  var(--amber-400);
  --color-expired-fg:  var(--neutral-400);
  --color-expired-bg:  var(--neutral-800);

  --color-success-bg: #0B2F26; --color-success-fg: var(--green-400); --color-success-border: var(--green-500);
  --color-warning-bg: #3A2C10; --color-warning-fg: var(--amber-400); --color-warning-border: var(--amber-500);
  --color-danger-bg:  #3A1414; --color-danger-fg:  var(--red-400);   --color-danger-border:  var(--red-500);
  --color-info-bg:    #122040; --color-info-fg:    var(--blue-400);  --color-info-border:    var(--blue-500);
  --color-destructive: var(--red-500); --color-destructive-foreground: var(--neutral-950);

  --color-sla-ok:      var(--neutral-300);
  --color-sla-warning: var(--amber-400);
  --color-sla-breach:  var(--red-400);

  --color-facility-1: var(--violet-400);
  --color-facility-2: var(--teal-400);
  --color-facility-3: var(--rose-400);
  --color-facility-4: var(--cyan-400);
  --color-facility-5: var(--lime-500);
  --color-facility-6: var(--orange-400);
}
```

The `#RRGGBB` values in `.dark` are now **`color.md`'s own values**, not the mockup's. The `"@ N%"` notation
that used to sit in those nine slots was corrected in place on 2026-08-26: the tokens are **opaque**, not
alpha composites, because a promise-state chip renders on four different backdrops and must be the same
colour on all of them. All four chip pairings were contrast-verified during that correction — see
`color.md` §*The dark chip backgrounds are opaque hex*.

### 1.3 Two tokens that exist only as component-scoped names (U59, `tokens.md`)

Deliberately **not** in `@theme`. `tokens.md` is explicit that the facility-accent restriction becomes
structural only if there is no functional alias for a third place to reach for.

```css
/* src/components/shell/rail.css */
.rail        { border-inline-start: 4px solid var(--rail-stripe-borderColor); }
/* src/components/shell/facility-switcher.css */
.fac-swatch  { background: var(--facilitySwitcher-swatch-bgColor); }
```

Both are set from the active facility's `--color-facility-N` **at the shell root only**. `--color-facility-*`
must never appear in any other selector. This is worth an ESLint/stylelint rule, not just a convention:
grep for `color-facility` in a pre-commit hook and fail on any hit outside those two files.

### 1.4 Typography

Values from `typography.md`. In `rem` at a 16px root, per its accessibility rule.

```css
@theme {
  --font-ui:   'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-data: 'JetBrains Mono', 'SF Mono', 'Cascadia Mono', Consolas, monospace;
  --font-sans: var(--font-ui);    /* so shadcn primitives inherit correctly */
  --font-mono: var(--font-data);

  --text-display: 2rem;      --text-display--line-height: 1.25; --text-display--font-weight: 700; --text-display--letter-spacing: -0.02em;
  --text-h1:      1.5rem;    --text-h1--line-height: 1.33;      --text-h1--font-weight: 600;      --text-h1--letter-spacing: -0.01em;
  --text-h2:      1.25rem;   --text-h2--line-height: 1.4;       --text-h2--font-weight: 600;      --text-h2--letter-spacing: -0.01em;
  --text-h3:      1rem;      --text-h3--line-height: 1.5;       --text-h3--font-weight: 600;      --text-h3--letter-spacing: 0em;
  --text-body:    0.875rem;  --text-body--line-height: 1.5;     --text-body--font-weight: 400;    --text-body--letter-spacing: 0em;
  --text-body-lg: 1rem;      --text-body-lg--line-height: 1.5;  --text-body-lg--font-weight: 400; --text-body-lg--letter-spacing: 0em;
  /* typography.md's `text-sm` (13px) — registered under a non-colliding name.
     Tailwind's built-in text-sm (14px) is deliberately left alone. */
  --text-supporting: 0.8125rem; --text-supporting--line-height: 1.4; --text-supporting--font-weight: 400; --text-supporting--letter-spacing: 0em;
  --text-label:   0.75rem;   --text-label--line-height: 1.33;   --text-label--font-weight: 600;   --text-label--letter-spacing: 0.04em;
  --text-micro:   0.6875rem; --text-micro--line-height: 1.3;    --text-micro--font-weight: 500;   --text-micro--letter-spacing: 0.02em;
}
```

Three things a developer will get wrong without being told:

1. **`typography.md`'s `text-sm` (13px) is the `text-supporting` utility.** Locked 2026-08-26 and written
   into `typography.md`. Tailwind's built-in `text-sm` stays at 14px, which coincides with `text-body`'s
   size, so shadcn primitives that ship `text-sm` land on the right size unpatched. In our own components,
   use `text-body` or `text-supporting` explicitly — `text-sm` in a search means "shadcn shipped this."
   Clearing the type namespace with `--text-*: initial`, the trick that enforces the tier rule for colour,
   was rejected here: it makes `text-xs`/`text-base`/`text-lg` unknown utilities and breaks every shadcn
   primitive at install time.
2. **`text-label` and `text-micro` are the only tokens carrying tracking.** `typography.md`: never
   letterspace lowercase body text.
3. **`tabular-nums` is not optional.** Every table numeric cell, every countdown, every queue position:
   `font-variant-numeric: tabular-nums`. Apply it as a base rule on `.font-mono` and on table `td`
   containing numbers, rather than remembering it per component.

**Font loading.** `typography.md` says load Inter 400/500/600/700 and JetBrains Mono 400/500, Latin subset
only, because a driver on a cheap Android pays for every weight. The mockup uses a Google Fonts CDN `<link>`
— fine for a mockup, wrong for the PWA (extra DNS + connection before first paint). **Recommendation
(performance, not a spec requirement): self-host `woff2` subsets via `@font-face` with `font-display: swap`,
six files total.** No foundations file states a hosting method, so this is an engineering call.

### 1.5 Spacing, radius, breakpoints — three happy alignments, verified

| Scale | Tailwind v4 default | `spacing-and-layout.md` | Action |
|---|---|---|---|
| Spacing | `--spacing: 0.25rem`, dynamic multiples | 4px base unit; `space-1..20` = 4..80px | **None.** `p-4` is exactly `space-4` (16px). Do not redeclare. |
| Breakpoints | sm 40rem / md 48rem / lg 64rem / xl 80rem / 2xl 96rem | `bp-sm` 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536 | **None.** Identical. |
| Radius | derives sm/md/lg/xl from one `--radius` | 4 / 6 / 8 / 12px | **Set `--radius: 0.5rem`.** shadcn's chain is `sm = r−4px`, `md = r−2px`, `lg = r`, `xl = r+4px` → **4 / 6 / 8 / 12px exactly.** Zero overrides. |

`radius-full` (9999px) is Tailwind's `rounded-full`. Per `spacing-and-layout.md`, it is permitted on
avatars, count badges and toggle switches only.

### 1.6 Density — a runtime attribute, not three builds (U8)

`spacing-and-layout.md`: density changes padding and row height **only** — never type size, never border
width, never icon size. That is expressible as one variable set switched by an attribute on the shell root.

```css
[data-density="compact"]     { --row-h:36px; --cell-py:8px;  --cell-px:12px; --card-p:12px; --stack:8px;  --tap:32px; --btn-h:32px; --content-p:16px; }
[data-density="comfortable"] { --row-h:44px; --cell-py:12px; --cell-px:16px; --card-p:16px; --stack:12px; --tap:44px; --btn-h:40px; --content-p:24px; }
[data-density="spacious"]    { --row-h:64px; --cell-py:20px; --cell-px:24px; --card-p:24px; --stack:16px; --tap:56px; --btn-h:56px; --content-p:32px; }
/* auth + full-page states: comfortable, with 44px controls (spacing-and-layout.md, added 2026-08-26) */
[data-density="auth"]        { --row-h:44px; --cell-py:12px; --cell-px:16px; --card-p:16px; --stack:12px; --tap:44px; --btn-h:44px; --content-p:24px; }
```

Surface assignment, verbatim from `spacing-and-layout.md`: `compact` → planner, ops. `comfortable` →
carrier, admin, driver chat. `spacious` → gate kiosk. `auth` → sign-in, role picker, both reset screens, and
the five full-page states — the group the original table had no row for, resolved 2026-08-26 with a stated
44px control override because these screens are the *driver's* door as well as a desk user's. **Set once per
route at the shell root; never per component, and never as a user preference in v1.**

Consumed as `h-(--row-h)` / `p-(--card-p)` (v4's var shorthand). The `compact` 32px tap target is
`spacing-and-layout.md`'s one deliberate exception and is **pointer-only** — a lint rule that flags
`data-density="compact"` on any touch-target route is worth having, because that exception silently
degrades AAA to below-AA if a planner console is ever opened on a tablet.

### 1.7 Elevation

```css
:root {
  --shadow-raised:   0 1px 2px rgba(15,23,42,.06);
  --shadow-floating: 0 4px 12px rgba(15,23,42,.10);
  --shadow-overlay:  0 12px 32px rgba(15,23,42,.14);
  --scrim:           rgba(15,23,42,.5);
}
.dark {
  --shadow-raised:   none;                          /* dark tier 1 uses lightness, not shadow */
  --shadow-floating: 0 4px 12px rgba(0,0,0,.40);
  --shadow-overlay:  0 12px 32px rgba(0,0,0,.55);
  --scrim:           rgba(0,0,0,.65);
}
```

Named `raised`/`floating`/`overlay` rather than `sm`/`md`/`lg` **on purpose**: they map 1:1 onto
`elevation-and-depth.md`'s five layers, so a developer picks a layer rather than a shadow size, and
`shadow-raised` resolving to `none` in dark stops reading as a bug.

Registering these under Tailwind's `--shadow-*` namespace so `.dark` overrides propagate into the `shadow-*`
utilities is **the one v4 API detail to verify at scaffold time** rather than assume — if it does not
propagate, use `@utility elev-1 { box-shadow: var(--shadow-raised) }` and friends.

Two rules that are code, not styling:

- **Focus ring is two rings, always.** `shadow-focus` = 2px in the surface colour, then 2px in
  `--color-ring`. In v4: `outline-2 outline-ring outline-offset-2`. Never a glow. Planners operate the
  queue by keyboard, and a glow vanishes against a selected row.
- **Forced-colors fallback (U87) is mandatory, not a nicety.** Windows High Contrast strips every
  `box-shadow`, which flattens the entire light-theme layer model on planner and admin — the two Windows
  desktop surfaces. Ship this globally:

  ```css
  @media (forced-colors: active) {
    .elev-1, .elev-3, .elev-4 { border: 1px solid CanvasText; }
  }
  ```

  `CanvasText` and not one of our tokens, because our tokens are exactly what the OS is overriding.

### 1.8 Motion

```css
:root {
  --d-instant:0ms; --d-fast:120ms; --d-base:200ms; --d-slow:320ms;
  --e-out:cubic-bezier(0.16,1,0.3,1);
  --e-in:cubic-bezier(0.7,0,0.84,0);
  --e-in-out:cubic-bezier(0.65,0,0.35,1);
}
```

- **Skeleton shimmer is `animate-shim` at 1600ms, not Tailwind's `animate-pulse` at 2000ms.** Resolved
  2026-08-26 in `motion.md`'s favour and written into `components.md` §13 (U78's technique now names
  `animate-shim`). Register `--animate-shim: shim 1600ms var(--e-in-out) infinite` with the keyframe
  `@keyframes shim { 0%,100%{opacity:1} 50%{opacity:.55} }`. Do not reach for the built-in because its
  class name is shorter.
- **Reduced motion keeps information, drops decoration.** `motion.md` is explicit that countdown ticks and
  TTL colour warming stay **unchanged**, the `HELD` pulse is **replaced** by a solid high-contrast border
  plus an "expiring" label, and the arrival flash is **replaced** by a persistent "new" badge. So the
  global `*{transition-duration:0}` shortcut the mockup uses (line 638) is **wrong for the app** — it would
  silently delete an expiry warning for a user who set an OS preference. Implement per-motion, per
  `motion.md`'s table.
- **One shared 1 Hz interval for every countdown in the app**, not one timer per component (`components.md`
  §3). 35 pending rows must not run 35 timers. This is a `CountdownProvider` in E5.0's scope, not the
  planner epic's — every surface needs it.
- **Animate `transform` and `opacity` only.** Row expansion animates `transform: scaleY` on the panel, not
  `height`.

### 1.9 Z-index — needs explicit utilities, and Radix will fight you

`spacing-and-layout.md`'s nine-step scale has one **correctness** rule in it: `z-toast` (700) sits above
`z-modal` (600), because U41's time-boxed undo that can be hidden is no undo.

```css
@utility z-sticky      { z-index: 100; }
@utility z-shell       { z-index: 200; }
@utility z-rail-expand { z-index: 300; }
@utility z-dropdown    { z-index: 400; }
@utility z-drawer      { z-index: 500; }
@utility z-modal       { z-index: 600; }
@utility z-toast       { z-index: 700; }
@utility z-tooltip     { z-index: 800; }
```

**Every shadcn/Radix overlay primitive ships `z-50` and portals to `document.body`.** Out of the box, toast
and dialog are both `z-50` and DOM order decides who wins — which means the undo toast can end up behind a
dialog. Each of `dialog`, `sheet`, `dropdown-menu`, `popover`, `tooltip`, `sonner` must have its `z-50`
replaced with the matching utility above **as part of E5.0**, and it needs a test: open a modal, trigger an
undo, assert the toast is hittable.

## 2 · shadcn/ui theme variables and `components.json`

### 2.1 The mapping

shadcn's convention is `--token` / `--token-foreground` pairs. Ours is roles from `color.md`. This table is
the join. **Every row goes through a functional token — no row references a primitive** (U85).

| shadcn variable | Our functional token | Light | Dark | Note |
|---|---|---|---|---|
| `--background` | `surface-base` | `neutral-50` | `neutral-950` | |
| `--foreground` | `text-primary` | `neutral-900` | `neutral-50` | |
| `--card` | `surface-raised` | `neutral-0` | `neutral-900` | Elevation tier 1 |
| `--card-foreground` | `text-primary` | `neutral-900` | `neutral-50` | |
| `--popover` | `surface-floating` | `neutral-0` | `neutral-800` | Tier 3 |
| `--popover-foreground` | `text-primary` | `neutral-900` | `neutral-50` | |
| `--primary` | `interactive-default` | `blue-600` | `blue-500` | |
| `--primary-foreground` | — | `neutral-0` | `neutral-950` | From `components.md` §1 `constructive` |
| `--secondary` | `surface-hover` | `neutral-100` | `neutral-800` | **Mapping judgement.** We have no "secondary" role — see §2.3 |
| `--secondary-foreground` | `text-primary` | `neutral-900` | `neutral-50` | Same |
| `--muted` | `surface-sunken` | `neutral-100` | `neutral-950` | Equals `--background` in dark by design — **every muted/sunken surface carries a 1px `--border` in both themes**, which is what separates it. A `bg-muted` region with no border is a component bug (`color.md`) |
| `--muted-foreground` | `text-secondary` | `neutral-600` | `neutral-300` | |
| `--accent` | `surface-hover` | `neutral-100` | `neutral-800` | ⚠ **NOT the facility accent.** See §2.2 |
| `--accent-foreground` | `text-primary` | `neutral-900` | `neutral-50` | |
| `--destructive` | `feedback-danger-border` | `red-600` | `red-500` | shadcn dropped `--destructive-foreground`; we still need one (`neutral-0` / `neutral-950`) for the filled `destructive` button |
| `--border` | `border-subtle` | `neutral-200` | `neutral-800` | Cards, panels |
| `--input` | `border-default` | `neutral-300` | `neutral-700` | Inputs — exactly shadcn's intent |
| `--ring` | `border-focus` | `blue-600` | `blue-400` | |
| `--radius` | — | `0.5rem` | same | Derives 4/6/8/12 exactly (§1.5) |
| `--sidebar` | `surface-raised` | `neutral-0` | `neutral-900` | Icon rail = elevation tier 2 |
| `--sidebar-foreground` | `text-secondary` | `neutral-600` | `neutral-300` | Rest state; active item is `text-primary` |
| `--sidebar-primary` | `interactive-default` | `blue-600` | `blue-500` | The active item's 2px inner accent bar |
| `--sidebar-primary-foreground` | — | `neutral-0` | `neutral-950` | |
| `--sidebar-accent` | `surface-hover` | `neutral-100` | `neutral-800` | |
| `--sidebar-accent-foreground` | `text-primary` | `neutral-900` | `neutral-50` | |
| `--sidebar-border` | `border-default` | `neutral-300` | `neutral-700` | Tier 2's content-facing edge |
| `--sidebar-ring` | `border-focus` | `blue-600` | `blue-400` | |
| `--chart-1` … `--chart-5` | **no source** | — | — | **Do not invent.** U66 defers the sparkline's colour to the `dataviz` skill, which has not been run. If the CLI writes defaults, comment them `UNSOURCED — do not reference` |

Since §1.2 already names these tokens shadcn-compatibly, the `@theme inline` block is a thin alias layer:

```css
@theme inline {
  --color-secondary:            var(--color-hover);
  --color-secondary-foreground: var(--color-foreground);
  --color-muted:                var(--color-sunken);
  --color-accent:               var(--color-hover);
  --color-accent-foreground:    var(--color-foreground);
  --color-sidebar:              var(--color-card);
  --color-sidebar-foreground:   var(--color-muted-foreground);
  --color-sidebar-primary:      var(--color-primary);
  --color-sidebar-primary-foreground: var(--color-primary-foreground);
  --color-sidebar-accent:       var(--color-hover);
  --color-sidebar-accent-foreground:  var(--color-foreground);
  --color-sidebar-border:       var(--color-input);
  --color-sidebar-ring:         var(--color-ring);
  --radius: 0.5rem;
}
```

**Colour space:** shadcn's own theme ships `oklch()`. Ours are hex, from `color.md`. **Keep hex.** They are
the values every contrast ratio in `color.md` was computed against, and a hex→oklch conversion is a silent
opportunity to shift `green-600` off its measured 3.8:1. Convert later, deliberately, with the checker in
CI — never as part of a scaffold.

### 2.2 `--accent` is a name collision, and it is a trap

shadcn's `--accent` is the hover/active background for menu items, dropdowns, command palettes. **It has
nothing to do with U59's facility accent.** If someone maps `--accent: var(--color-facility-1)` — an
entirely reasonable-looking guess from the name — then every dropdown item, every command-palette row and
every calendar cell hover renders in the facility hue, and `color.md`'s entire safety argument for spending
that hue ("confined to exactly two locations") is gone in one line.

Mitigation, cheap: `--accent` maps to `surface-hover`, with the comment above it in the CSS, plus the
pre-commit grep from §1.3.

### 2.3 shadcn's Button variants do not match ours — re-author, don't re-theme

shadcn ships `default | secondary | destructive | outline | ghost | link`, named by **appearance**.
`components.md` §1 defines `constructive | neutral | cautionary | destructive | ghost`, named by
**consequence** — U12, and the whole point is that a new button must declare what it does.

Re-theming shadcn's variants keeps the appearance names and loses U12. **Rewrite the `cva` variant map with
our five names.** `cautionary` in particular has no shadcn equivalent at all (amber-tinted, for Escalate /
Get help). Three §1 rules also have to live in code, not in review notes:

- One `constructive` per view.
- `destructive` never adjacent to `constructive` — minimum 16px and a different visual group.
- **Safer action first in DOM order (U79)**, regardless of visual position, so a planner overshooting Tab
  in a 35-request spike lands on Reject before Confirm, never the reverse. The mockup does this correctly
  at line 1772 — Report before Try again.

### 2.4 `components.json`

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/theme.css",
    "baseColor": "slate",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/shared/ui",
    "utils": "@/shared/lib/utils",
    "ui": "@/shared/ui",
    "lib": "@/shared/lib",
    "hooks": "@/shared/hooks"
  },
  "iconLibrary": "lucide"
}
```

`"config": ""` is correct for v4 (no config file). `baseColor: "slate"` matches our slate-tinted neutral,
so any value the CLI writes before we override lands in the right family. `rsc: false` — Vite SPA, not Next.
`components` aliases into the existing `src/shared/ui/` rather than creating a second component root.

### 2.5 Packages E5.0 adds

```
tailwindcss @tailwindcss/vite tailwind-merge clsx class-variance-authority
@radix-ui/* (pulled per-component by the shadcn CLI, not installed wholesale)
lucide-react
sonner                       # toast — components.md §8
```

Deferred to their own epics, listed so nobody adds them early: `@assistant-ui/react` (driver chat, ops
co-pilot), Kibo UI Gantt via the shadcn/kibo CLI (planner board, §5), `vite-plugin-pwa` (driver PWA).

**PWA note:** the mockup declares `theme-color` `#E2E8F0` light / `#020617` dark (lines 6–7). `#E2E8F0` is
`neutral-200`, the **mockup board's** background, not an app surface. The real manifest should use
`#F8FAFC` (`surface-base`) or `#FFFFFF` (the top bar's `surface-raised`) for light. Small, but it is the
colour of the phone's status bar on the driver surface.

---

## 3 · The 32 shared-shell artboards

All in `docs/New-Solution-New-Design/UI-UX/00-foundations/mockup-shared-shell.html`. Line numbers are the
artboard's `<div class="cap">` — open the file at that line. Copy is authoritative in
`stitch-prompts-shared-shell.md` (prompt number in the last column).

### A · Signing in (5)

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 1 | Sign-in — at rest | 708 | `card`, `label`, `input`, `button` | One field "Email or phone", not two tabs. No Remember me / SSO / Sign up / social divider. Prompt 1 |
| 2 | Sign-in — password revealed, field focused | 744 | + `toggle` semantics on a `button` | Icon-only `button` inset in the field, `aria-pressed`, name flips Show/Hide password, `eye`/`eye-off`. Field reserves 40px right padding. **Not** a checkbox |
| 3 | Sign-in — "Those details don't match" | 780 | `alert` (`danger`) + field `aria-invalid` | Wording is identical whichever half was wrong — deliberate, anti-enumeration |
| 4 | Sign-in — rate limited | 821 | `alert` (`danger`) | "Too many attempts. Try again in 5 minutes." A cause and a next action |
| 5 | Role picker — multi-role only | 861 | plain `button` list — **not** `radio-group`, **not** `command` | Whole row is the target; activating proceeds immediately. No selected state, no Continue. **Never renders with one row** — single-role accounts skip it entirely. Prompt 2 |

### B · Password reset (5)

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 6 | Reset — request a link | 900 | `card`, `label`, `input`, `button` | Same 400px chassis as sign-in; continuity is the point. Prompt 3 |
| 7 | Reset — link sent | 931 | `alert` (`info`) | **Informational blue, never green.** Wording identical whether or not the account exists |
| 8 | Set a new password | 957 | `card`, two `input` + independent toggles, requirements list | Requirements carry a check/dot marker, never colour alone. ⚠ the two requirement strings are placeholders — mockup's own flag, line 992 |
| 9 | Set a new password — mismatch | 999 | field-level error | "Those two passwords don't match." `aria-describedby` |
| 10 | Reset link expired or already used | 1041 | empty-state block | Form is **not rendered at all** behind it. `link-2-off` 32px + "Request a new link". Beyond the locked decision, flagged in the prompts file |

### C · Top bar, help and the two popovers (8)

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 11 | Top bar — anatomy at rest | 1069 | `button` (facility switcher trigger), `button` (search), `button`s + `avatar` | 56px. Switcher always shows the facility **name**, never an icon alone, and carries the only facility-accent swatch outside the rail stripe. Unread count is in the bell's accessible name, not just the badge |
| 12 | Help — a contact route, nothing more | 1105 | `tooltip` | Single 24px `circle-help`. Goes **straight** to contact — no menu, no popover, no panel. No help centre, ever (U73). Prompt 7 |
| 13 | User menu — multi-role | 1133 | `dropdown-menu` (or `popover`) + inline segmented control | Identity header is **inert**: no hover, no cursor change, no focus ring. "Switch role" absent from the DOM for single-role accounts — not greyed (U83: scope-denied is Hidden). Appearance is inline, visible without opening. Prompt 4 |
| 14 | User menu — single role, sign-out-everywhere expanded | 1186 | same + in-place confirm block | Confirmation **expands in place inside the popover** — no modal, no separate dialog |
| 15 | Notifications — unread present | 1236 | `popover` + `scroll-area` | 400px, max-h 480. Unread on three channels: 6px dot, weight 600, `aria-label` starting "Unread". **Every operational time carries dock + date.** No per-item buttons at all. Prompt 5 |
| 16 | Notifications — loading | 1305 | `skeleton` | Three rows shaped like real items, never a centred spinner |
| 17 | Notifications — caught up | 1346 | empty state | `circle-check-big`, no CTA — this is a good state (U74) |
| 18 | Notifications — nothing yet | 1378 | empty state | `inbox`. **Distinct from #17** and the distinction is a server-side history check, never `count === 0` |

### D · Search palette (3)

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 19 | Search palette — grouped results | 1418 | `command` inside `dialog` | 640px, ~15% from top. Fixed group order: Shipments · Appointments · Drivers · Carriers · Facilities. Empty groups absent, never an empty header. Highlight = `surface-selected` **plus** a 2px left edge, never background alone. Matches marked by weight 600, not a coloured highlight. Prompt 6 |
| 20 | Search palette — first open | 1460 | same, `RECENT` group | ⚠ the palette input is the one control in the product with no visible label — the mockup flags it (line 1490) as a scoped exception carrying an `aria-label`. **The exception stops at this component** |
| 21 | Search palette — no results | 1498 | empty state | `search-x`, echoes the actual query in quotes, states the scope ("Search covers Jaipur DC only"), one Clear search |

### E · Account settings (3)

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 22 | Settings — the whole page | 1534 | `card` ×5, `switch`, `radio-group`, segmented control | One scrolling route, 720px column, left-aligned. Sections 1 and 5 are **Read-only** in U83's sense: zero interactive affordance — no boxes, no hover, no cursor change. Toggles carry an On/Off text label, never colour alone. Saves immediately; no Save button. Prompt 8 |
| 23 | Settings — "Mute everything" on | 1632 | + disabled `switch` | Category rows dim, toggles disabled, reason stated inline. Section 3 dims with its reason, never silently no-ops |
| 24 | Settings — a preference failed to save | 1687 | inline error row | "That didn't save — nothing has changed. [Try again]" — the "nothing has changed" clause is essential, not padding |

### F · States that replace the whole content region (5)

The shell — rail, top bar, status bar — **never unmounts** (U71). Only this region changes.

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 25 | Out of scope | 1729 | empty state | `shield-off`. Names the facilities the user **does** have; never the one they hit |
| 26 | 404 — resource not found | 1746 | empty state | `map-pin-off`. Deliberately the **same string** whether the record is absent or out of scope — a distinguishing 404 is a record-enumeration tool |
| 27 | Error boundary — scoped | 1762 | empty state | `octagon-alert`. **Per region**, never whole-app: queue, dock board and co-pilot each get their own. Report attaches region + trace id, never a stack trace |
| 28 | Maintenance | 1783 | empty state | `wrench`. Always states a duration. **No retry button** — retrying doesn't shorten a migration |
| 29 | Idle warning | 1799 | `dialog` | Warn at 55 min, sign out at 60. Initial focus on **"Stay signed in"** — never the countdown, never the destructive option. Drivers never see this. ⚠ copy is placeholder — mockup's own flag, line 1815 |

### G · The rest of the shell (3) — added 2026-08-26

These three closed §4.1.1. All values were already decided; the only thing derived was the destination list.

| # | Artboard | Line | shadcn primitives | Notes |
|---|---|---:|---|---|
| 30 | Icon rail — at rest, and expanded as an overlay | 1920 | `sidebar` (Radix-backed) + `tooltip` | Three rails in one plate: planner (1 destination, violet stripe), carrier (3 destinations, hover + tooltip, **no stripe**), carrier expanded (240px, tier-3, overlaying content that has **not** moved). Active item = 2px inner accent bar, never a fill. Maps to shadcn's `--sidebar-*` set (§2.1) |
| 31 | Status bar — connected, and offline | 2009 | none — plain flex row | 28px, five fields in fixed order. Connection state is icon **+** text, never a dot. Offline is the only state taking danger colour, and it takes it on icon and word. Counts and versions in `--font-data` |
| 32 | Facility switcher — open | 2053 | `popover` + `command` (search-filterable listbox) | The swatch here and the rail stripe are the only two places facility accent may appear. "All facilities" carries a **dashed outline, not a hue** — it is not a facility. Changing facility **clears row focus and pending selection**. Absent from the DOM entirely for carrier (U83) |

**Lucide icons the shell needs** (extracted from the mockup's inline `<symbol>` set — **26**):
`eye`, `eye-off`, `circle-alert`, `info`, `link-2-off`, `bell`, `circle-help`, `search`, `search-x`,
`clock`, `inbox`, `circle-check-big`, `check`, `chevron-down`, `chevron-right`, `shield-off`,
`map-pin-off`, `octagon-alert`, `wrench`, and — added with section G — `wifi`, `wifi-off`, `flag`,
`chart-gantt`, `warehouse`, `package`, `sliders-horizontal`. All 2px stroke, sizes 14/16/20/24/32. Import
per-icon from `lucide-react`; never the barrel.

`chart-line` was dropped when Carrier collapsed to one destination — the on-time figure is a stat tile on
the Fleet dashboard, not a rail item. Removed from the sprite rather than left as an orphan symbol.

⚠️ **Verify `chart-gantt` against the pinned `lucide-react` version** — it was renamed in Lucide's `chart-*`
sweep (from `gantt-chart`). Same glyph, different export name.

---

## 4 · Readiness call

**Verdict, final 2026-08-26: build-ready. Nothing outstanding, no open forks, no unresolved questions.**
Both hard blockers closed, all six §4.3 decisions locked into the foundations files, the eleven token-tier
defects fixed at source, and **both forks resolved by the owner** — Tailwind **v4** (the v3 artifact deleted,
not parked) and theme persistence **client-only `localStorage`** (§4.5, with the false cross-device copy
corrected in both places that rendered it).

Three further defects were found *after* the artboards were drafted, none of which a markdown spec could
have caught:

- **Two rendering defects** in artboard 30, diagnosed by measuring the rendered box model rather than
  reading the markup — the rail tooltip painted under the content, and the active marker painted over the
  facility stripe (§4.7).
- **One derivation error**: the carrier rail's three destinations contradicted a locked surface design.
  Found by the owner questioning why Admin (4 areas → 1 destination) and Carrier (3 jobs → 3 destinations)
  were treated differently. **They shouldn't have been**, and the missing rail-vs-tabs criterion — the
  absence that allowed it — is now stated in `components.md` §7 (§4.1.2).

All three are re-verified in a real render, not by inspection.

**The U38 `web-design-guidelines` gate has now been run on section G** (§4.8) — seven findings, six fixed,
one reported with a stated reason for not fixing it. One of them closed a genuine spec gap: the status bar
had no row in U82's announcement politeness matrix, and the matrix's default would have silently swallowed
a connection drop.

What changed, and where — every item verified in the file, not from intent:

| Was | Now | Landed in |
|---|---|---|
| Rail and status bar had prose specs and no rendering | **3 artboards drafted** → 32 total | `mockup-shared-shell.html` §G, artboards 30–32 |
| Rail destinations undefined | **Derived per role** from §2 × §7.5.* | `iconography.md` §Rail destinations; cross-refs in `spacing-and-layout.md` + `components.md` §7 |
| 9 dark tokens written as `"@ N%"`, irreproducible | **Opaque hex, contrast-verified** | `color.md` (3 state + 4 feedback + 2 selected) |
| Mockup auto-switched to dark on OS preference | **Both `@media` blocks removed**; JS defaults to light | `mockup-shared-shell.html` |
| Badge white-on-`blue-500` at 3.7:1 in dark | **`interactive-on` → 5.5:1** | `color.md` + mockup `.badge` |
| Toggle off-track hardcoded, unreachable by theme | **`switch-track-off`, both themes** | `color.md` + mockup `.sw2` |
| 11 components reaching base primitives | **All 11 via functional tokens** | mockup CSS; 8 new tokens in `color.md` |
| 6 open decisions | **All 6 locked** | see §4.3 |
| `auth-and-scoping.md` had no gate-officer landing row | **`GATE_OFFICER` added** | `auth-and-scoping.md` |
| Tailwind version undecided | **v4 locked; v3 artifact deleted, not parked** | this file, §Tailwind version |
| Theme copy promised cross-device sync it would not deliver | **"This is saved on this device."** | `stitch-prompts-shared-shell.md` prompt 8 + mockup settings artboard |
| Rail tooltip painted *under* the content; active marker painted *over* the facility stripe | **Both fixed, re-measured in a real render** | mockup `.rail` / `.railtip` / `.railexp` / `.railitem.active::before`; rules recorded in `components.md` §7 |
| Carrier had 3 rail destinations, contradicting its own locked surface design | **Collapsed to 1 (Fleet), and the missing rail-vs-tabs criterion added** | `components.md` §7, `iconography.md`, artboard 30, §4.1.2 |

### 4.1 Blockers — both closed 2026-08-26

Kept rather than deleted, because *how* each was closed is the part a reviewer needs, and because the
reasoning is what stops the same gap reopening.

**4.1.1 — Rail, status bar and facility switcher had no rendered reference. CLOSED.**
E5.0's deliverable *is* the shared shell, and of the shell's three persistent regions only the top bar had
been drawn — the two that are on screen 100% of the time for five of six roles had not, and neither had the
facility switcher's open state. `mockup-shared-shell.html` said so outright: *"The icon rail and status bar
are out of frame here."* Prose plus a token table is enough to build a *plausible* rail; it is not enough to
build *the* rail, and U101 exists because rail destinations are where this project already guessed wrong
once and was caught only by looking at a rendering.

**Closed by section G — artboards 30, 31, 32** (§3). Every value came from `spacing-and-layout.md` and
`components.md` §7; nothing was invented except the destination list, which was derived (4.1.2). Three
things the rendering surfaced that the prose had not:

- **The carrier rail has no facility stripe and no facility switcher.** Carriers are scoped by `carrier_id`,
  not by facility (§7.5.6), so there is no facility to colour. Now stated in `components.md` §7.
- **"All facilities" needs a non-hue affordance.** The cross-facility ops roles need that row, but it is not
  a facility and must not borrow a facility's swatch — it renders as a dashed outline.
- **Two of the status bar's five fields cannot apply universally** — see §4.6.

**4.1.2 — Rail destinations per role. CLOSED — derived, not invented.**
Derived from `SOLUTION_DESIGN.md` §2's persona table cross-checked job-by-job against each role's own
§7.5.* catalog, per U101. **A job with no tool does not get a destination.** Now enumerated in
`iconography.md` §Rail destinations, with cross-references from `spacing-and-layout.md` and
`components.md` §7.

**The criterion, added to `components.md` §7 on 2026-08-26 because it was missing and its absence caused a
real error:** *a rail destination is a **surface**, and this product has one surface per role.* Tabs,
sections and segmented controls are all internal navigation and never rail items.

| Role | Rail destination | Icon | Grounded in |
|---|---|---|---|
| **Driver** | **None — no rail at all** | — | PWA at 320–768px; a 56px rail expanding to a 240px overlay is not viable on a 390px phone. Prompt 8 scopes the shell to "the five internal roles" |
| **Ops** (`OPERATIONS_EXECUTIVE`, `OPERATIONS_MANAGER`) | Exceptions | `flag` | §2 "triage exceptions, resolve ambiguity, escalate"; §7.5.5's 8 tools |
| **Planner** (`WAREHOUSE_PLANNER`) | Dock Command | `chart-gantt` | §2 "confirm/reject, block docks, re-sequence"; §7.5.1's 8 tools + §7.5.3. Queue and Board are **tabs** |
| **Gate** (`GATE_OFFICER`) | Yard | `warehouse` | §2 "gate-in, yard queue, call-to-dock…"; §7.5.2's 5 tools. Two device contexts on a **segmented control** (`components.md` §12) |
| **Carrier** (`TRANSPORT_MANAGER`) | Fleet | `package` | §2's three jobs + §7.5.6's 5 tools, all landing on **one sectioned dashboard** — `05-carrier-portal/screens.md`: *"one sectioned dashboard," "no tabs"* |
| **Admin** (`ADMIN`) | Admin | `sliders-horizontal` | §2 + §7.5.7's 12 tools. Users, Rules, Policy and Audit are **four tabs** |

**Settings is not a rail destination** — it is reached from the user menu (prompt 4), which also keeps
`settings` from colliding with `sliders-horizontal`'s admin meaning.

**Corrected 2026-08-26 — Carrier was wrong, and the mechanism is worth recording.** It first had three
destinations (Shipments · Exceptions · Performance), derived by counting §2's jobs and §7.5.6's tools. That
contradicted a *locked surface design*: `05-carrier-portal/screens.md` had already specified one sectioned
dashboard with no tabs, where shipments and exceptions are page sections and on-time performance is a stat
tile. The root cause was **two derivation methods used without noticing**: planner and admin were derived
from their surfaces' known tab structure, carrier from a job count, because its `screens.md` was outside
this pass's declared scope. The lesson is now a rule in `components.md` §7 — **a job in §2 is not a
destination and neither is a tool in §7.5.\***, and *the surface's own `screens.md` is authoritative for
navigation shape*. If it hasn't been written, that is a gap to raise, not something to infer.

**All five internal roles therefore have a single-destination rail — owner-confirmed 2026-08-26, closed.**
The rail earns its 56px by carrying the facility accent stripe (U40), the active/scope indicator, and
headroom for §2's two deferred personas (facility manager, regional ops head), which are genuine future
destinations. Do not reopen this as an oversight, and do not add a second icon to make the rail look
busier — that is precisely what U101 forbids.

**4.1.3 — Nine dark tokens written as `"@ N%"`. CLOSED — the notation was the error.**
`color.md` specified dark `state-held-bg` as `amber-900 @ 25%` and eight more like it; the mockup shipped
flat hexes. **The two did not derive from each other**: `amber-900 #78350F` at 25% over `neutral-900`
composites to `#291E23`, while the mockup used `#3A2C10` — visibly warmer, and the computed version is a
chip that barely reads as amber.

**Judgment: the mockup's hexes are intended and the tokens are opaque; the `"@ N%"` notation was shorthand
that never survived contact with a rendering.** Two reasons, and the second is the decisive one:

1. The rendered value was reviewed; the notation never was. And U14 needs that background to *work* as one
   of four redundant channels — a desaturated near-neutral does not.
2. **Opaque is the better engineering answer independent of which value wins.** A promise-state chip renders
   on cards, table rows, dock-board bars and inside popovers. A translucent token is a different colour on
   each of those four backdrops; an opaque one is identical everywhere. For the one component in this
   product that must never be misread, identical everywhere is a requirement, not a preference.

All four dark chip pairings were contrast-verified as part of the correction (8.1:1 / 6.3:1 / 7.5:1 /
5.9:1 — all pass) and the numbers are recorded in `color.md` beside the values.

**4.1.4 — The mockup auto-switched to dark on OS preference. CLOSED — it contradicted U69.**
The mockup carried `@media (prefers-color-scheme: dark)` *and* a `data-theme` override, so a planner on a
dark-configured Windows laptop got dark by default — precisely the "two internal screens disagree by
accident" outcome `color.md` records U69 as having rejected. **Both media blocks are removed**, the JS
resolver now returns `'light'` rather than falling back to `matchMedia`, and the `theme-color` meta pair
collapsed to one value (a `prefers-color-scheme`-keyed pair would have tinted the browser chrome dark while
the page rendered light).

**Implementation:** class-based dark only — `@custom-variant dark (&:where(.dark, .dark *))`. Light is the
shipped default for every role. `prefers-color-scheme` is consulted **only** when the user has explicitly
chosen "System" in the Appearance control — an explicit choice, never a default. Where that preference is
stored is now settled: **`localStorage`, client-only** (§4.5).

### 4.2 Eleven token-tier defects in the mockup, two of them live bugs (U85)

Found by grepping the mockup's component CSS for primitive references. `tokens.md` exists to prevent exactly
this, and the mockup predates a mechanical check — so these are the list of functional tokens that are
**missing**, discovered the way U85 predicted they would be.

| Line | Component | Reaches for | Should be | Severity |
|---:|---|---|---|---|
| 323 | `.inp:hover` | `--neutral-400` | `border-strong` — **already exists**, just wasn't used | Cosmetic |
| 391 | `.dot` (unmet requirement) | `--neutral-400` | No token fits. Needs one (`marker-unmet`) | Needs a token |
| 429 | `.badge` text | `--neutral-0` | `interactive-on` / `--color-primary-foreground` | **Live dark-mode bug** |
| 434 | `.avatar` text | `--neutral-0` | `avatar-fg` component token | Same class as above |
| 441, 444, 445 | `.tip` (tooltip) | `--neutral-900` / `--neutral-50` / `--neutral-200` | **No `surface-inverse` token exists.** `text-inverse` does; its surface counterpart doesn't | Needs a token |
| 590, 595, 601 | `.sw2` (toggle) | `--neutral-300`, `--neutral-0`, `--neutral-100` | No switch track/knob tokens exist | **Live dark-mode bug** |

The two live bugs are worth stating precisely, because they are the argument for §1.0 in one paragraph:

- **`.badge`** hardcodes white text. In dark mode `--interactive-default` becomes `blue-500 #3B82F6`, and
  white on `blue-500` is ~3.7:1 — below AA for 10px badge text. Had it used `interactive-on` it would have
  correctly flipped to `neutral-950`.
- **`.sw2`** hardcodes `neutral-300` for the off-track and is never redefined for dark, so in dark mode the
  toggle's off state is a **light grey pill on a near-black card** — inverted. And because it reached a
  primitive, no theme override *can* reach it. Stitch prompt 8 states the intended dark off-state is
  `#334155` (`neutral-700`), so the mockup also contradicts its own prompt here.

**This is not a criticism of the mockup — it is the mockup doing its job.**

**CLOSED 2026-08-26. All eleven reaches now go through a functional token, and eight tokens were added to
`color.md`** — the four identified plus four more the same audit turned up:

| Token | Light | Dark | Fixes |
|---|---|---|---|
| `interactive-on` | `neutral-0` | `neutral-950` | `.badge` — **the 3.7:1 bug**. Existed only as prose in `components.md` §1's variant table, so components had nothing to reference |
| `destructive-on` | `neutral-0` | `neutral-950` | Same idea for the `destructive` variant's red fill |
| `switch-track-off` | `neutral-300` | `neutral-700` | `.sw2` — **the inverted-toggle bug** |
| `switch-knob` | `neutral-0` | `neutral-50` | `.sw2` knob |
| `surface-inverse` / `-fg` | `neutral-900` / `neutral-50` | `neutral-200` / `neutral-900` | `.tip` tooltip ground |
| `marker-unmet` | `neutral-500` | `neutral-400` | `.dot`, the unmet-requirement marker |
| `avatar-bg` / `avatar-fg` | `neutral-600` / `neutral-0` | `neutral-400` / `neutral-950` | `.avatar` |
| `surface-floating`, `border-floating` | `neutral-0` / `neutral-200` | `neutral-800` / `neutral-700` | Elevation tier 3 — specified in `elevation-and-depth.md`, never named in `color.md` |
| `skeleton`, `scrim`, `urgent` | see `color.md` | — | Used correctly by the mockup, undocumented in `color.md` |

`.inp:hover` now uses `border-strong`, which existed all along — and that also silently fixed a dark-mode
issue, since the hardcoded `neutral-400` was too bright on a dark ground where `border-strong` resolves to
`neutral-600`.

Two deliberate non-additions, for the record: the **disabled knob** reuses `interactive-disabled-text`
rather than getting a fifth switch token (low contrast against `interactive-disabled-bg` *is* the correct
disabled appearance), and the **avatar** got its own pair rather than reusing `surface-inverse`, because
reusing it would have turned a mid-grey circle near-black — this pass was correcting tier violations, not
changing rendered colours.

### 4.3 Six decisions — all locked 2026-08-26, all written into the foundations

Each had a recommendation in the previous revision; each is now a decision in the file that owns it. None
turned out to be a genuine fork. (The one thing that *did* turn out to be a fork is §4.5, and it surfaced
from reading §7.5.8, not from this list.)

| # | Decision | Locked in |
|---|---|---|
| 1 | `typography.md`'s `text-sm` (13px) registers as the **`text-supporting`** utility; Tailwind's `text-sm` stays 14px, untouched | `typography.md` |
| 2 | Auth + full-page states get their own density row: **`comfortable` with 44px controls** | `spacing-and-layout.md` |
| 3 | Skeleton is **`animate-shim`, 1600ms `ease-in-out`** — `motion.md` wins over U78's `animate-pulse` | `components.md` §13 |
| 4 | Segmented control: **4px padding** (not the off-grid 2px) and hover is a **`text-primary` colour change** (not an invisible fill) | `components.md` §12 |
| 5 | Dark `surface-sunken` stays `neutral-950`; **sunken surfaces carry a 1px `border-subtle` in both themes** | `color.md` |
| 6 | `--chart-1..5` stay **unset and commented `UNSOURCED`** | this file, §2.1 |

**4.3.1 — `text-sm` collision. LOCKED: register as `text-supporting`.**
Ours is 13px, Tailwind's built-in is 14px. Renaming the *design token* was rejected (U85's own "existing
token names are not retroactively renamed", and six surface folders reference the scale). Overriding
`--text-sm` in place was also rejected: it would silently shrink every shadcn primitive by a pixel and leave
every developer's muscle memory pointing at the wrong size. Registering the 13px value under a
non-colliding utility name solves both — and Tailwind's `text-sm` at 14px happens to coincide with
`text-body`, so shadcn primitives land on the right size unpatched.

The obvious symmetry with §1.0's `--color-*: initial` trick **does not transfer**: clearing the type
namespace would make `text-xs`/`text-base`/`text-lg` unknown utilities and break every shadcn primitive at
install time. Stated because it is the first thing a reader will propose.

**4.3.2 — Density for the pre-shell screens. LOCKED: a stated `auth` row, `comfortable` with 44px controls.**
`spacing-and-layout.md`'s table maps densities to *operational surfaces*; sign-in, the role picker, both
reset screens and the five full-page states belong to none of them, which is why the mockup had drifted to
44px buttons against `comfortable`'s 40px with no row to justify it. The override is deliberate and narrow:
these screens are the **driver's** door as well as a desk user's, so the field 44×44 bar applies to the door
even though it does not apply to the planner console behind it. Tagged `Source: assumption, untested` in
`spacing-and-layout.md` so a later review can challenge the number without reverse-engineering it.

**4.3.3 — Skeleton timing. LOCKED: `animate-shim`, 1600ms `ease-in-out`.**
`components.md` §13 (U78) named Tailwind's `animate-pulse`; `motion.md`'s inventory says 1600ms
`ease-in-out`. Tailwind's built-in is **2000ms** on `cubic-bezier(0.4,0,0.6,1)`. `motion.md` is the motion
authority, so it wins, and U78's text is amended. Register the custom keyframe; do not reach for the
built-in because its class name is shorter.

**4.3.4 — Segmented control: two contradictions, both LOCKED.**
(a) The container's inset is **4px, not 2px**. 2px is not a multiple of the 4px base unit, which
`spacing-and-layout.md`'s opening line forbids without exception — so the original §12 text was violating a
different foundation file. 4px padding with `radius-sm` segments inside a `radius-md` container achieves the
same non-colliding corners on the grid.
(b) Unselected hover is a **`text-primary` colour change, not a `surface-hover` fill.** The fill was
literally unimplementable: the container is `surface-sunken`, and `surface-sunken` and `surface-hover` are
**the same value in light mode** (`neutral-100`), so the specified hover was invisible. Minting a surface
token for one component was the alternative and was rejected. The mockup had already substituted the colour
change silently; it is now the spec.

**4.3.5 — `surface-sunken` in dark. LOCKED: keep `neutral-950`, carry a border.**
Dark `surface-sunken` equals dark `surface-base` (`neutral-950`), so via §2.1 shadcn's `--muted` equals
`--background` and every muted surface flattens in dark. Not fixable by picking a darker step — 950 is the
floor.

Shifting the dark stack (base 950 → sunken 900 → raised 800) was the alternative and **was rejected as
disproportionate**: it changes three surface tokens across every dark screen on six surfaces to fix a
problem that `elevation-and-depth.md` already has an idiom for. That file's dark Level 1 uses **no shadow at
all** and separates by "the lightness step plus a subtle border." Sunken is the same situation inverted:
where there is no step available, **the border carries it**. So sunken surfaces carry a 1px `border-subtle`
unconditionally in both themes — which is why the segmented control already reads correctly in dark despite
its fill matching the page. A `bg-muted` region with no border is now a component bug, not a token gap.

Related, lower stakes and left alone: dark `surface-hover` and `surface-overlay` are both `neutral-800`, so
a hovered row is the same colour as a modal. Different contexts, no confusion in practice — recorded rather
than fixed.

**4.3.6 — `--chart-1..5`. LOCKED: unset, commented `UNSOURCED`.**
U66 defers the sparkline's form and colour to the `dataviz` skill, which has not been run for this product.
Accepting shadcn's defaults would put five unaudited hues into a system whose entire colour argument is a
rationed hue budget — the exact opposite of `color.md`'s opening section. The stat tile (§14) is fully
specified and buildable without them; the five variables get values when the sparkline slot is specified,
with `dataviz` actually invoked at that point.

### 4.4 Named-but-unread files — now read, and what they changed

The previous revision flagged three files as load-bearing but out of scope. **All three were read on
2026-08-26, and two of them changed the answer:**

- **`SOLUTION_DESIGN.md` §2 + §7.5.\*** — the source for §4.1.2's destination table. §7.5.8 (shared
  cross-cutting tools, added 2026-08-22) turned out to back all seven shell screens, and it is also where
  §4.5's fork came from.
- **`iconography.md`** — had **no navigation domain at all**, despite its own sizing table saying `icon-lg`
  is for "Top bar, rail, section headers." A §Rail destinations section was added. It also resolved a
  question the mockup could not: `inbox` and `circle-check-big` are bound to the two empty-state meanings,
  so neither was available for an ops-queue destination icon — which is how `flag` was chosen.
- **`auth-and-scoping.md`** — its Role landing table **had no `GATE_OFFICER` row**, despite §2 marking the
  role ✅ for v1, §7.5.2 giving it five tools, and this same file's "What each role never sees" table
  already having a Gate officer row. Added, grounded in §2's "yard queue" + §7.5.2's `update_queue_state`.
  One structural note that follows: the table has **seven** role identifiers for **six** personas
  (`OPERATIONS_EXECUTIVE` and `OPERATIONS_MANAGER` share the ops console, differing only in whether
  escalations are pinned) — they get identical rail destinations.

Two files remain unread and are still needed, but by later epics rather than E5.0:

- **`data-formatting.md`** — mid-truncated IDs, the zero/unknown/scope-hidden distinction, the dock+date
  time pattern. Every identifier and timestamp in artboards 15, 19, 22 and 31 goes through it.
- **`voice-and-tone.md`** — the state templates and negative-path copy.

### 4.5 Theme persistence — **LOCKED: client-only `localStorage`** (owner decision, 2026-08-26)

Found while reading §7.5.8: two authoritative documents contradicted each other on user-visible copy.

| Source | Said |
|---|---|
| `SOLUTION_DESIGN.md` §7.5.8 | *"**Not a tool, by design**: the appearance/theme toggle. It is a client-only preference (localStorage or equivalent) with no server state and no `user_id` binding requirement — inventing an endpoint for it would be exactly the kind of scope creep `TECH_STACK.md`'s '5-person internal tool' calibration exists to catch."* |
| `stitch-prompts-shared-shell.md` prompt 8 | *"This is saved to your account and **follows you between devices**."* |

**Resolved: §7.5.8 stands unchanged, and the copy was wrong.** Both places that rendered the promise are
fixed to **"This is saved on this device."** — `stitch-prompts-shared-shell.md` prompt 8 (Section 4) and
`mockup-shared-shell.html`'s settings artboard, which had the same string.

This mattered more than its size suggests: it was **user-visible copy making a false promise about
behaviour**, which this project treats as a correctness issue rather than a detail. A user who reads
"follows you between devices," sets dark on their laptop, then opens the kiosk to a light theme has been
told something untrue by the interface.

**Implementation consequences:**

- Theme is read from `localStorage` on boot and written on change. **No tool, no endpoint, no `user_id`
  binding** — do not add one to `update_notification_preferences` "while you're in there."
- `"System"` resolves via `matchMedia` **at read time**, and should also listen for changes so a mid-session
  OS switch is honoured. Only this explicit choice consults `prefers-color-scheme` (§4.1.4).
- Theme is now the **only** preference in the product that is not durable server state — notification
  preferences are Postgres-backed per §7.5.8. Worth a comment at the read site, since the asymmetry
  otherwise looks like an oversight to the next person.
- **Boot order matters**: read and apply the class before first paint, or every dark-theme user gets a
  white flash on every load. An inline script in `index.html` ahead of the bundle, not a React effect.

### 4.8 `web-design-guidelines` audit of section G (U38 gate, run 2026-08-26)

Skill actually invoked, guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md),
applied to artboards 30–32. **Seven findings; six fixed, one reported and deliberately not fixed.** Two were
substantive enough to change a foundations file, not just markup.

| # | Finding | Resolution |
|---|---|---|
| 1 | Three `<nav aria-label="Main">` on one page — duplicate landmark names, so a screen-reader user gets three identically-named navigation landmarks | Distinct labels: `Main — planner`, `Main — carrier`, `Main — carrier, expanded` |
| 2 | `role="tooltip"` on the rail tooltip referenced by nothing — an orphan role no AT can associate | `id="tip-fleet"` + `aria-describedby`, matching artboard 12's existing precedent |
| 3 | **`role="listbox"` containing a search `<input>` and two `<hr>`s** — invalid content model; a listbox may only contain `option`/`group` | Listbox moved to an inner `#fac-list` wrapping only the options; input promoted to `role="combobox"` with `aria-controls`; rules `aria-hidden` |
| 4 | **The status bar is a live region with no announcement strategy** — and no row in U82's politeness matrix | `role="status"` on the connection field only; **matrix row added to `accessibility-behaviour.md`** — see below |
| 5 | `.sbi` flex children lacked `min-width:0`; the status bar had no overflow strategy, so a long facility name would push the policy version out | `min-width:0` + a `.sbfac` truncation class — the facility name is the only variable-length field, so it is the one that truncates |
| 6 | `.fpop` is a scrollable popover without `overscroll-behavior: contain` | Added |
| 7 | Placeholder `"Filter facilities"` doesn't end with `…` per the guideline | **Reported, not fixed** — see below |

**Finding 4 is the one that mattered.** U82 requires every live-updating region to have a matrix entry, and
the status bar had none. Worse, the matrix's *general rule* routes ambient state **to** the status bar as the
silent alternative to a push — which would have **silently swallowed a driver's or planner's connection
dropping.** That is not ambient: a planner who goes offline and keeps confirming is acting on stale capacity
data, which is the exact failure `auth-and-scoping.md`'s degradation policy exists to prevent. Two rows added:
connection state → `polite` on transition; last sync / pending count / facility / policy version → **silent**,
because they tick continuously and a live region over them would make the bar unusable with a screen reader
(the same reasoning that throttles the countdown to four thresholds).

**Finding 7 was deliberately not fixed.** The guideline is real, but this product has six placeholder strings
and none of them use a trailing ellipsis — the search palette's is `"Search shipments, appointments, drivers,
carriers, facilities"`. Fixing one of six would make the reference board internally inconsistent, which is
worse for an implementer copying from it than a consistent deviation. **Recorded as a product-wide question
for `voice-and-tone.md` to settle once**, not patched here.

Verified in a real render, not by inspection — landmark labels unique, `aria-describedby` resolves, listbox
children are `option,option,option` with no input inside, `aria-controls` resolves, exactly one live region in
the status bar, and a 60-character facility name injected at runtime truncates without overflowing the bar or
pushing the policy field off (`scrollWidth == clientWidth`, policy field still within bounds).

### 4.6 Non-blocking, recorded so they aren't rediscovered

- **Status-bar field presence per role is unspecified.** `spacing-and-layout.md` gives five fields once, for
  all roles, but two cannot apply universally: **carrier has no active facility** (scoped by `carrier_id`,
  §7.5.6) and **policy version** is only meaningful where a decision receipt is rendered (planner, ops,
  admin). Flagged in artboard 31 rather than resolved inside a mockup. Low stakes — it is field visibility,
  not a correctness rule — but it needs an answer before the status bar ships for carrier.
- `--font-data` dropped `'Cascadia Mono'` in the mockup; `typography.md` includes it. **`typography.md` is
  authoritative** (used in §1.4).
- The footnote's "four items are flagged inline" was an off-by-one against three `class="flag"` blocks. Now
  **six flags and the count is corrected** — the three new artboards each carry one (single-destination
  rails, status-bar field presence, two facility names instead of six).
- `color.md`'s own open item — *"every token pair against every surface it can land on, in both themes …
  needs a checker in CI, not a spreadsheet"* — is an **E5.0 deliverable**, not a later nicety. The `.badge`
  bug in §4.2 is exactly what it catches, and it was found by hand. Coloured text on `surface-selected` and
  `surface-hover` is the untested combination the spec itself names.
- **Only two facility names exist in any document in scope** (Jaipur DC, Gurugram Cross-Dock) against §2's
  six facilities. Artboard 32 renders two and says so rather than inventing four, since facility names are
  operational data. The four remaining hues are already fixed in `color.md` and assigned by creation order.

---

### 4.7 Two rendering defects a markdown spec could not have caught

Found by the owner opening `mockup-shared-shell.html` in a browser, then diagnosed by **measuring the
rendered box model** in headless Chromium rather than reading the CSS. Both were in artboard 30. Recorded
because the *method* generalises: neither defect is visible in the markup, and both would have shipped.

**Defect 1 — the rail's hover tooltip was painted underneath the content.**

`.rail` and the content region are sibling boxes, both `position:relative` with `z-index:auto`. The content
comes later in DOM order, so **it paints on top of the rail and everything inside it** — burying the
tooltip. Confirmed with `document.elementFromPoint()` at three points across the tooltip: the topmost
element was `.fakecontent` / `.fakebar`, never `.railtip`.

Compounding it, the tooltip's offset was wrong: `left:48px` on a 40px button that sits 5.5px inside a 56px
rail put the tooltip's left edge **0.5px inside the rail's right border** (measured
`GAP_RAIL_TO_TIP = −0.5px`), so it appeared to grow out of the rail rather than beside it.

Fixed with the design system's own z-scale rather than an ad-hoc number — `.rail` → `z-shell` (200),
`.railtip` → `z-tooltip` (800), `.railexp` → `z-rail-expand` (300) so the expanded overlay is correct by
construction instead of by DOM luck — plus `left:calc(100% + 16px)` and `shadow-md`
(`elevation-and-depth.md` names tooltips at Level 3). Re-measured: gap **+7.5px**, topmost element at all
three points **`railtip`**.

**Defect 2 — the active marker was painted over U40's facility stripe.**

Found while re-viewing the fix, not reported. The 2px active accent bar sat at **1.5–3.5px inside the rail,
entirely within the 0–4px facility stripe** (`COLLIDES_WITH_STRIPE true`). So on every facility-scoped rail
— planner, ops, gate, admin; four of the five internal roles — the active-item marker and the facility
colour were drawn on top of each other and neither read correctly. Moved to 6–8px, a measured 2px clear of
the stripe, and the constraint is now stated in `components.md` §7 so it does not recur.

**The lesson worth keeping:** two 2–4px vertical bars competing for the same edge is a hazard this shell
creates by design (U40's stripe plus an active marker), and it is invisible in every artifact except a
render. The `web-design-guidelines` post-write gate on `mockup.html` (U38) is the standing mechanism for
this class of defect; this instance is the argument for actually running it on the three new artboards
before E5.0 consumes them.

## 5 · Kibo UI Gantt — U52 checked, and it is worse than "unverified"

Checked the published docs and the package source. **U52's flag is confirmed, and there is a third issue
neither U52 nor `TECH_STACK.md` §9 anticipated.**

| Question | Finding |
|---|---|
| Zoom presets? | **No presets.** `zoom?: number`, default `100`, a unitless percentage. Presets would be ours to build on top |
| Virtualisation? | **None.** No `react-window`, no `react-virtual`, no `@tanstack/react-virtual` anywhere in the package. Every column and every bar renders |
| Granularity | `range?: Range`, default `"monthly"`, allowed values **`"daily" \| "monthly" \| "quarterly"`** |
| Intra-day? | **No.** At `range="daily"` **one column is one day**. There is no hourly grid. Item *positioning within* a column uses `differenceInHours`, so a bar can sit at an hour offset — but the header renders day numbers and weekday initials, and the grid ticks are days |
| Drag/resize | Uses `@dnd-kit/core`. **Drag and resize are opt-in** — only active when `onMove` is passed to `GanttFeatureItem`. Omit the callback and the bar renders inert |
| Docs coverage | The published docs mention **neither** zoom nor virtualisation, exactly as U52 recorded |
| Install / licence | MIT; `npx kibo-ui add gantt` (shadcn-registry style), installed as source |

**The finding that actually matters: the granularity mismatch.** A dock board is an intra-day instrument —
6–12 dock lanes across roughly 06:00–22:00, with intervals of 30–90 minutes and `LAST_NEW_START_TIME`
mattering to the quarter-hour. Kibo's finest grid is one column per day. To get a usable board you would
set `range="daily"` and push `zoom` very high (order of 1000+) to stretch a single day-column wide enough
to place hour-offset bars inside it — while the header still labels **days, not hours**. That is a
header-and-grid rewrite, not configuration. And with no virtualisation, a wide zoom across a multi-day
horizon renders every column in the DOM.

**One piece of good news, and it is not small:** because drag/resize is opt-in via `onMove`, **U25 ("no free
dragging") is satisfied by simply not passing the callback.** Kibo's headline feature is exactly what our
design forbids, and it is off by default. The `GanttFeatureDragHelper` / `GanttAddFeatureHelper` exports
should be left uninstalled, not merely unused — and U103's click-to-pick counter-offer and U107's
block-dock form are unaffected either way.

**Read this as information, not a blocker** — as instructed. But it is worth an honest sentence to whoever
picks up E5.3: adopting Kibo Gantt means owning a custom time-axis header, a zoom-preset layer, and a
virtualisation strategy on top of a library that supplies none of the three, in exchange for its lane/bar
layout, markers and grouping. Whether that is a better trade than a purpose-built lane renderer over
`@tanstack/react-virtual` is a real question for E5.3's planning, and it should be asked **then**, with the
dock board's actual requirements in hand — not settled here. U52 stays open; it is now open with specifics.

Sources: [kibo-ui.com/components/gantt](https://www.kibo-ui.com/components/gantt) ·
[haydenbleasel/kibo](https://github.com/haydenbleasel/kibo)

---

## 6 · Suggested order for E5.0

1. `@/*` alias in `vite.config.ts` **and** `tsconfig.app.json`. Nothing else works first.
2. ~~Resolve the Tailwind fork.~~ **Done — v4.** Nothing gates §1 any more.
3. Install Tailwind **v4** + `@tailwindcss/vite`; write `primitives.css` (§1.1) and `theme.css` (§1.2–1.9),
   including the eight tokens added in §4.2. Delete `src/index.css`'s Hanken Grotesk import and retire
   `src/App.css`.
4. `shadcn init` with §2.4's `components.json`; verify the CLI did not overwrite `theme.css`'s colour block.
5. Re-author `button.tsx` with U12's five intent variants (§2.3) — before any surface consumes it.
6. `CountdownProvider` (one 1 Hz interval, server-authoritative `expires_at` with a measured clock offset).
7. Shell, in artboard order: top bar (11) → rail (30) → status bar (31) → facility switcher (32). The rail
   needs §4.1.2's destination table wired to the role claim, and **absent** — not hidden — for out-of-scope
   destinations (U29/U83).
8. Patch every Radix overlay's `z-50` to §1.9's scale; add the modal-open + undo-toast reachability test.
9. Contrast checker in CI (§4.6) — every token pair, both themes, including `surface-selected` and
   `surface-hover` backdrops. This is the gate that would have caught §4.2's badge bug.
10. `forced-colors` fallback (§1.7) and the **per-motion** reduced-motion behaviour (§1.8) — not the
    mockup's blanket `*{transition-duration:0}`, which would delete an expiry warning.
11. Theme boot: an **inline script in `index.html` ahead of the bundle** that reads `localStorage` and
    applies `.dark` before first paint (§4.5). A React effect is too late and gives every dark-theme user a
    white flash on every load.

Artboards 1–10 and 25–29 are buildable in parallel with step 7; they render inside no shell. Note artboards
1–10 and 25–29 run the new `auth` density (§1.6), not `comfortable`.

---

## 7 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No — and one violation was found and removed.** The mockup's `prefers-color-scheme` auto-dark contradicted U69; it is gone (§4.1.4). U85, U69, U12, U14, U25, U40, U41, U52, U59, U74, U79, U83, U101 are each cited where they constrain a value |
| Amends a foundations file? | **Yes, seven — all corrections or gaps, none a redesign.** `color.md` (9 notation fixes + 8 tokens + sunken rule), `iconography.md` (§Rail destinations — a domain it never had), `spacing-and-layout.md` (auth density row + rail cross-ref), `components.md` (§7 rail, §12 ×2, §13 U78), `typography.md` (`text-supporting`), `auth-and-scoping.md` (`GATE_OFFICER` row), `mockup-shared-shell.html` (3 artboards, 11 tier fixes, U69 violation). Each edit states its date and reason inline |
| Invents product behaviour? | **No.** Rail destinations are derived job-by-job from §2 × §7.5.*, and the single-destination consequence is flagged rather than padded out with invented icons (U101) |
| Invents data? | **No.** Artboard 32 renders the two facility names that exist in the documents and flags the other four as unknown rather than making them up |
| React 19 frontend (ADR 012)? | Yes — current `package.json` confirmed React 19.2 |
| Stays inside the named scope? | Yes, plus the four files the coordinator explicitly opened (`SOLUTION_DESIGN.md` §2/§7.5.*, `iconography.md`, `auth-and-scoping.md`). `data-formatting.md` and `voice-and-tone.md` still unread and named as such in §4.4 |
| Skills? | **`web-design-guidelines` was actually invoked via the `Skill` tool** on section G (§4.8), guidelines fetched fresh from source — not cited from memory. `checklist-design` was not run: artboards 30–32 render already-decided values of already-audited components rather than new screens. `dataviz` remains the gate on §4.3.6's chart tokens when the sparkline is specified |
| Genuine forks surfaced, not silently decided? | **Yes, two — both raised, both now resolved by the owner.** Tailwind → **v4** (v3 artifact deleted). Theme persistence → **client-only `localStorage`**, §7.5.8 upheld and the false "follows you between devices" copy corrected in both places that rendered it. Nothing is left open |
| Rendering verified, not eyeballed? | **Yes.** Artboard 30's two defects were diagnosed and re-verified by measuring the rendered box model in headless Chromium (`getBoundingClientRect`, `elementFromPoint`, computed pseudo-element offsets), then re-viewed as a screenshot. §4.7 |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/` |
| Empirical numbers tagged? | Yes. `--radius: 0.5rem` → 4/6/8/12 is *computed*; the four dark-chip contrast ratios are *computed*; Kibo's `range`/`zoom` are *source-verified*; §4.3.2's 44px is `Source: assumption, untested` |
