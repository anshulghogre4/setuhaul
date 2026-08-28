import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * `cn()` — clsx + tailwind-merge.
 *
 * ## Why this is no longer a bare `twMerge`
 *
 * **A real, systemic defect, found by measuring a render during E5.1 (issue #36) on
 * 2026-08-27 — it was live in E5.0's shell too, not introduced here.**
 *
 * `typography.md`'s scale registers custom `--text-*` tokens (`text-body`, `text-h1`,
 * `text-label`, …), and `color.md`'s scale registers custom `--color-*` tokens whose utilities
 * are also `text-*` (`text-muted-foreground`, `text-state-pending-text`, `text-danger-fg`, …).
 * Out of the box **tailwind-merge cannot tell them apart** — it has no knowledge of this
 * project's theme, so every unrecognised `text-*` lands in one conflict group and the *later*
 * class silently deletes the earlier one. Reproduced directly:
 *
 * ```
 * twMerge('text-body text-muted-foreground')   -> 'text-muted-foreground'   // size GONE
 * twMerge('text-muted-foreground text-body')   -> 'text-body'               // colour GONE
 * twMerge('text-label uppercase text-primary') -> 'uppercase text-primary'  // size GONE
 * ```
 *
 * So any component writing `cn('text-body text-muted-foreground')` — the single most common
 * idiom in this codebase — was emitting no font size at all and inheriting the 16px root.
 * **How it was caught:** the driver-chat promise chip measured `font-size: 16px` in a real
 * render when its class list said `text-body` (14px), and dumping the element's rendered
 * `className` showed `text-body` was not in it. It would never have surfaced from reading the
 * source, and it passed the 14px-floor audit by accident because 16 > 14.
 *
 * ## The fix, taken from tailwind-merge's own configuration docs (fetched 2026-08-27)
 *
 * `extend.theme.text` tells tailwind-merge which `text-*` values are **font sizes**; everything
 * else falls through to `text-color`, and the two stop conflicting. Verified in both directions
 * plus the cases that MUST still collapse:
 *
 * ```
 * cn('text-body text-muted-foreground')  -> 'text-body text-muted-foreground'   ✓ both kept
 * cn('text-muted-foreground text-body')  -> 'text-muted-foreground text-body'   ✓ both kept
 * cn('text-body text-body-lg')           -> 'text-body-lg'                      ✓ still merges
 * cn('text-muted-foreground text-foreground') -> 'text-foreground'              ✓ still merges
 * cn('text-sm text-muted-foreground')    -> 'text-sm text-muted-foreground'     ✓ shadcn's own
 * ```
 *
 * **Keep this list in step with `theme.css`'s `--text-*` block.** A new size added there and not
 * here is a size that will be silently dropped again — which is exactly the failure this comment
 * exists to stop recurring. `text-sm` / `text-xs` etc. are Tailwind's own and are already in
 * tailwind-merge's default config; only the project's custom names go below.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [
        'display',
        'h1',
        'h2',
        'h3',
        'body',
        'body-lg',
        'supporting',
        'label',
        'micro',
      ],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
