# Typography

> Structure follows Checklist Design's *Typography* checklist. Decisions follow `../README.md` U9, U30, U31.

## Typefaces

| Role | Family | Why |
|---|---|---|
| **UI** | **Inter** | Exceptional legibility at 12–14px, which is where a dense queue lives. Large weight range, genuine tabular figures, open licence, and a tall x-height that survives glare on a driver's phone. |
| **Data** | **JetBrains Mono** | Shipment/appointment IDs, timestamps, countdowns and dock codes. Machine-generated values should *look* machine-generated. |

Fallback stacks:

```css
--font-ui:   'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-data: 'JetBrains Mono', 'SF Mono', 'Cascadia Mono', Consolas, monospace;
```

**Load Inter 400/500/600/700 and JetBrains Mono 400/500 only.** Subset to Latin. A driver on a cheap
Android over a poor connection pays for every weight, and the design uses no others.

---

## When mono is mandatory, not decorative

This is a rule, not a preference. Use `--font-data` for:

- **Identifiers** — `SHP1015`, `APT-1042`, `DOCK-JAI-D4`, `REC-8f3a`
- **Timestamps and ranges** — `13:00–14:15`, `2026-08-13T18:30`
- **Countdowns** — `01:27`, `00:09`
- **Numeric measures in tables** — weights, durations, queue positions
- **Policy values in the admin console** — weights, thresholds

Everything else is `--font-ui`.

The reason is not aesthetic. Mono gives **fixed advance width**, so a countdown ticking `01:00 → 00:59`
does not shift the layout, and a column of IDs aligns character-for-character when a planner scans it
vertically. Both matter operationally.

### Tabular numerals everywhere numbers align

Even in `--font-ui`, any number that appears in a column or updates live must use tabular figures:

```css
font-variant-numeric: tabular-nums;
```

Apply to: all table cells containing numbers, all countdowns, queue positions, all metric displays.
Proportional figures are correct only in running prose.

---

## Type scale

A 1.2 modular scale, rounded to whole pixels and snapped to the 4px baseline
(`spacing-and-layout.md`). Line heights are unitless.

| Token | Size | Line height | Weight | Tracking | Used for |
|---|---:|---:|---:|---:|---|
| `text-display` | 32px | 1.25 | 700 | −0.02em | Rare. Empty-state headlines, login. |
| `text-h1` | 24px | 1.33 | 600 | −0.01em | Page title |
| `text-h2` | 20px | 1.4 | 600 | −0.01em | Section heading, modal title |
| `text-h3` | 16px | 1.5 | 600 | 0 | Card title, group header |
| `text-body` | 14px | 1.5 | 400 | 0 | **Default.** All UI text, table cells. |
| `text-body-lg` | 16px | 1.5 | 400 | 0 | Driver chat messages only |
| `text-sm` | 13px | 1.4 | 400 | 0 | Secondary/supporting text |
| `text-label` | 12px | 1.33 | 600 | 0.04em | Uppercase column headers, chip labels |
| `text-micro` | 11px | 1.3 | 500 | 0.02em | Timestamps, metadata. **Floor — nothing smaller.** |

### `text-sm` renders as the `text-supporting` utility (added 2026-08-26)

A naming collision, resolved without renaming the design token. **Tailwind ships a built-in `text-sm` at
14px**; ours is 13px. Overriding the built-in in place would leave every developer's muscle memory pointing
at the wrong size forever, and would silently shrink every shadcn/ui primitive (which use `text-sm`
liberally) by a pixel.

**Resolution: this token keeps the name `text-sm` in the design system, and is registered in Tailwind as
`--text-supporting`.** Tailwind's own `text-sm` is left untouched at 14px — which coincides with
`text-body`'s size anyway, so a shadcn primitive that ships `text-sm` lands on the right size without
patching. Components in our own code use `text-body` (14px/1.5) and `text-supporting` (13px/1.4)
explicitly; `text-sm` in a codebase search means "shadcn shipped this and nobody has patched it yet."

