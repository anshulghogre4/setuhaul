import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Label } from '@/shared/ui/label'
import { RadioGroup, RadioGroupItem } from '@/shared/ui/radio-group'
import { formatInterval, formatTime } from '../lib/format'
import { REASON_LABELS, REJECT_REASON_CODES, type RejectReasonCode } from '../lib/reasons'
import type { FeasibleSlotOption, PlannerQueueRow } from '../lib/types'

/**
 * U103's **persistent context banner** -- `screens.md` section 4:
 *
 * > *"A persistent context banner names the shipment and offers Cancel — a planner must never
 * > forget which request they're picking a slot for, and must always have a clean way out without
 * > committing anything."*
 *
 * Presentational: every piece of state below is owned by `DockBoardPanel`, which also owns the one
 * write. That split is deliberate -- the banner and the lanes underneath it have to agree on which
 * interval is chosen, and two components each holding their own copy of that is how they stop
 * agreeing.
 *
 * ## Why the reason group appears only after an interval is chosen
 *
 * `counter_offer` requires `reason_code`, which section 4's sketch does not draw (see
 * `lib/flags.ts::plannerBoardPickerEnabled` for the fork). Rendering the radio group up front would
 * make the banner a form and the click-a-lane gesture an afterthought; rendering it on selection
 * keeps the spatial act primary and asks for the contract's argument at the moment it becomes
 * relevant. Cancel stays present in both states, which is the half of section 4 that is not
 * negotiable.
 */
export function BoardPickerBanner({
  row,
  chosen,
  reason,
  note,
  optionCount,
  outOfHorizonCount,
  loading,
  busy,
  error,
  onReasonChange,
  onNoteChange,
  onClearChoice,
  onCancel,
  onSubmit,
}: {
  row: PlannerQueueRow
  chosen: FeasibleSlotOption | null
  reason: RejectReasonCode | null
  note: string
  /** Feasible intervals Stage 1 returned, in total. */
  optionCount: number
  /** How many of those fall outside the board's drawn horizon and therefore have no lane position.
   *  Counted and stated rather than silently dropped -- see the flag's own note. */
  outOfHorizonCount: number
  loading: boolean
  busy: boolean
  error: string | null
  onReasonChange: (next: RejectReasonCode) => void
  onNoteChange: (next: string) => void
  onClearChoice: () => void
  onCancel: () => void
  onSubmit: () => void
}) {
  const canSend = chosen !== null && reason !== null && !busy

  return (
    <section
      aria-label="Counter-offer picker"
      // `role="region"` via aria-label, and it sits ABOVE the board in DOM order so a keyboard
      // user meets the context and the way out before the lanes they are about to act on.
      className="mb-3 flex flex-col gap-2 rounded-md border border-info-border bg-info-bg px-3 py-2"
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <p className="min-w-0 flex-1 text-body text-info-fg">
          Picking a new slot for{' '}
          <span translate="no" className="font-mono">
            {row.shipment_id}
          </span>
          {row.driver_name ? ` (${row.driver_name}` : ''}
          {row.driver_name && row.carrier_name ? ` · ${row.carrier_name}` : ''}
          {row.driver_name ? ')' : ''} — currently{' '}
          <span translate="no" className="font-mono tabular-nums">
            {formatInterval(row)}
          </span>
          . {loading ? 'Loading feasible intervals…' : 'Click an open interval on an eligible dock.'}
        </p>
        {/* Always reachable, in both states, per section 4. */}
        <Button variant="neutral" size="sm" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>

      {!loading && optionCount === 0 ? (
        // A gap is a gap. Stage 1 found nothing, so there is nothing to click and the banner says
        // so instead of leaving a planner hunting an empty board for a clickable interval.
        <Alert variant="warning">
          Stage 1 found no feasible interval for this shipment. There is nothing to counter-offer —
          reject with a reason, or leave it for the deadline.
        </Alert>
      ) : null}

      {outOfHorizonCount > 0 ? (
        <p className="text-supporting text-info-fg">
          {outOfHorizonCount} of {optionCount} feasible interval
          {optionCount === 1 ? '' : 's'} fall outside this board&apos;s horizon and cannot be drawn
          here. Cancel and use the counter-offer dialog on the queue row to reach those.
        </p>
      ) : null}

      {chosen ? (
        <div className="flex flex-col gap-3 border-t border-info-border pt-2">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-body text-info-fg">
              Chosen:{' '}
              <span translate="no" className="font-mono tabular-nums">
                {chosen.dock_code} · {chosen.slot_local_date} · {formatTime(chosen.slot_start_ts)}–
                {formatTime(chosen.slot_end_ts)}
              </span>
            </span>
            <Button variant="ghost" size="sm" onClick={onClearChoice} disabled={busy}>
              Pick a different interval
            </Button>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-label text-subtle-foreground uppercase">Reason</legend>
            {/* Same five codes as reject -- `COUNTER_OFFER_REASON_CODES = REJECTION_REASON_CODES`
                in the service, flagged there as an assumption and so flagged here too. */}
            <RadioGroup
              value={reason ?? undefined}
              onValueChange={(v) => onReasonChange(v as RejectReasonCode)}
              className="grid grid-cols-2 gap-2"
            >
              {REJECT_REASON_CODES.map((code) => (
                <div key={code} className="flex min-h-8 items-center gap-2">
                  <RadioGroupItem value={code} id={`picker-r-${code}`} />
                  <Label htmlFor={`picker-r-${code}`} className="cursor-pointer text-body">
                    {REASON_LABELS[code]}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </fieldset>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="picker-note" className="text-label text-subtle-foreground uppercase">
              Internal note <span className="normal-case">(never shown to the driver)</span>
            </Label>
            <textarea
              id="picker-note"
              value={note}
              onChange={(e) => onNoteChange(e.target.value)}
              maxLength={500}
              rows={2}
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
          </div>

          <p className="text-micro text-info-fg">
            The offered interval is <strong>reserved</strong>, not merely shown — the appointment
            moves to it and stays pending the driver&apos;s reply, so nobody else can take it in the
            meantime.
          </p>

          {error ? <Alert variant="danger">{error}</Alert> : null}

          <div className="flex items-center gap-2">
            <Button
              variant="constructive"
              aria-disabled={!canSend}
              title={reason === null ? 'Choose a reason first.' : undefined}
              onClick={() => {
                if (!canSend) return
                onSubmit()
              }}
            >
              {busy ? 'Sending…' : 'Send counter-offer'}
            </Button>
          </div>
        </div>
      ) : error ? (
        // A refusal that cleared the choice (INTERVAL_UNAVAILABLE re-fetches and drops it) still
        // has to be readable, so the error survives losing the selection.
        <Alert variant="danger">{error}</Alert>
      ) : null}
    </section>
  )
}
