import { ArrowLeft, ShieldOff } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'
import { PromiseChip } from '@/features/driver/components/promise-chip'
import { RegionFailedBlock } from '../components/blocks'
import { fetchShipmentDetail, isOutOfScope } from '../lib/api'
import { carrierShownHeldEnabled } from '../lib/flags'
import { formatDockLine, formatTime } from '../lib/format'
import { historyLabel } from '../lib/history'
import { promiseCell } from '../lib/promise'
import type { ShipmentDetail as ShipmentDetailPayload } from '../lib/types'

/**
 * Shipment detail, read-only — `screens.md` §2, `stitch-prompts.md` §8,
 * `05-carrier-portal/components.md` §4.
 *
 * ## Read-only is structural here, not a rendering choice
 *
 * **No Confirm, Reject, Counter-offer, Hold-for-information, Escalate, Reschedule, Cancel or
 * Approve — not even greyed out.** §7.5.6 has no mutating tool for this role at all
 * (`carrier.py` is five `@router.get`s and zero POST/PATCH/DELETE), and `components.md` §18
 * requires an unavailable control to be **Hidden**, never Disabled: a greyed-out Confirm would
 * misrepresent what this surface can do. This screen reuses the planner's *chip*, not the
 * planner's *context*.
 *
 * Equally: **no client-side scope check anywhere in this file.** `get_shipment_detail` refuses a
 * cross-carrier id server-side — `get_fleet_shipment` scopes the query itself so another
 * carrier's row is never read into the process, and `assert_shipment_in_carrier_fleet` turns
 * "no row" into a 403. Adding a second guard here would look like the real one while protecting
 * nothing. The client renders what the server returns, and renders the refusal when the server
 * refuses.
 *
 * ## The refusal must not be able to answer "does this shipment exist?"
 *
 * `edge-cases.md` #1: a shipment that does not exist and one belonging to another carrier
 * produce the **identical** response — same status, same code, same message — so the screen
 * cannot be used to probe for which shipments are real. The copy says the shipment *isn't in
 * your fleet*; it does not say "not found", "deleted", or "belongs to someone else", and **the
 * requested id is never echoed back**, because repeating it invites the reading that the system
 * looked it up and found something.
 *
 * ## One designed element that has no data behind it (reported, not faked)
 *
 * `stitch-prompts.md` §8 gives `PENDING CONFIRMATION` a deadline line — `Decision by 11:57.`
 * **There is no deadline field on this payload, and none in the schema**: `public.appointments`
 * has no `expires_at`/deadline column, and `backend/app/scheduling/expiry.py:75-81` states in
 * its own comment that D9's 15-minute deadline is *derived* as `booked_at + ttl` server-side and
 * deliberately never stored. Deriving it here would mean hardcoding a backend policy constant
 * into the frontend, where nothing would keep the two in step. Prompt 8's own wording — "deadline
 * line (**only where one exists**)" — is followed literally: the line is omitted, and the gap is
 * reported so `get_shipment_detail` can return the deadline it already knows how to compute.
 */

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; payload: ShipmentDetailPayload }
  /** The designed out-of-scope screen. Never distinguishes missing from cross-carrier. */
  | { kind: 'refused' }
  /** Anything else — a network fault, a 500. Not a scope statement. */
  | { kind: 'failed' }

export function CarrierShipmentDetail({ onOpened }: { onOpened: (shipmentId: string) => void }) {
  const { shipmentId = '' } = useParams()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const headingRef = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    onOpened(shipmentId)
  }, [shipmentId, onOpened])

  useEffect(() => {
    let live = true
    const ac = new AbortController()
    setState({ kind: 'loading' })
    fetchShipmentDetail(shipmentId, ac.signal)
      .then((payload) => {
        if (live) setState({ kind: 'ready', payload })
      })
      .catch((err: unknown) => {
        if (!live || ac.signal.aborted) return
        setState({ kind: isOutOfScope(err) ? 'refused' : 'failed' })
      })
    return () => {
      live = false
      ac.abort()
    }
  }, [shipmentId])

  // `accessibility.md` focus management: opening this screen focuses **the screen's own
  // heading**, which is also the assertive announcement target for the refusal state.
  useEffect(() => {
    if (state.kind !== 'loading') headingRef.current?.focus()
  }, [state.kind])

  if (state.kind === 'refused') return <CarrierOutOfScope headingRef={headingRef} />

  return (
    <div className="mx-auto w-full max-w-[688px]">
      <Link
        to="/carrier"
        className="inline-flex min-h-11 items-center gap-1.5 text-body text-subtle-foreground no-underline outline-none hover:underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <ArrowLeft className="size-4" aria-hidden="true" strokeWidth={2} />
        Dashboard
      </Link>

      {state.kind === 'loading' ? (
        <DetailSkeleton />
      ) : state.kind === 'failed' ? (
        <div className="mt-3 rounded-lg border border-border bg-card shadow-raised">
          {/* Deliberately NOT the out-of-scope copy. A connection fault is not a statement about
              who this shipment belongs to, and conflating the two would either accuse the server
              of refusing or reassure a carrier that the shipment is theirs when nobody knows. */}
          <RegionFailedBlock what="shipment" onRetry={() => setState({ kind: 'loading' })} />
        </div>
      ) : (
        <CarrierDetailCard payload={state.payload} headingRef={headingRef} />
      )}
    </div>
  )
}

/** Exported for the states gallery, which renders all four promise variants side by side —
 *  including the two that are flag-gated off in the live route, so they can be reviewed without
 *  flipping the flag. */
