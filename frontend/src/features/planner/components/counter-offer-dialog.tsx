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
import { Skeleton } from '@/shared/ui/skeleton'
import { fetchFeasibleSlots } from '../lib/api'
import { formatInterval, formatTime } from '../lib/format'
import { REASON_LABELS, REJECT_REASON_CODES, type RejectReasonCode } from '../lib/reasons'
import type { FeasibleSlotOption, PlannerQueueRow } from '../lib/types'

/**
 * Counter-offer -- `flows-and-states.md` Flow 2, FR-PLN-002, issue #63.
 *
 * ## A deliberate, flagged deviation from `screens.md` section 4
 *
 * The design's affordance is a **board picker** (U103): the planner switches to the Board tab, an
 * open interval on an eligible dock is clicked, ineligible docks dim in place. That board is
 * blocked on `dock_occupancy.state`, a column no live database has (issue #53, migration written
 * but unapplied), so the spatial picker cannot be built today.
 *
 * This dialog is the interim entry point, and it is a form rather than a grid. **What it does not
 * do is weaken the guarantee**: the options offered are the ones Stage 1 says are genuinely
 * feasible for this shipment (`find_feasible_slots`), which is exactly the eligibility the dimmed
 * lanes were going to express, and the server still revalidates the chosen interval through
 * `explain_slot_eligibility` before reserving it. What is lost is the spatial context -- seeing
 * *why* a dock is unavailable by looking at what occupies it -- and that returns with the board.
 *
 * The alternative was leaving a complete, tested backend unreachable behind an unapplied
 * migration. This is flagged for the owner rather than treated as the finished design.
 *
 * ## Refusals
 *
 * `INTERVAL_UNAVAILABLE` keeps the dialog open and re-fetches, because Flow 2's own answer is
 * *"board re-renders that interval occupied, banner stays, pick again"* -- the form analogue is a
 * refreshed option list with the taken interval gone, never a dead click and never a silent
 * close. Everything else (`ALREADY_ACTIONED`, `SNAPSHOT_STALE`, `DISPLACEMENT_DETECTED`) closes
 * and reports on the row, where the planner can see it in the queue's own context.
 */
