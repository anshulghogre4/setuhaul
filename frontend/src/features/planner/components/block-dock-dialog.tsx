import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { CircleAlert } from 'lucide-react'

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
import { formatUserFriendlyError } from '@/core/http/api'
import { blockDock, fetchDockBlockImpact, fetchDocksForFacility } from '../lib/api'
import type { ConflictingEvent, Dock, DockBlockImpact } from '../lib/types'

/**
 * `screens.md` section 5 / `components.md` section 6 (states 16-18). The one write path this
 * pass ships unconditionally -- `block_dock`, `end_dock_block` and `get_dock_block_impact` are
 * all fully shipped in E3.6 (`implementation-spec.md` section 0.1), and this is the only group
 * with a complete backend, so it carries no feature flag.
 *
 * **Fork G, resolved (a): native form controls, not the mockup's `<div role="combobox">`
 * pattern.** `<select>` / `<input type="time">` / `<textarea>` are used throughout -- native
 * `<input type="time">` gets 24-hour behaviour and keyboard entry for free, which `screens.md`
 * section 5 asks for explicitly, and the mockup's own `role="textbox" aria-readonly` divs cannot
 * fire the field-change events Flow 7 step 2's live affected-appointment fetch depends on.
 *
 * **No date field.** `stitch-prompts.md` section 10's own layout has only DOCK / FROM / TO /
 * REASON -- "this is a single operating day, two time fields" -- and explicitly excludes a
 * calendar/date-range widget. There is no board date context yet (the Board tab's "at rest" view
 * is gated behind `dockBoardEnabled`, issue #53), so the window is built against the browser's
 * local today. `Source: inferred, not in a design file` -- flagged rather than silently assumed.
 */
