import { CircleCheckBig, Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { useCountdownClock } from '@/shared/lib/countdown'
import { useTheme } from '@/shared/lib/theme'
import { Composer } from '../components/composer'
import {
  EligibilityAnswerError,
  EligibilityAnswerPart,
  EligibilityAnswerSkeleton,
} from '../components/eligibility-answer'
import { DriverMessageRow } from '../components/message'
import { MessageParts } from '../components/message-parts'
import { OptionCard } from '../components/option-card'
import { OptionSetPart } from '../components/option-set'
import { PromiseChip } from '../components/promise-chip'
import { ScrollToLatest } from '../components/scroll-to-latest'
import { StateLine } from '../components/state-line'
import { ThinkingIndicator, ThreadListSkeleton, TranscriptSkeleton } from '../components/thinking'
import { ThreadCard } from '../components/thread-card'
import { DriverPushDenied, DriverPushPriming } from '../screens/push-priming'
import { copy } from '../lib/copy'
import { heldStateEnabled } from '../lib/flags'
import {
  BAND_EXPIRED,
  BAND_FINAL,
  BAND_MID,
  BAND_REST,
  BAND_URGENT,
  ELIGIBILITY_FAIL,
  ELIGIBILITY_PASS,
  ESCALATED_SET,
  FEASIBLE_SET,
  HELD_EXPIRED,
  HELD_FINAL,
  HELD_MID,
  OPTIONS,
  PENDING_LIVE,
  TAKEOVER_TRANSCRIPT,
  THREADS,
  TOMORROW_SET,
  TRANSCRIPT,
} from './fixtures'
import type { DriverMessage } from '../lib/types'

/**
 * Every driver-chat screen and state, rendered by the **built components** rather than by the
 * reference markup. Route `/driver/_states`. Not linked from the app.
 *
 * This exists for the same reason E5.0's `/_states` does: *"it type-checks and looks plausible
 * in code" is not the same as "it has been seen working"*. This surface specifically has four
 * defects (R2–R5) that are **invisible in markup and only appear ~37 seconds into a live
 * render** — the 20–50% band never firing, the expiry state never rendering, the chip and the
 * option card disagreeing on urgency, and a caption claiming a pulse that had no keyframe. The
 * live-hold plates below exist so those four are observable, and the spec is explicit that they
 * are **regression tests, not one-off fixes**.
 *
 * The `HELD` plates render only when `heldStateEnabled` is on. **They render now** -- the flag went
 * on 2026-08-31, once the D2 migration was applied, `TWO_PHASE_HOLD_ENABLED` defaulted true and the
 * consuming reads (#83/#86) landed. The gated branch is kept rather than deleted so a revert is one
 * line, and so the plates still state why they are absent instead of silently looking complete.
 */
export function DriverStatesGallery() {
  const { choice, setChoice, resolved } = useTheme()
  const { now } = useCountdownClock()

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="mx-auto max-w-320 px-6 pt-10 pb-4">
        <p className="text-label uppercase text-primary">SetuHaul · driver chat (E5.1)</p>
        <h1 className="mt-2 text-display text-balance">
          28 screens, rendered from the built components
        </h1>
        <p className="mt-2 max-w-[70ch] text-body text-muted-foreground">
          All 28 render. The four <code className="font-mono">HELD</code> plates sit behind{' '}
          <code className="font-mono">heldStateEnabled</code>, which went on 2026-08-31: the D2
          migration is applied, <code className="font-mono">TWO_PHASE_HOLD_ENABLED</code> defaults
          true, <code className="font-mono">confirm_held_slot</code> is bound, and the driver reads
          return a real <code className="font-mono">current_hold</code> with a server-computed
          deadline. The live-hold plates run a real countdown; watch one for a minute rather than
          reading it.
        </p>
        <div className="mt-4 flex items-center gap-3">
          <Button variant="neutral" onClick={() => setChoice(resolved === 'dark' ? 'light' : 'dark')}>
            Switch to {resolved === 'dark' ? 'light' : 'dark'}
          </Button>
          <span className="text-body text-subtle-foreground">
            stored choice: <span className="font-mono">{choice}</span> · flag:{' '}
            <span className="font-mono">{String(heldStateEnabled)}</span>
          </span>
        </div>
      </header>

      <div className="mx-auto grid max-w-320 grid-cols-[repeat(auto-fill,minmax(390px,1fr))] gap-6 p-6">
        {/* ---- A · Thread list -------------------------------------------------------- */}
        <Plate n="1" title="Thread list — home">
          <ul role="list" className="flex flex-col gap-3 p-4">
            {THREADS.map((t) => (
              <ThreadCard key={t.threadId} thread={t} />
            ))}
          </ul>
        </Plate>

        <Plate n="2" title="Thread list — loading">
          <ThreadListSkeleton />
        </Plate>

        <Plate n="3A" title="Empty — caught up (no CTA, U74)">
          <EmptyState
            icon={CircleCheckBig}
            title={copy.emptyCaughtUpTitle}
            body={copy.emptyCaughtUpBody}
          />
        </Plate>

        <Plate n="3B" title="Empty — nothing yet (distinct icon AND copy)">
          <EmptyState
            icon={Inbox}
            title={copy.emptyNothingYetTitle}
            body={copy.emptyNothingYetBody}
          />
        </Plate>

        {/* ---- B · The promise states ------------------------------------------------- */}
        <Plate n="4" title="Conversation — SHOWN">
          <StateLine state="SHOWN" />
          <Log>
            {TRANSCRIPT.map((m) => (
              <Row key={m.id} m={m} nowMs={now} />
            ))}
          </Log>
        </Plate>

        <Plate n="5" title="HELD — 90s live (mid band, then <20% pulse)">
          {heldStateEnabled ? (
            <>
              <StateLine state="HELD" expiresAt={HELD_MID} operationalLine="Dock D1 · Tue 4 Aug" />
              <div className="p-4">
                <PromiseChip state="HELD" expiresAt={HELD_MID} />
                <div className="mt-3">
                  <PromiseChip state="HELD" expiresAt={HELD_FINAL} />
                </div>
                <div className="mt-3">
                  <PromiseChip state="HELD" expiresAt={HELD_EXPIRED} />
                </div>
                <div className="mt-4">
                  <OptionCard option={OPTIONS[1]} state="held" heldUntil={HELD_FINAL} />
                  {/* R6: the SIBLINGS of a held card are plain and selectable. Not `dead`. */}
                  <OptionCard option={OPTIONS[0]} />
                  <OptionCard option={OPTIONS[2]} />
                </div>
              </div>
            </>
          ) : (
            <Gated />
          )}
        </Plate>

        {/* Ungated regression plate for R2/R3/R4 -- see the fixtures' own comment on why it uses
            PENDING rather than HELD. `data-band` is the measurement hook: a probe reads the
            computed colour and weight of each numeric and asserts the band, rather than a human
            eyeballing four ambers. */}
        <Plate n="R" title="Countdown bands — R2/R3/R4 regression (ungated)">
          <div className="space-y-4 p-4">
            {(
              [
                ['rest 70%', BAND_REST],
                ['mid 40% — amber-600', BAND_MID],
                ['urgent 15% — red, weight 600', BAND_URGENT],
                ['final 8s', BAND_FINAL],
                ['expired — replaced in place', BAND_EXPIRED],
              ] as const
            ).map(([label, expiresAt]) => (
              <div key={label} data-band={label} className="flex flex-col gap-1">
                <span className="text-body text-subtle-foreground">{label}</span>
                <PromiseChip state="PENDING_CONFIRMATION" expiresAt={expiresAt} />
              </div>
            ))}
          </div>
        </Plate>

        <Plate n="6" title="PENDING CONFIRMATION — 15 min (no quick replies)">
          <StateLine
            state="PENDING_CONFIRMATION"
            expiresAt={PENDING_LIVE}
            operationalLine="Dock D1 · Tue 4 Aug · 13:00 – 14:15"
          />
          <div className="p-4">
            <PromiseChip state="PENDING_CONFIRMATION" expiresAt={PENDING_LIVE} />
          </div>
        </Plate>

        <Plate n="7" title="CONFIRMED — the only screen allowed finality language">
          <StateLine
            state="CONFIRMED"
            operationalLine="Dock D1 · Tue 4 Aug · 13:00 – 14:15"
          />
          <div className="space-y-2 p-4">
            <PromiseChip state="CONFIRMED" />
            <p className="text-body-lg">{copy.confirmedArrival('12:00', 60)}</p>
            <p className="text-body">{copy.confirmedNoShow('13:30')}</p>
            <p className="font-mono text-body text-muted-foreground">
              {copy.confirmedReference('APT-1042')}
            </p>
          </div>
        </Plate>

        {/* ---- C · Transcript mechanics ------------------------------------------------ */}
        <Plate n="8" title="Message tiers + permanent takeover divider">
          <Log>
            {TAKEOVER_TRANSCRIPT.map((m) => (
              <Row key={m.id} m={m} nowMs={now} />
            ))}
          </Log>
        </Plate>

        <Plate n="9" title="Option card — the full state matrix">
          <div className="space-y-2 p-4">
            <OptionCard option={OPTIONS[0]} state="default" />
            <OptionCard option={OPTIONS[0]} state="committing" />
            {heldStateEnabled ? (
              <>
                <OptionCard option={OPTIONS[1]} state="held" heldUntil={HELD_MID} />
                {/* Screen 15's card treatment, in the matrix beside the state it comes from: the
                    dashed amber is gone, the lines are struck, and the status line names the
                    reason -- distinguishable from `lost`, which is a different fact. */}
                <OptionCard option={OPTIONS[1]} state="lapsed" />
              </>
            ) : (
              <p className="text-body text-muted-foreground">
                Held and lapsed columns gated behind heldStateEnabled.
              </p>
            )}
            <OptionCard option={OPTIONS[1]} state="lost" />
            <OptionCard option={OPTIONS[1]} state="withdrawn" />
            <OptionCard option={OPTIONS[2]} state="offline" />
            <OptionCard option={OPTIONS[2]} state="superseded" />
          </div>
        </Plate>

        <Plate n="10A" title="Composer + quick replies">
          <div className="flex-1" />
          <Composer quickReplies={['Yes, 11:00', 'Another hour']} onSend={() => {}} />
        </Plate>

        <Plate n="10B" title="Composer — offline (never disabled)">
          <div className="flex-1" />
          <Composer offline onSend={() => {}} />
        </Plate>

        <Plate n="11A" title="Assistant thinking (400ms → dots, 8s → still working)">
          <Log>
            <ThinkingIndicator startedAtMs={now - 9000} nowMs={now} />
          </Log>
        </Plate>

        <Plate n="11B" title="Transcript skeleton — 3 alternating shapes">
          <TranscriptSkeleton />
        </Plate>

        <Plate n="11C" title="Scroll to latest — counts messages, not events">
          <div className="relative flex-1">
            <ScrollToLatest newCount={2} onClick={() => {}} />
          </div>
        </Plate>

        {/* ---- D · Read-only answers --------------------------------------------------- */}
        <Plate n="12A" title="Eligibility — passes (passing rows stay neutral)">
          <div className="p-4">
            <EligibilityAnswerPart answer={ELIGIBILITY_PASS} />
          </div>
        </Plate>

        <Plate n="12B" title="Eligibility — fails (only the failing row is red)">
          <div className="p-4">
            <EligibilityAnswerPart answer={ELIGIBILITY_FAIL} />
          </div>
        </Plate>

        <Plate n="12C" title="Eligibility — loading (skeleton rows) and tool error">
          <div className="p-4">
            <EligibilityAnswerSkeleton rows={4} />
            <EligibilityAnswerError />
          </div>
        </Plate>

        <Plate n="14A" title="Push priming — with a real notification preview (F4)">
          <DriverPushPriming />
        </Plate>

        <Plate n="14B" title="Push denied — consequence stated once">
          <DriverPushDenied />
        </Plate>

        {/* ---- E · The negative paths — the real product ------------------------------- */}
        <Plate n="15" title="Hold lapsed — card mutates IN PLACE">
          {heldStateEnabled ? (
            <div className="p-4">
              {/* `lapsed`, not `withdrawn`. They looked alike before this state existed, and the
                  difference is the whole signal: "No longer available" describes a dock going out
                  of service, "Hold lapsed" describes 90 seconds passing. */}
              <OptionCard option={OPTIONS[1]} state="lapsed" />
              <Notice
                body={copy.holdLapsed('Dock D1 · 13:00–14:15')}
                action={copy.findOptionsAgainAction}
              />
            </div>
          ) : (
            <Gated />
          )}
        </Plate>

        <Plate n="16A" title="Pending expired — names the release AND the escalation">
          <div className="p-4">
            <Notice
              body={copy.pendingExpired('Dock D1 · 13:00–14:15')}
              action={copy.findOptionsAgainAction}
            />
          </div>
        </Plate>

        <Plate n="17" title="Lost the race — never blames the driver, no penalty haptic">
          <div className="p-4">
            <OptionCard option={OPTIONS[1]} state="lost" />
            <Notice body={copy.slotConflict('Dock D1 · 13:00–14:15')} />
            <OptionSetPart set={FEASIBLE_SET} />
          </div>
        </Plate>

        <Plate n="18" title="Option withdrawn — ONLY the affected card mutates (U50)">
          <div className="p-4">
            <OptionSetPart
              set={{ ...FEASIBLE_SET, perOption: { [OPTIONS[0].slotId]: 'withdrawn' } }}
            />
            <Notice body={copy.optionWithdrawn('D5', '18:00', 2)} />
          </div>
        </Plate>

        <Plate n="19" title="No same-day slot — NOT an escalation, the date is load-bearing">
          <div className="p-4">
            <OptionSetPart
              set={TOMORROW_SET}
              facilityName="Jaipur DC"
              blockingReason="the reefer dock is down for maintenance until 22:00 and the site closes then"
            />
          </div>
        </Plate>

        <Plate n="20" title="No feasible slot → escalation. No cards, no retry">
          <div className="p-4">
            <p className="text-body-lg">
              {copy.noFeasibleSlot(
                'Jaipur DC',
                'the only reefer dock is out of service past your arrival time, and there’s nothing tomorrow either',
                'ESC-4471',
              )}
            </p>
            <OptionSetPart set={ESCALATED_SET} />
          </div>
        </Plate>

        <Plate n="21" title="Human takeover — permanent divider, heavier border">
          <Log>
            {TAKEOVER_TRANSCRIPT.slice(2).map((m) => (
              <Row key={m.id} m={m} nowMs={now} />
            ))}
          </Log>
        </Plate>

        <Plate n="22A" title="Ambiguous shipment — human descriptors, never IDs">
          <Log>
            <Row
              m={agent(copy.clarifyAmbiguousShipment('Kota load', '08:45', '18:00'))}
              nowMs={now}
            />
          </Log>
          <Composer quickReplies={['The 08:45 one', 'The 18:00 one']} onSend={() => {}} />
        </Plate>

        <Plate n="22B" title="After two failed attempts → escalate, do not loop">
          <div className="p-4">
            <Notice body="I’ve passed this to operations so a person can sort out which load you mean. Reference ESC-4482." />
          </div>
        </Plate>

        <Plate n="23A" title="Low-confidence ETA — never derive an ETA from a delay">
          <Log>
            <Row m={agent(copy.clarifyLowConfidenceEta('11:00'))} nowMs={now} />
          </Log>
          <Composer quickReplies={['Arriving 11:00', 'Might be longer']} onSend={() => {}} />
        </Plate>

        <Plate n="23B" title="Risk framed as a choice, not a hidden warning">
          <Log>
            <Row m={agent(copy.clarifyRiskAsChoice('11:00', '12:15'))} nowMs={now} />
          </Log>
        </Plate>

        <Plate n="24" title="Offline — cards disabled visibly, composer stays enabled">
          <StateLine
            state="PENDING_CONFIRMATION"
            expiresAt={PENDING_LIVE}
            operationalLine="Dock D1 · Tue 4 Aug"
            staleMinutes={2}
          />
          <div className="flex-1 p-4">
            <OptionCard option={OPTIONS[0]} state="offline" />
            <Notice body={copy.connectionLost} />
          </div>
          <Composer offline onSend={() => {}} />
        </Plate>

        {/* ---- F · Refusals and failures ---------------------------------------------- */}
        <Plate n="25A" title="“Just confirm it”">
          <Log>
            <Row m={agent(copy.refuseJustConfirm)} nowMs={now} />
          </Log>
          <Composer quickReplies={[copy.refuseFlagUrgentAction]} onSend={() => {}} />
        </Plate>

        <Plate n="25B" title="“Book 7:30 even though I arrive at 8” — names the invariant">
          <Log>
            <Row m={agent(copy.refuseInfeasibleTime('7:30', '08:00'))} nowMs={now} />
          </Log>
          <div className="px-4 pb-4">
            <OptionCard option={OPTIONS[0]} />
          </div>
        </Plate>

        <Plate n="25C" title="Off-manifest cargo — copy only, thread → ESCALATED">
          <Log>
            <Row m={agent(copy.refuseOffManifest)} nowMs={now} />
          </Log>
        </Plate>

        <Plate n="25D" title="“Give me that truck's slot” — policy once, then what IS open">
          <Log>
            <Row m={agent(copy.refuseOtherDriversSlot)} nowMs={now} />
          </Log>
          <div className="px-4 pb-4">
            <OptionCard option={OPTIONS[1]} />
          </div>
        </Plate>

        <Plate n="26" title="Refusal — safety. Nothing competes: no cards, no quick replies">
          <Log>
            <Row m={agent(copy.refuseSafety('ESC-4471'))} nowMs={now} />
          </Log>
        </Plate>

        <Plate n="27A" title="Message failed to send — inline Retry, text preserved">
          <Log>
            <Row
              m={{
                id: 'f1',
                tier: 'DRIVER',
                createdAt: new Date(now - 60_000).toISOString(),
                parts: [{ kind: 'text', text: 'Reaching around 11:20.' }],
                delivery: 'failed',
                clientMessageId: 'fixed-uuid',
              }}
              nowMs={now}
            />
            <Row
              m={{
                id: 'f2',
                tier: 'DRIVER',
                createdAt: new Date(now - 30_000).toISOString(),
                parts: [{ kind: 'text', text: 'Still stuck at the toll.' }],
                delivery: 'queued',
              }}
              nowMs={now}
            />
          </Log>
        </Plate>

        <Plate n="27B" title="Commit failed — “Nothing has changed” is load-bearing">
          <div className="p-4">
            <Notice body={copy.commitFailed} assertive />
          </div>
        </Plate>

        <Plate n="27C" title="Thread failed to load — skeleton → error + Retry">
          <EmptyState
            icon={Inbox}
            title={copy.threadLoadFailedTitle}
            body={copy.threadLoadFailedBody}
            actions={<Button variant="neutral">{copy.retryAction}</Button>}
          />
        </Plate>

        <Plate n="28A" title="Cancelled shipment — routes to DISPATCH, not operations">
          <Log>
            <Row m={agent(copy.cancelledShipment)} nowMs={now} />
          </Log>
        </Plate>

        <Plate n="28B" title="Thread-list consequence of a cancelled shipment">
          <ul role="list" className="flex flex-col gap-3 p-4">
            <ThreadCard
              thread={{
                ...THREADS[0],
                promiseState: null,
                operationalLine: null,
                lastMessagePreview: 'That shipment and its appointment were cancelled.',
                resolved: true,
                unread: false,
              }}
            />
          </ul>
        </Plate>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------------------- */

/** One 390x844 phone frame — the primary target from `screens.md`'s own header. */
function Plate({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <figure className="m-0">
      <figcaption className="mb-2 text-body">
        <span className="font-mono text-primary">{n}</span>{' '}
        <span className="text-muted-foreground">{title}</span>
      </figcaption>
      <div
        data-density="comfortable"
        className="flex h-[844px] w-[390px] flex-col overflow-hidden rounded-xl border border-border bg-background"
      >
        {children}
      </div>
    </figure>
  )
}

function Log({ children }: { children: ReactNode }) {
  return (
    <div role="log" aria-label="Conversation" className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      {children}
    </div>
  )
}

/** Uses the SAME `MessageParts` renderer the product transcript uses. The first version of this
 *  helper passed no children, and screen 4 rendered its two bubbles with no option cards under
 *  them -- the gallery certifying a screen it had not drawn. See message-parts.tsx. */
function Row({ m, nowMs }: { m: DriverMessage; nowMs: number }) {
  return (
    <DriverMessageRow message={m} nowMs={nowMs} onRetry={() => {}}>
      <MessageParts message={m} facilityName="Jaipur DC" />
    </DriverMessageRow>
  )
}

function agent(text: string): DriverMessage {
  return {
    id: text.slice(0, 12),
    tier: 'AGENT',
    createdAt: new Date().toISOString(),
    parts: [{ kind: 'text', text }],
  }
}

function Notice({
  body,
  action,
  assertive,
}: {
  body: string
  action?: string
  assertive?: boolean
}) {
  return (
    <div className="my-3 flex flex-col items-center gap-2">
      <p role={assertive ? 'alert' : 'status'} className="text-center text-body text-muted-foreground">
        {body}
      </p>
      {action ? <Button variant="neutral">{action}</Button> : null}
    </div>
  )
}

/** What a flagged plate shows instead of pretending to be built. */
function Gated() {
  return (
    <div className="flex flex-1 flex-col justify-center p-6 text-center">
      <p className="text-body-lg font-semibold">Gated behind issue #53</p>
      <p className="mt-2 text-body text-muted-foreground">
        The <code className="font-mono">HELD</code> promise state has no backend: no schema value
        on <code className="font-mono">appointments_appointment_status_check</code>, no{' '}
        <code className="font-mono">state</code>/<code className="font-mono">expires_at</code> on{' '}
        <code className="font-mono">dock_occupancy</code>, no{' '}
        <code className="font-mono">confirm_held_slot</code> tool, and the M8 sweeper's HELD leg
        returns <code className="font-mono">supported: false</code>. Set{' '}
        <code className="font-mono">heldStateEnabled</code> to see this plate.
      </p>
    </div>
  )
}