export function CounterOfferDialog({
  row,
  open,
  onOpenChange,
  onSubmit,
  busy,
  error,
  refreshToken,
}: {
  row: PlannerQueueRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (option: FeasibleSlotOption, reasonCode: RejectReasonCode, note: string | null) => void
  busy: boolean
  error: string | null
  /** Bumped by the parent after an `INTERVAL_UNAVAILABLE` so the option list re-fetches. */
  refreshToken: number
}) {
  const titleId = useId()
  const noteId = useId()
  const [options, setOptions] = useState<FeasibleSlotOption[] | null>(null)
  const [outcome, setOutcome] = useState<string>('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [slotId, setSlotId] = useState<string | null>(null)
  const [reason, setReason] = useState<RejectReasonCode | null>(null)
  const [note, setNote] = useState('')

  const shipmentId = row?.shipment_id ?? null

  useEffect(() => {
    if (!open || !shipmentId) return
    // React's own documented pattern for this (react.dev, `useEffect` -> "Fetching data"): an
    // `ignore` latch set in cleanup, so a slow first response cannot overwrite a newer one.
    let ignore = false
    setOptions(null)
    setLoadError(null)
    setSlotId(null)
    fetchFeasibleSlots(shipmentId)
      .then((res) => {
        if (ignore) return
        setOptions(res.options)
        setOutcome(res.outcome)
      })
      .catch((err: unknown) => {
        if (ignore) return
        setLoadError(err instanceof Error ? err.message : 'Could not load feasible intervals.')
      })
    return () => {
      ignore = true
    }
  }, [open, shipmentId, refreshToken])

  useEffect(() => {
    if (!open) return
    setReason(null)
    setNote('')
  }, [open, shipmentId])

  if (!row) return null

  const selected = options?.find((o) => o.slot_id === slotId) ?? null
  const canSend = selected !== null && reason !== null && !busy

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent aria-labelledby={titleId} className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle id={titleId}>
            Counter-offer ·{' '}
            <span translate="no" className="font-mono">
              {row.shipment_id}
            </span>
          </DialogTitle>
        </DialogHeader>

        {/* The persistent context banner screens.md section 4 requires: a planner must never
            forget which request they are picking for, and Cancel is always reachable. */}
        <p className="-mt-2 text-supporting text-muted-foreground">
          Picking a new interval for {row.driver_name ?? row.shipment_id}
          {row.carrier_name ? ` · ${row.carrier_name}` : ''}. Currently{' '}
          <span translate="no" className="font-mono tabular-nums">
            {formatInterval(row)}
          </span>
          .
        </p>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-label text-subtle-foreground uppercase" id={`${titleId}-slot`}>
              Feasible intervals
            </span>
            {loadError ? (
              <Alert variant="danger">
                Couldn’t load feasible intervals. {loadError}
              </Alert>
            ) : options === null ? (
              <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading intervals">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : options.length === 0 ? (
              // A gap is a gap. No invented interval, and the outcome code is named because
              // NO_SAME_DAY_SLOT and NO_FEASIBLE_SLOT are different facts.
              <Alert variant="warning">
                Stage 1 found no feasible interval for this shipment
                {outcome ? ` (${outcome.toLowerCase().replace(/_/g, ' ')})` : ''}. There is nothing
                to counter-offer — reject with a reason, or leave it for the deadline.
              </Alert>
            ) : (
              <RadioGroup
                aria-labelledby={`${titleId}-slot`}
                value={slotId ?? undefined}
                onValueChange={setSlotId}
                className="flex flex-col gap-1"
              >
                {options.map((option) => (
                  <div key={option.slot_id} className="flex min-h-8 items-start gap-2">
                    <RadioGroupItem
                      value={option.slot_id}
                      id={`${titleId}-${option.slot_id}`}
                      className="mt-1"
                    />
                    <Label
                      htmlFor={`${titleId}-${option.slot_id}`}
                      className="flex cursor-pointer flex-col gap-0.5 text-body"
                    >
                      <span translate="no" className="font-mono tabular-nums">
                        {option.dock_code} · {option.slot_local_date} ·{' '}
                        {formatTime(option.slot_start_ts)}–{formatTime(option.slot_end_ts)}
                      </span>
                      {option.differentiator ? (
                        <span className="text-supporting text-muted-foreground">
                          {option.differentiator}
                        </span>
                      ) : null}
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-label text-subtle-foreground uppercase" id={`${titleId}-reason`}>
              Reason
            </span>
            {/* Same five codes as reject. `COUNTER_OFFER_REASON_CODES = REJECTION_REASON_CODES`
                in the service -- flagged there as an assumption, so it is flagged here too. */}
            <RadioGroup
              aria-labelledby={`${titleId}-reason`}
              value={reason ?? undefined}
              onValueChange={(v) => setReason(v as RejectReasonCode)}
              className="grid grid-cols-2 gap-2"
            >
              {REJECT_REASON_CODES.map((code) => (
                <div key={code} className="flex min-h-8 items-center gap-2">
                  <RadioGroupItem value={code} id={`${titleId}-r-${code}`} />
                  <Label htmlFor={`${titleId}-r-${code}`} className="cursor-pointer text-body">
                    {REASON_LABELS[code]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={noteId} className="text-label text-subtle-foreground uppercase">
              Internal note <span className="normal-case">(never shown to the driver)</span>
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

          <p className="text-micro text-subtle-foreground">
            The offered interval is <strong>reserved</strong>, not merely shown — the appointment
            moves to it and stays pending the driver’s reply, so nobody else can take it in the
            meantime.
          </p>

          {error ? <Alert variant="danger">{error}</Alert> : null}
        </div>

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="constructive"
            aria-disabled={!canSend}
            title={
              selected === null
                ? 'Choose an interval first.'
                : reason === null
                  ? 'Choose a reason first.'
                  : undefined
            }
            onClick={() => {
              if (!canSend || selected === null || reason === null) return
              onSubmit(selected, reason, note.trim() === '' ? null : note.trim())
            }}
          >
            {busy ? 'Sending…' : 'Send counter-offer'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
