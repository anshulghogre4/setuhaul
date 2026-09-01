import { useEffect, useId, useState } from 'react'

import { formatUserFriendlyError } from '@/core/http/api'
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
import { escalateException } from '../lib/api'
import { REASON_META, REASON_ORDER } from '../lib/reasons'
import {
  ESCALATE_SEVERITY_CODES,
  isEscalatePreview,
  type EscalatePreview,
  type EscalationQueueItem,
  type EscalationReason,
} from '../lib/types'

/**
 * **Escalate** -- the first entry of the detail pane's overflow menu (`screens.md` section 3,
 * `stitch-prompts.md` prompt 7's `[ ⋯ ]` line: "a ghost icon button ... holding Escalate, Reassign
 * and Cancel").
 *
 * ## What this control actually does, since the design names it without defining it
 *
 * `screens.md` puts *Escalate* in the overflow and says nothing else about it -- no argument list,
 * no target, no flow. The only escalate-shaped thing that exists is
 * `POST /api/v1/operations/escalate` -> `escalate_exception`, which opens (or refreshes) a case in
 * `escalation_queue` for a **shipment** under one of section 7.4's nine reasons. So this dialog
 * raises a *second, differently-reasoned case on the same shipment* -- "this notification failure
 * turns out to be a safety matter" -- rather than pretending to bump a severity or hand ownership
 * upward, neither of which any shipped tool can do. The wording on screen says exactly that; it
 * does not imply an escalation ladder the backend has no rung for.
 *
 * ## Why the reason list excludes the open case's own reason
 *
 * `escalate_exception`'s dedupe key is `(shipment_id, calendar day, escalation_type)` and, since
 * issue #96, the ON CONFLICT predicate matches only non-terminal rows. Re-escalating the same
 * shipment under the *same* reason on the same day therefore does not open anything -- it
 * refreshes the row already on screen and hands it straight back, which would read as "nothing
 * happened". That option is rendered and disabled with the reason stated, rather than removed
 * (`components.md` foundations section 18: a control a coordinator needs to understand explains
 * itself instead of vanishing).
 *
 * ## Two presses, and the first one writes nothing
 *
 * Step 1 posts `confirmed: false`, which returns `CONFIRMATION_REQUIRED` **before the service
 * touches the database** (`escalation_service.py:128-141`). Its `note` is rendered verbatim as the
 * confirm copy. Step 2 posts the identical body with `confirmed: true`. This is the same
 * two-read/two-gate discipline `flows-and-states.md` Flow 3 uses for a co-pilot draft: the
 * sentence a coordinator agrees to is the server's own account of what is about to happen, not a
 * client-side paraphrase of it.
 */
