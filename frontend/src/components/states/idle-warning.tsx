import { useEffect, useRef } from 'react'

import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui/dialog'

/**
 * Artboard 29.  Warn at 55 minutes, sign out at 60 (planner/ops; 25/30 for carrier/admin).
 *
 * **Initial focus goes to "Stay signed in"** -- the recoverable action.  Never the countdown,
 * never the destructive option.  This is accessibility-behaviour.md's focus-management
 * contract, and it is why the ref exists rather than letting the DOM decide: Radix's default
 * initial focus is the first focusable element, which here is "Sign out now".
 *
 * **Drivers never see this.**  A login screen at a roadside mid-exception is a product
 * failure, so `idlePolicyFor('DRIVER')` returns null and this never mounts for them.  The
 * gate kiosk is likewise exempt -- an officer cannot re-authenticate with gloves on every
 * few minutes.
 *
 * "Sign out now" is FIRST in DOM order and "Stay signed in" second (U79), so the safer
 * action is not what a fast keyboard user overshoots into... which is exactly why the
 * explicit initial-focus ref is doing real work here rather than being belt-and-braces.
 *
 * ⚠ The two body sentences are placeholder wording.  auth-and-scoping.md specifies the
 * timing, the modal and the "Stay signed in" button, but no foundations file carries this
 * dialog's copy.  The countdown's mono/tabular treatment IS spec-sourced.
 */
export function IdleWarning({
  open,
  remainingLabel,
  onStay,
  onSignOut,
}: {
  open: boolean
  /** "5:00" -- mono, tabular-nums, from the shared 1 Hz clock. */
  remainingLabel: string
  onStay: () => void
  onSignOut: () => void
}) {
  const stayRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (open) stayRef.current?.focus()
  }, [open])

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onStay()}>
      <DialogContent
        showCloseButton={false}
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          stayRef.current?.focus()
        }}
        className="w-full max-w-120 gap-0 rounded-xl bg-overlay p-6 shadow-overlay"
      >
        <DialogTitle className="text-h2">
          You’ll be signed out in{' '}
          <span className="font-mono" translate="no">
            {remainingLabel}
          </span>
        </DialogTitle>
        <DialogDescription className="mt-2 text-body text-muted-foreground">
          You’ve been idle for a while. Anything you have typed is saved and will still be here
          when you sign back in.
        </DialogDescription>
        <div className="mt-6 flex justify-end gap-4">
          <Button variant="neutral" onClick={onSignOut}>
            Sign out now
          </Button>
          <Button ref={stayRef} variant="constructive" onClick={onStay}>
            Stay signed in
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
