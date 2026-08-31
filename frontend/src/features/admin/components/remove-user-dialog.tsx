import { TriangleAlert } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { getUserRemovalImpact } from '../lib/api'
import { adminRemovalImpactEnabled } from '../lib/flags'
import type { AdminUser } from '../lib/types'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

/**
 * Screen 4 — Remove user, typed confirmation. **🟢, built for real** (`implementation-spec.md`
 * §3): typed-email confirmation, a generated `Idempotency-Key`, a real Supabase Auth identity
 * deletion, local deactivation that preserves audit FK integrity, and an audit-log entry — every
 * one of those is genuinely shipped in `admin_user_service.py::remove_user`.
 *
 * This is the surface's one genuinely novel interaction pattern relative to everything E5.0–E5.5
 * built (`accessibility.md`'s own framing), so the four rules it names are implemented explicitly
 * rather than inherited:
 *
 *  1. **Focus lands on the typed field, never on the destructive button** — `components.md`
 *     foundations §10's modal rule. Radix would focus the first tabbable child anyway; it is done
 *     by ref through `onOpenAutoFocus` so the guarantee does not depend on DOM ordering surviving
 *     a future edit.
 *  2. **The confirm button stays genuinely unavailable until the typed value matches, and says
 *     why.** `aria-disabled` + `tabIndex={0}` + `title` + `aria-describedby`, with the handler
 *     early-returning — not the HTML `disabled` attribute. MDN is explicit that `disabled` removes
 *     the element from the focus order while `aria-disabled` keeps it focusable, and names exactly
 *     this case ("a button which is important to keep in the page's focus order, but its action is
 *     presently unavailable") as what `aria-disabled` is for. A screen-reader user therefore
 *     reaches the button, hears it is unavailable, and hears the reason — which is what
 *     `accessibility.md` asks for and what `disabled` alone would prevent.
 *     (MDN, `aria-disabled`, checked 2026-08-29.)
 *  3. **Assertive on open and on successful commit.** The consequence panel is `role="alert"`, so
 *     opening the dialog announces what is about to be lost; the success announcement is owned by
 *     the Users tab's own `role="alert"` region, because this component unmounts on success.
 *  4. **A mismatch is not an error state.** No red border, no error text — nothing has been
 *     submitted yet. The button simply has not enabled (`mockup.html` §4.3, verbatim reasoning).
 *
 * Cancel is first in DOM order (U79, safer action first) and `DialogFooter`'s `gap-4` keeps the
 * 16px minimum §19 requires between a neutral and a destructive control.
 */
export function RemoveUserDialog({
  user,
  open,
  onOpenChange,
  onConfirm,
  busy,
  errorDetail,
}: {
  user: AdminUser | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (user: AdminUser) => void
  busy?: boolean
  /** A failed removal keeps the dialog open and names the cause; it never closes on failure. */
  errorDetail?: string | null
}) {
  const [typed, setTyped] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)
  const whyId = useId()
  const fieldId = useId()

  /**
   * `null` means "not known" — never "zero". A-G8 / issue #76: the sentence
   * `edge-cases.md` #1 locks names a real number, so it renders only once one has actually
   * arrived. A failed or in-flight read leaves this `null` and the sentence is simply absent,
   * which is the same honest state the dialog shipped in before the endpoint existed.
   */
  const [impactCount, setImpactCount] = useState<number | null>(null)
  const userId = user?.user_id ?? null

  // Clearing on close rather than on open: a reopened dialog must never start with a previously
  // typed value still satisfying the gate.
  useEffect(() => {
    if (!open) setTyped('')
  }, [open])

  /**
   * Fetching here rather than in `UsersTab` on purpose: the count is only ever rendered by this
   * dialog, and hoisting it would make the Users tab issue a request per row hover/menu open.
   *
   * `GET .../removal-impact` is a pure read and **advisory** — `remove_user` recounts inside its
   * own removing transaction and never trusts this value — so a failure is swallowed rather than
   * routed to `errorDetail`, which is reserved for a write that actually failed. Blocking a
   * removal because a preview read 500'd would be strictly worse than removing without the
   * sentence.
   *
   * The reflow this causes lands early: the Remove button stays unavailable until the admin has
   * typed a full email address, which takes far longer than the read, so the sentence appears
   * while they are typing rather than shifting layout under a destructive control at click time.
   *
   * `cancelled` guards the switch-users race (`apiGet` takes no `AbortSignal`, and widening the
   * shared HTTP helper is not this change's to do) — a late response for a previously-selected
   * user must never paint a count against the one now on screen.
   */
  useEffect(() => {
    if (!adminRemovalImpactEnabled || !open || userId === null) {
      setImpactCount(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const impact = await getUserRemovalImpact(userId)
        if (!cancelled) setImpactCount(impact.active_escalation_count)
      } catch {
        if (!cancelled) setImpactCount(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, userId])

  if (!user) return null

  const matches = typed.trim() === user.email
  const canCommit = matches && !busy
  const whyUnavailable = busy ? 'Removing…' : 'Type the user’s email to confirm'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          inputRef.current?.focus()
        }}
      >
        <DialogHeader>
          {/* Not red: the title states the action, the button carries the consequence
              (`mockup.html` §4.1). */}
          <DialogTitle>Remove {user.full_name ?? user.email}</DialogTitle>
        </DialogHeader>

        <div
          role="alert"
          className="flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg px-4 py-3 text-body text-danger-fg"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div className="flex flex-col gap-1">
            <p>
              This account will be removed permanently and will not appear in user search again.
            </p>
            {/*
              A-G8 / issue #76, wired 2026-08-29 against `GET /admin/users/{id}/removal-impact`.

              Three conditions, all load-bearing: the flag is on, the read has actually answered
              (`!== null`, not falsy — 0 is a real answer), and the count is above zero. A user who
              owns nothing gets no sentence at all rather than "owns 0 active escalations", which
              `edge-cases.md` #1's copy was never written to say.

              The count comes from the server's `count(*) OVER ()`, evaluated before its own
              `LIMIT 50` — so it is never `active_escalations.length`, which would silently cap at
              50 and under-report a genuinely large removal.
            */}
            {adminRemovalImpactEnabled && impactCount !== null && impactCount > 0 ? (
              <p>
                This user owns {impactCount} active{' '}
                {impactCount === 1 ? 'escalation' : 'escalations'} — they will show as unowned once
                removed.
              </p>
            ) : null}
            <p>Their past actions stay attributable in the Audit tab.</p>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId}>
            <span>
              Type <span className="font-data">{user.email}</span> to confirm
            </span>
          </Label>
          <Input
            ref={inputRef}
            id={fieldId}
            type="text"
            value={typed}
            autoComplete="off"
            spellCheck={false}
            className="font-data"
            onChange={(e) => setTyped(e.currentTarget.value)}
          />
        </div>

        {errorDetail ? (
          <p role="alert" className="text-supporting text-danger-fg">
            That didn’t save. <strong className="font-semibold">Nothing has changed.</strong>{' '}
            {errorDetail}
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            aria-disabled={!canCommit}
            tabIndex={0}
            title={canCommit ? undefined : whyUnavailable}
            aria-describedby={canCommit ? undefined : whyId}
            className={canCommit ? undefined : 'opacity-50'}
            onClick={() => {
              if (!canCommit) return
              onConfirm(user)
            }}
          >
            Remove user
          </Button>
          {canCommit ? null : (
            <span id={whyId} className="sr-only">
              {whyUnavailable}
            </span>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
