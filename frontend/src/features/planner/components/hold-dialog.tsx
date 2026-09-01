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
import type { PlannerQueueRow } from '../lib/types'

/**
 * **Hold for information** -- `flows-and-states.md` Flow 4 step 1:
 *
 * > *"`H` or click Hold → **mandatory question field** → `hold_for_information(appointment_id,
 * > question, Idempotency-Key)`."*
 *
 * The question is mandatory in the design and in the contract alike (`question: str` with
 * `min_length=1` on `HoldForInformationBody`), so the commit is gated on it here rather than
 * letting the server 422 a blank one. That is the same gating discipline the reject and
 * counter-offer dialogs already apply to their reason codes.
 *
 * ## What the dialog tells the planner it is about to buy, and why that wording is careful
 *
 * The affordance is named "hold" and U67 describes a **paused** clock. The shipped tool grants a
 * single bounded **extension** -- `now + N minutes`, server-chosen, one per request -- and time
 * keeps elapsing against it. So this dialog says "extends the deadline once" rather than "pauses
 * the clock": a planner who believes the clock is stopped will not come back in time. The same
 * honesty is carried into the row's countdown treatment (`queue-row.tsx`) and the divergence is
 * flagged for the owner rather than resolved silently in either direction.
 */
export function HoldDialog({
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
  onSubmit: (question: string) => void
  busy: boolean
  error: string | null
}) {
  const titleId = useId()
  const questionId = useId()
  const [question, setQuestion] = useState('')

  useEffect(() => {
    if (open) setQuestion('')
  }, [open, row?.appointment_id])

  if (!row) return null

  const trimmed = question.trim()
  const canSend = trimmed.length > 0 && !busy

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent aria-labelledby={titleId} className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle id={titleId}>
            Hold{' '}
            <span translate="no" className="font-mono">
              {row.shipment_id}
            </span>{' '}
            for information
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={questionId}>What do you need from the driver?</Label>
            <textarea
              id={questionId}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={500}
              rows={3}
              // Autofocus is correct here specifically: the dialog exists to collect this one
              // value, and `H` opened it from a keyboard-first queue.
              autoFocus
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
            <p className="text-micro text-subtle-foreground">
              Required. This is the question the driver is being held against, and it is stored on
              the request.
            </p>
          </div>

          <p className="text-supporting text-muted-foreground">
            Holding <strong>extends this request&apos;s deadline once</strong>, by a fixed amount
            the server decides — you cannot choose how long, and there is no second hold on this
            request. The clock keeps running against the new deadline; it does not stop.
          </p>

          {error ? <Alert variant="danger">{error}</Alert> : null}
        </div>

        <DialogFooter>
          {/* U79: the safer action first in DOM order. */}
          <Button variant="neutral" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="neutral"
            aria-disabled={!canSend}
            title={trimmed.length === 0 ? 'Write the question first.' : undefined}
            onClick={() => {
              if (!canSend) return
              onSubmit(trimmed)
            }}
          >
            {busy ? 'Holding…' : 'Hold for information'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