export function EscalateDialog({
  item,
  open,
  onOpenChange,
  onEscalated,
}: {
  item: EscalationQueueItem
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Fired after a real `confirmed: true` write, with the new (or refreshed) case's id. */
  onEscalated: (escalationId: string) => void
}) {
  const titleId = useId()
  const typeId = useId()
  const severityId = useId()
  const reasonId = useId()

  const [escalationType, setEscalationType] = useState<EscalationReason>(
    () => firstOtherReason(item.escalation_type),
  )
  const [severity, setSeverity] = useState<string>('HIGH')
  const [reason, setReason] = useState('')
  const [preview, setPreview] = useState<EscalatePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Re-open on a different escalation must not carry the previous one's half-finished case.
  useEffect(() => {
    if (!open) return
    setEscalationType(firstOtherReason(item.escalation_type))
    setSeverity('HIGH')
    setReason('')
    setPreview(null)
    setError(null)
  }, [open, item.escalation_id, item.escalation_type])

  // Any edit after a preview invalidates it: the confirm copy describes the body that produced it,
  // and confirming a preview taken against different fields is exactly the mis-commit the two-step
  // exists to prevent.
  function edit<T>(set: (value: T) => void) {
    return (value: T) => {
      setPreview(null)
      setError(null)
      set(value)
    }
  }

  const trimmed = reason.trim()
  const canSubmit = trimmed.length > 0 && !busy

  async function submit(confirmed: boolean) {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const result = await escalateException({
        shipmentId: item.shipment_id,
        escalationType,
        severityCode: severity,
        reason: trimmed,
        confirmed,
      })
      if (isEscalatePreview(result)) {
        setPreview(result)
        return
      }
      onEscalated(result.escalation_id)
      onOpenChange(false)
    } catch (err) {
      // `components.md` foundations section 13's mandatory phrase for a failed write. It is true
      // in both halves here: the preview call writes nothing by construction, and the confirm call
      // rolls its session back (`operations.py:335-337`) before the error reaches this line.
      setError(`${formatUserFriendlyError(err)} Nothing has changed — no case was opened.`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent aria-labelledby={titleId} className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle id={titleId}>
            Escalate{' '}
            <span translate="no" className="font-mono">
              {item.shipment_id}
            </span>
          </DialogTitle>
        </DialogHeader>

        <p className="-mt-2 text-supporting text-muted-foreground">
          This opens a <strong>separate</strong> operations case on the same shipment under a
          different reason. It does not change {item.escalation_id}, its owner or its SLA clock —
          that case stays exactly where it is.
        </p>

        <div className="flex flex-col gap-4">
          {/* Native controls, properly labelled -- the same call `03-planner-dock-board`'s Fork G
              resolved for the block-dock form, rather than the mockup's div-with-a-role pattern. */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={typeId}>Reason</Label>
            <select
              id={typeId}
              value={escalationType}
              onChange={(e) => edit(setEscalationType)(e.target.value as EscalationReason)}
              className="h-9 rounded-md border border-input bg-card px-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              {REASON_ORDER.map((code) => (
                <option key={code} value={code} disabled={code === item.escalation_type}>
                  {REASON_META[code].label}
                  {code === item.escalation_type ? ' — already open on this shipment today' : ''}
                </option>
              ))}
            </select>
            <p className="text-micro text-subtle-foreground">
              {REASON_META[item.escalation_type].label} is unavailable because escalations dedupe
              on shipment, day and reason — re-raising it would refresh {item.escalation_id} rather
              than open a new case.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={severityId}>Severity</Label>
            <select
              id={severityId}
              value={severity}
              onChange={(e) => edit(setSeverity)(e.target.value)}
              className="h-9 w-40 rounded-md border border-input bg-card px-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              {ESCALATE_SEVERITY_CODES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
            <p className="text-micro text-subtle-foreground">
              Severity sets the new case&apos;s SLA budget. `Source: assumption, untested` —
              `SLA_BUDGET_MIN` carries no documented policy behind its per-severity minutes.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={reasonId}>What is happening</Label>
            <textarea
              id={reasonId}
              value={reason}
              onChange={(e) => edit(setReason)(e.target.value)}
              maxLength={500}
              rows={3}
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
            <p className="text-micro text-subtle-foreground">
              Stored on the new case and shown to whoever picks it up. Never sent to the driver.
            </p>
          </div>

          {preview ? (
            // The server's own words, not ours. `role="status"` rather than `alert`: this is the
            // expected next step of a two-press flow, not an interruption.
            <div
              role="status"
              className="flex flex-col gap-1 rounded-md border border-info-border bg-info-bg px-3 py-2 text-body text-info-fg"
            >
              <p className="font-semibold">Confirm before this becomes a real case</p>
              <p>{preview.note}</p>
            </div>
          ) : null}

          {error ? <Alert variant="danger">{error}</Alert> : null}
        </div>

        <DialogFooter>
          {/* U79: the safer action first in DOM order. */}
          <Button variant="neutral" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="cautionary"
            aria-disabled={!canSubmit}
            title={trimmed.length === 0 ? 'Say what is happening first.' : undefined}
            onClick={() => void submit(preview !== null)}
          >
            {busy
              ? preview
                ? 'Escalating…'
                : 'Checking…'
              : preview
                ? 'Escalate'
                : 'Preview escalation'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The default selection: the first section 7.4 reason that is not the one already open, so the
 *  dialog never opens pre-set to the one option it cannot submit. */
function firstOtherReason(current: EscalationReason): EscalationReason {
  return REASON_ORDER.find((r) => r !== current) ?? REASON_ORDER[0]
}