Clearing Tailwind's whole type scale with `--text-*: initial` — the trick that *does* work for colour, and
is what enforces U85 there — was considered and rejected here: it would make `text-xs`/`text-base`/`text-lg`
unknown utilities and break every shadcn primitive at install time.

### Two deliberate deviations

**Body is 14px, not 16px.** The planner console must fit seven fields on a row and ~20 rows on screen
(§7.3). 14px Inter at 1.5 line height is comfortably legible for a seated desk user and buys roughly 12%
more rows than 16px. This is a density decision, made knowingly.

**Driver chat overrides to 16px** (`text-body-lg`). A stressed driver holding a phone at arm's length in
sunlight is a different reading situation entirely, and 16px also prevents iOS Safari's auto-zoom on
input focus. The density argument does not apply to a surface showing three options.

**11px is a hard floor.** Below that, Inter's legibility falls off sharply on low-DPI Android screens.
If something does not fit at 11px, the layout is wrong — do not shrink the type.

---

## Hierarchy in dense views

In a table there is no room for size-based hierarchy — every cell is `text-body`. Hierarchy comes from:

1. **Weight** — 600 for the primary identifier in a row (shipment id), 400 for everything else
2. **Colour** — `text-primary` for what matters, `text-secondary` for context
3. **Family** — mono marks values as data, which separates them from labels without changing size
4. **Case** — column headers are `text-label`, uppercase, `text-tertiary`

Never use size to create hierarchy inside a table row. It breaks vertical rhythm and costs scan speed.

---

## Promise-state typography

The four state chips (`color.md`) all use `text-label` — 12px, 600, uppercase, 0.04em tracking. Uppercase
here is deliberate: it makes the state read as a *status token* rather than as prose, which reinforces
§7.2b's rule that state declarations are templated, not generated.

**State words are never abbreviated.** `PENDING CONFIRMATION` does not become `PENDING CONF.` or `PC`. If
it does not fit, the container is too small. Ambiguity in this specific label is the failure mode the whole
design guards against.

---

## Copy rules that are typographic

From §7.2b, expressed as typesetting:

- **Times always carry their dock and date.** `Dock D4 · Tue 4 Aug · 12:15–13:30`. The middot separators
  are part of the pattern — they group three facts as one unit rather than three fragments.
- **Use an en dash for time ranges** (`12:15–13:30`), never a hyphen. With mono figures either side, the
  en dash is what makes it read as a span.
- **Never letterspace lowercase body text.** Tracking is defined only on `text-label` and `text-micro`.

---

## Internationalisation

English only in v1, structured so Hindi/Hinglish is a translation job rather than a rebuild (U31).

- **All copy externalised as keys.** No hardcoded strings in components — especially the §7.2b state
  templates, which are the most painful to extract retroactively.
- **Layouts tolerate ~30% text expansion.** Devanagari also runs taller than Latin, so line-height
  containers must not be fixed-height. Test every chip, button and table header at +30%.
- **Inter covers Latin only.** Hindi requires a Devanagari companion — Noto Sans Devanagari is the
  natural pairing and metrically compatible enough for mixed runs. Not loaded in v1.
- **Dates and numbers are locale-formatted** via `Intl`, never string-concatenated. `en-IN` from the start,
  so the format is already right before any translation happens.

---

## Accessibility

- **Text is never below 11px**, and never below 14px on driver or gate surfaces (field conditions, U30).
- **Line length caps at ~75 characters** for prose; chat bubbles cap at 60ch for comfortable reading.
- **Never communicate through weight or style alone.** A bolded row is not sufficient signal for state.
- **Respect user font scaling.** All sizes in `rem`, root at 16px. The layout must survive 200% zoom —
  the planner table becomes horizontally scrollable rather than truncating, since a truncated
  displacement warning is worse than a scrollbar.
- **Never disable text selection.** Planners copy shipment IDs into other systems constantly.