export function BlockDockDialog({
  open,
  onOpenChange,
  facilityId,
  onBlocked,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  facilityId: string
  onBlocked: (dockCode: string) => void
}) {
  const [docks, setDocks] = useState<Dock[]>([])
  const [docksError, setDocksError] = useState(false)
  const [dockId, setDockId] = useState('')
  const [fromTime, setFromTime] = useState('')
  const [toTime, setToTime] = useState('')
  const [reason, setReason] = useState('')
  const [timeError, setTimeError] = useState<string | null>(null)
  const [touchedTimes, setTouchedTimes] = useState(false)

  const [impact, setImpact] = useState<DockBlockImpact | null>(null)
  /** `components.md` section 6: "checked, none" and "not yet checked" are different facts
   *  (state 17) -- `checkedForCurrentFields` is what keeps the two distinct, and what
   *  `[ Block dock ]` waits on before it will submit. Reset to false on every field edit. */
  const [checkStatus, setCheckStatus] = useState<'idle' | 'checking' | 'checked' | 'error'>('idle')
  const [checkedForCurrentFields, setCheckedForCurrentFields] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [alreadyBlocked, setAlreadyBlocked] = useState<ConflictingEvent | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const dockSelectRef = useRef<HTMLSelectElement | null>(null)
  const titleId = useId()

  // Focus management (accessibility.md): opens with focus on the Dock select -- the first
  // interactive element, never the submit button. Resets all field state on open so a second
  // open never carries a stale window from a previous block.
  useEffect(() => {
    if (!open) return
    setDockId('')
    setFromTime('')
    setToTime('')
    setReason('')
    setTimeError(null)
    setTouchedTimes(false)
    setImpact(null)
    setCheckStatus('idle')
    setCheckedForCurrentFields(false)
    setSubmitting(false)
    setAlreadyBlocked(null)
    setSubmitError(null)
    setDocksError(false)
    fetchDocksForFacility(facilityId)
      .then(setDocks)
      .catch(() => setDocksError(true))
    requestAnimationFrame(() => dockSelectRef.current?.focus())
  }, [open, facilityId])

  const windowValid = dockId !== '' && fromTime !== '' && toTime !== '' && timeError === null

  // Flow 7 step 2: the affected-appointment set fetches live as the dock/time fields complete,
  // "not deferred to submission" -- a short debounce so it does not fire on every keystroke of a
  // still-being-typed time value.
  useEffect(() => {
    setCheckedForCurrentFields(false)
    if (!windowValid) {
      setCheckStatus('idle')
      setImpact(null)
      return
    }
    setCheckStatus('checking')
    const [startIso, endIso] = toIsoWindow(fromTime, toTime)
    const handle = window.setTimeout(() => {
      fetchDockBlockImpact(dockId, startIso, endIso)
        .then((res) => {
          setImpact(res)
          setCheckStatus('checked')
          setCheckedForCurrentFields(true)
        })
        .catch(() => {
          setCheckStatus('error')
        })
    }, 350)
    return () => window.clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- toIsoWindow is a pure helper
  }, [dockId, fromTime, toTime, windowValid])

  function validateTimesOnBlur() {
    setTouchedTimes(true)
    if (fromTime === '' || toTime === '') {
      setTimeError(null)
      return
    }
    setTimeError(toTime <= fromTime ? 'End time must be after start time.' : null)
  }

  async function handleSubmit() {
    if (!windowValid || !checkedForCurrentFields || reason.trim() === '' || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    setAlreadyBlocked(null)
    try {
      const [startIso, endIso] = toIsoWindow(fromTime, toTime)
      const result = await blockDock(dockId, { window_start: startIso, window_end: endIso, reason: reason.trim() })
      if (result.code === 'ALREADY_BLOCKED') {
        // The form STAYS OPEN and names the conflicting block (screens.md section 5's error
        // variant) -- field values are preserved so the planner can adjust rather than re-enter.
        setAlreadyBlocked(result.conflicting_event)
      } else {
        const dock = docks.find((d) => d.dock_id === dockId)
        onBlocked(dock?.dock_code ?? dockId)
        onOpenChange(false)
      }
    } catch (err) {
      // Nothing has changed -- the mandatory phrase for a failed write (stitch-prompts.md section 12).
      setSubmitError(`${formatUserFriendlyError(err)} Nothing has changed.`)
    } finally {
      setSubmitting(false)
    }
  }

  const submitDisabled = !windowValid || !checkedForCurrentFields || reason.trim() === '' || submitting
  const submitTitle = !windowValid
    ? 'Fill in the dock, start and end time first.'
    : checkStatus === 'checking'
      ? 'Checking which appointments this affects…'
      : reason.trim() === ''
        ? 'A reason is required.'
        : undefined

  return (
    <Dialog open={open} onOpenChange={(next) => !submitting && onOpenChange(next)}>
      <DialogContent aria-labelledby={titleId} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle id={titleId}>Block a dock</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <Field label="Dock" htmlFor={`${titleId}-dock`}>
            <select
              id={`${titleId}-dock`}
              ref={dockSelectRef}
              value={dockId}
              onChange={(e) => setDockId(e.target.value)}
              disabled={docksError}
              className="h-11 w-full rounded-md border border-input bg-card px-3 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <option value="" disabled>
                {docksError ? "Couldn't load docks" : 'Select a dock…'}
              </option>
              {docks.map((d) => (
                <option key={d.dock_id} value={d.dock_id}>
                  {d.dock_code} ({dockTypeLabel(d.dock_type)})
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="From" htmlFor={`${titleId}-from`}>
              <input
                id={`${titleId}-from`}
                type="time"
                value={fromTime}
                onChange={(e) => setFromTime(e.target.value)}
                onBlur={validateTimesOnBlur}
                aria-invalid={touchedTimes && timeError !== null}
                aria-describedby={timeError ? `${titleId}-time-error` : undefined}
                className="h-11 w-full rounded-md border border-input bg-card px-3 font-data text-body tabular-nums outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 aria-invalid:border-danger-border"
              />
            </Field>
            <Field label="To" htmlFor={`${titleId}-to`}>
              <input
                id={`${titleId}-to`}
                type="time"
                value={toTime}
                onChange={(e) => setToTime(e.target.value)}
                onBlur={validateTimesOnBlur}
                aria-invalid={touchedTimes && timeError !== null}
                aria-describedby={timeError ? `${titleId}-time-error` : undefined}
                className="h-11 w-full rounded-md border border-input bg-card px-3 font-data text-body tabular-nums outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2 aria-invalid:border-danger-border"
              />
            </Field>
          </div>
          {timeError ? (
            <p id={`${titleId}-time-error`} className="-mt-2 flex items-center gap-1.5 text-supporting text-danger-fg">
              <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              {timeError}
            </p>
          ) : null}

          <Field label="Reason" htmlFor={`${titleId}-reason`}>
            <textarea
              id={`${titleId}-reason`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Leveller failure…"
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-body text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            />
          </Field>

          <ImpactBlock status={checkStatus} impact={impact} />

          {alreadyBlocked ? (
            <Alert variant="danger">
              {dockLabelFor(docks, dockId)} is already blocked {formatEventWindow(alreadyBlocked)} for “
              {alreadyBlocked.reason ?? 'no reason given'}”. Adjust your window, or end that block first.
            </Alert>
          ) : null}
          {submitError ? <Alert variant="danger">{submitError}</Alert> : null}
        </div>

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="cautionary"
            aria-disabled={submitDisabled}
            title={submitTitle}
            onClick={() => {
              if (submitDisabled) return
              void handleSubmit()
            }}
          >
            {submitting ? 'Blocking…' : 'Block dock'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={htmlFor} className="text-label uppercase text-subtle-foreground">
        {label}
      </Label>
      {children}
    </div>
  )
}

/**
 * State 17: "checked, none" and "not checked yet" are different facts and must look different.
 * `checking` and `error` both render a neutral in-flight/failed line -- the warning or the plain
 * "none" line only appears once `checked` genuinely reflects the current fields.
 */
function ImpactBlock({
  status,
  impact,
}: {
  status: 'idle' | 'checking' | 'checked' | 'error'
  impact: DockBlockImpact | null
}) {
  if (status === 'idle') return null
  if (status === 'checking') {
    return (
      <p aria-live="polite" className="text-supporting text-subtle-foreground">
        Checking which appointments this affects…
      </p>
    )
  }
  if (status === 'error') {
    return <Alert variant="danger">Couldn't check affected appointments. Try changing a field to re-check.</Alert>
  }
  if (!impact || impact.affected_count === 0) {
    return <p className="text-supporting text-muted-foreground">No confirmed appointments in this window.</p>
  }
  return (
    <Alert variant="warning">
      {impact.affected_count} confirmed appointment{impact.affected_count === 1 ? '' : 's'} fall inside this
      window — {impact.affected_appointments.map((a) => a.shipment_id).join(', ')}. Blocking will escalate{' '}
      {impact.affected_count === 1 ? 'it' : 'both'} as a capacity incident.
    </Alert>
  )
}

function dockTypeLabel(type: Dock['dock_type']): string {
  switch (type) {
    case 'REEFER':
      return 'Reefer'
    case 'HEAVY':
      return 'Heavy'
    default:
      return 'Standard'
  }
}

function dockLabelFor(docks: Dock[], dockId: string): string {
  return docks.find((d) => d.dock_id === dockId)?.dock_code ?? dockId
}

function formatEventWindow(event: ConflictingEvent): string {
  const start = new Date(event.event_start_ts)
  const end = event.event_end_ts ? new Date(event.event_end_ts) : null
  const fmt = (d: Date) => d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
  return end ? `${fmt(start)}–${fmt(end)}` : `from ${fmt(start)}`
}

/** Combines today's local date with an `HH:mm` field into a UTC ISO pair the backend's
 *  `_coerce_ts` (planner_service.py) accepts directly. `Source: inferred` -- see this file's own
 *  header comment on why there is no date field to read from instead. */
function toIsoWindow(fromTime: string, toTime: string): [string, string] {
  const today = new Date()
  const [fh, fm] = fromTime.split(':').map(Number)
  const [th, tm] = toTime.split(':').map(Number)
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate(), fh, fm)
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate(), th, tm)
  return [start.toISOString(), end.toISOString()]
}
