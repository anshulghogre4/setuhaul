import { useEffect, useId, useState } from 'react'

import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Label } from '@/shared/ui/label'
import { RadioGroup, RadioGroupItem } from '@/shared/ui/radio-group'
import { formatInterval } from '../lib/format'
import {
  DRIVER_FACING_SENTENCE,
  NEXT_STEP_SENTENCE,
  REASON_LABELS,
  REJECT_REASON_CODES,
  type RejectReasonCode,
} from '../lib/reasons'
import type { PlannerQueueRow } from '../lib/types'

/**
 * States 12-13. `flows-and-states.md` Flow 3, `components.md` foundations section 11 verbatim:
 * **category -> internal detail -> preview -> send**, and the preview step is not optional.
 *
 * The preview exists because the reason is **sent to the driver**, so the person sending it reads
 * the exact words first. The five sentences are `stitch-prompts.md` section 5's own, never
 * rewritten and never generated (`lib/reasons.ts`).
 *
 * ## Built against the enum, not the prose (issue #66)
 *
 * The wire field is `reason_code`, not the `rejection_reason` earlier design prose named, and the
 * five values are now enforced **server-side** with a 422 `INVALID_REASON_CODE` naming the
 * supported set. That changes this dialog's status from "a client-side courtesy" (which is what
 * `implementation-spec.md` section 5.1 G7 recorded) to a real contract on both ends. The 422 is
 * still handled below rather than assumed unreachable -- if the vocabularies ever drift, a
 * planner should see which values the server accepts, not a generic failure.
 *
 * On failure the dialog **stays open and every value survives** (State 13). The one exception is
 * `ALREADY_ACTIONED`: that is not a failed send, it is somebody else's write winning the race, so
 * the dialog closes and the row itself reports what won -- `edge-cases.md` #1's "updates in place
 * to show the actual outcome" belongs on the row, not in a modal the planner has to dismiss.
 */
export function RejectDialog({
  row,
  open,
  onOpenChange,
  onSubmit,
  busy,
  error,
}: {
  row: PlannerQueueRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (reasonCode: RejectReasonCode, note: string | null) => void
  busy: boolean
  error: string | null
}) {
  const titleId = useId()
  const noteId = useId()
  const [reason, setReason] = useState<RejectReasonCode | null>(null)
  const [note, setNote] = useState('')

  // A second open must never inherit the previous request's reason -- sending last decision's
  // reason code to a different driver is exactly the kind of error this dialog exists to prevent.
  useEffect(() => {
    if (!open) return
    setReason(null)
    setNote('')
  }, [open, row?.appointment_id])

  if (!row) return null

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent aria-labelledby={titleId} className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle id={titleId}>
            Reject request ·{' '}
            <span translate="no" className="font-mono">
              {row.shipment_id}
            </span>
          </DialogTitle>
        </DialogHeader>
        <p className="-mt-2 font-mono text-supporting text-muted-foreground tabular-nums" translate="no">
          {formatInterval(row)}
        </p>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-label text-subtle-foreground uppercase" id={`${titleId}-reason`}>
              Reason
            </span>
            <RadioGroup
              aria-labelledby={`${titleId}-reason`}
              value={reason ?? undefined}
              onValueChange={(v) => setReason(v as RejectReasonCode)}
              className="grid grid-cols-2 gap-2"
            >
              {REJECT_REASON_CODES.map((code) => (
                <div key={code} className="flex min-h-8 items-center gap-2">
                  <RadioGroupItem value={code} id={`${titleId}-${code}`} />
                  <Label htmlFor={`${titleId}-${code}`} className="cursor-pointer text-body">
                    {REASON_LABELS[code]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={noteId} className="text-label text-subtle-foreground uppercase">
              Internal note{' '}
              <span className="normal-case">(never shown to the driver)</span>
            </Label>
            <textarea
              id={noteId}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              rows={2}
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
          </div>

          {/* The preview. Updates the instant the radio changes, and always ends pointing at
              alternatives -- "a rejection is never the last message in a thread". */}
          <div className="flex flex-col gap-2">
            <span className="text-label text-subtle-foreground uppercase">The driver will receive</span>
            <blockquote className="rounded-md border border-border bg-background p-3 text-body text-foreground">
              {reason ? (
                `“${DRIVER_FACING_SENTENCE[reason]} ${NEXT_STEP_SENTENCE}”`
              ) : (
                <span className="text-muted-foreground">
                  Choose a reason to see the exact words the driver receives.
                </span>
              )}
            </blockquote>
            <p className="text-micro text-subtle-foreground">
              Rendered from the reason code, verbatim. Nothing here is model-generated, and there is
              deliberately no free-text substitute.
            </p>
          </div>

          {error ? <Alert variant="danger">{error}</Alert> : null}
        </div>

        {/* Cancel FIRST in DOM order (U79) and in a separate group, 16px apart -- destructive is
            never adjacent to constructive (`components.md` section 1). */}
        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            aria-disabled={reason === null || busy}
            title={reason === null ? 'Choose a reason first.' : undefined}
            onClick={() => {
              if (reason === null || busy) return
              onSubmit(reason, note.trim() === '' ? null : note.trim())
            }}
          >
            {busy ? 'Sending…' : 'Send rejection'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