export function CarrierDetailCard({
  payload,
  headingRef,
  shownHeldEnabled = carrierShownHeldEnabled,
}: {
  payload: ShipmentDetailPayload
  headingRef?: React.RefObject<HTMLHeadingElement | null>
  shownHeldEnabled?: boolean
}) {
  const s = payload.shipment
  const cell = promiseCell(s.promise_state, shownHeldEnabled)
  const dockLine = formatDockLine({
    facilityName: s.facility_name,
    dockCode: s.dock_code,
    slotStart: s.slot_start_ts,
    slotEnd: s.slot_end_ts,
  })

  return (
    <div className="mt-3 rounded-lg border border-border bg-card p-5 shadow-raised">
      <h1 ref={headingRef} tabIndex={-1} className="mb-3 text-h2 outline-none">
        <span className="font-mono">{s.shipment_id}</span> · {s.driver_name}
      </h1>

      {cell.kind === 'chip' ? <PromiseChip state={cell.state} /> : null}
      {cell.kind === 'plain' ? (
        <p className="text-body text-muted-foreground">{cell.label}</p>
      ) : null}
      {cell.kind === 'none' ? (
        // Fork A's undesigned case, rendered honestly. No `SHOWN` chip: the system does not know
        // this shipment has been shown anything, and until #53 lands it structurally cannot.
        <p className="text-supporting text-muted-foreground">No appointment yet.</p>
      ) : null}

      {/* Supporting lines, verbatim from prompt 8. `CONFIRMED` is the only state permitted
          finality language, so nothing below it says booked / reserved / secured / your slot. */}
      {cell.kind === 'chip' && cell.state === 'PENDING_CONFIRMATION' ? (
        <p className="mt-2 text-supporting text-muted-foreground">
          The warehouse hasn&rsquo;t confirmed this yet.
        </p>
      ) : null}
      {cell.kind === 'chip' && cell.state === 'SHOWN' ? (
        <p className="mt-2 text-supporting text-muted-foreground">Nothing is held yet.</p>
      ) : null}
      {/* Prompt 8's HELD line is `Held for the driver until 11:42:30. This is not a booking
          yet.` The timestamp half has no field to render from — the same missing-deadline gap as
          `PENDING`'s, and doubly so here, since a hold has no row to hang an expiry on at all
          until #53 lands. The sentence that does not depend on a value is kept; the one that does
          is dropped rather than invented. Unreachable while the flag is off. */}
      {cell.kind === 'chip' && cell.state === 'HELD' ? (
        <p className="mt-2 text-supporting text-muted-foreground">
          Held for the driver. This is not a booking yet.
        </p>
      ) : null}

      {/* `Jaipur · D5 · Tue 20 Aug · 13:00–14:15` -- mandatory in this exact shape. An
          operational time never appears without its dock and its date, because an option set can
          span two days and a bare time is a wrong-day arrival waiting to happen. */}
      {dockLine ? (
        <p className="my-3 font-mono text-body text-muted-foreground" data-numeric>
          {dockLine}
        </p>
      ) : null}

      {/* Only `CONFIRMED` carries a reference. `warehouse_confirmation_ref` is not in this
          payload's projection, so the appointment id is the reference this surface can actually
          show -- named plainly rather than dressed up as something it is not. */}
      {cell.kind === 'chip' && cell.state === 'CONFIRMED' && s.appointment_id ? (
        <p className="mt-2 font-mono text-body text-muted-foreground">
          Reference {s.appointment_id}
        </p>
      ) : null}

      <h2 className="mt-4 text-label text-subtle-foreground uppercase">History</h2>
      {payload.history.length === 0 ? (
        <p className="mt-2 text-supporting text-muted-foreground">Nothing recorded yet.</p>
      ) : (
        <ul className="mt-1 list-none p-0">
          {payload.history.map((entry, i) => (
            <li
              key={`${entry.event_type}-${entry.occurred_at}-${i}`}
              className="flex gap-3 border-t border-border py-2 text-supporting"
            >
              <span className="w-14 shrink-0 font-mono tabular-nums text-subtle-foreground" data-numeric>
                {formatTime(entry.occurred_at) ?? '—'}
              </span>
              <span>{historyLabel(entry)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * `stitch-prompts.md` §9 / `mockup.html` state 13.
 *
 * The block sits directly on the page ground — **no card, no shadow**: this is a full-region
 * state, not a component in a container. No mono type anywhere on it and no shipment id echoed
 * back. No search box offering to look the shipment up another way, which would be the same
 * disclosure through a different door. No "request access", no 404 numeral, no illustration.
 */
export function CarrierOutOfScope({
  headingRef,
}: {
  headingRef?: React.RefObject<HTMLHeadingElement | null>
}) {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-90 items-center justify-center">
      {/* Assertive: this is both a route change and an unsuccessful action
          (`accessibility.md`'s announcement table). */}
      <div role="alert" className="w-100 text-center">
        <ShieldOff
          className="mx-auto size-8 text-subtle-foreground"
          aria-hidden="true"
          strokeWidth={2}
        />
        <h1 ref={headingRef} tabIndex={-1} className="mt-6 text-h3 outline-none">
          This shipment isn&rsquo;t in your fleet
        </h1>
        <p className="mt-2 text-supporting text-muted-foreground">
          Check the link, or go back to your dashboard.
        </p>
        <Button type="button" variant="neutral" className="mt-6" onClick={() => navigate('/carrier')}>
          Back to dashboard
        </Button>
      </div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="mt-3 rounded-lg border border-border bg-card p-5 shadow-raised" aria-hidden="true">
      <Skeleton className="h-6 w-64 rounded-sm" />
      <Skeleton className="mt-4 h-7 w-48 rounded-sm" />
      <Skeleton className="mt-4 h-4 w-72 rounded-sm" />
      <Skeleton className="mt-6 h-3 w-20 rounded-sm" />
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="mt-3 h-4 w-56 rounded-sm" />
      ))}
    </div>
  )
}
