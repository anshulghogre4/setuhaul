import { useId, useState, type RefObject } from 'react'
import { Ban, Info, MailWarning, MailX } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { facilityDisplayName } from '../lib/facility-names'
import { REASON_META } from '../lib/reasons'
import { sendAsOperationsEnabled } from '../lib/flags'
import type { EscalationChange } from '../lib/live-queue'
import type { CancelReasonCode, EscalationQueueItem, ResolveReasonCode, ThreadMessage } from '../lib/types'
import { EscalateDialog } from './escalate-dialog'
import { EscalationStepper } from './escalation-stepper'
import { DetailOverflowMenu, REASSIGN_BLOCKED_REASON } from './overflow-menu'
import { OwnerControl } from './owner-control'
import { CancelDialog, ResolveDialog } from './reason-picker-dialog'
import { ThreadComposer } from './thread-composer'
import { ThreadTranscript, type PendingMessage } from './thread-transcript'
import { TakeoverControl, TakeoverNoticeBanner, type TakeoverNotice } from './takeover-control'

/**
 * `screens.md` sections 3/3b, `edge-cases.md`. The flexible centre pane -- empty state when no
 * row is selected, otherwise the escalation's full detail, its thread, and the composer.
 *
 * ## Action order in this pane, and an unresolved contradiction it exposes
 *
 * `accessibility.md`'s "Safer-action-first DOM order" paragraph says two things that cannot both
 * hold: its **instruction** is that "Resolve/Cancel/Reassign precede any takeover-adjacent action
 * in tab order", while its **stated reason** is "destructive-adjacent controls should not be the
 * first stop for a keyboard user tabbing through quickly" -- which argues the opposite, since
 * Resolve and Cancel are the two terminal, irreversible actions here and Send is not.
 *
 * This build follows the stated *reason* and prompt 8's own layout: transcript, then composer and
 * Send, then the Resolve/Cancel group last, with DOM order matching visual order throughout. The
 * alternative -- CSS-reordering the group to satisfy the instruction's letter -- was checked
 * against WCAG 2.2's Understanding document for 2.4.3 Focus Order, which permits a mismatch but
 * treats it as a hazard and recommends that "the focus order reinforces the reading order implied
 * by the visual layout". Introducing that hazard to satisfy half of a self-contradicting sentence
 * is the wrong trade. **Flagged for the owner rather than silently decided.**
 */
export function DetailPane({
  item,
  liveChange = null,
  onDismissLiveChange = () => {},
  onAcknowledge,
  onStartWork = () => {},
  onEscalated = () => {},
  onResolve,
  onCancel,
  busy,
  alreadyActioned,
  // --- thread + takeover (E5.2 gap closure, issues #55/#56/#58) ---
  threadState = 'none',
  messages = [],
  pending = [],
  undelivered = {},
  currentUserId = null,
  takeoverNotice = null,
  onReloadThread = () => {},
  onSendMessage = () => {},
  onRetryPending = () => {},
  onDiscardPending = () => {},
  onTakeOver = () => {},
  onHandBack = () => {},
  onRecoverHandBack = () => {},
  onDismissTakeoverNotice = () => {},
  composerRef,
  stepperRef,
  headingId: headingIdProp,
}: {
  item: EscalationQueueItem | null
  /** `edge-cases.md` sections 2 and 9 -- what a poll observed changing on THIS escalation since the
   *  coordinator opened it (issue #59). */
  liveChange?: EscalationChange | null
  onDismissLiveChange?: () => void
  onAcknowledge: () => void
  /** Flow 1 step 4 -- `ACKNOWLEDGED -> IN_PROGRESS`, set explicitly once real work has started. */
  onStartWork?: () => void
  /** A new case was opened on this shipment from the overflow's Escalate entry. */
  onEscalated?: (escalationId: string) => void
  onResolve: (reasonCode: ResolveReasonCode) => void
  onCancel: (reasonCode: CancelReasonCode) => void
  busy?: boolean
  /** edge-cases.md section 2 -- this exact row was acted on elsewhere while focused. */
  alreadyActioned?: { winningOwnerName: string | null } | null
  threadState?: 'loading' | 'error' | 'ready' | 'none'
  messages?: ThreadMessage[]
  pending?: PendingMessage[]
  undelivered?: Record<string, string | null>
  currentUserId?: string | null
  takeoverNotice?: TakeoverNotice | null
  onReloadThread?: () => void
  onSendMessage?: (text: string) => void
  onRetryPending?: (key: string) => void
  onDiscardPending?: (key: string) => void
  onTakeOver?: () => void
  onHandBack?: () => void
  onRecoverHandBack?: () => void
  onDismissTakeoverNotice?: () => void
  composerRef?: RefObject<HTMLTextAreaElement | null>
  stepperRef?: RefObject<HTMLDivElement | null>
  /** Issue #91. The heading's id used to be the literal "ops-detail-heading", and the states
   *  gallery renders NINE detail panes, so nine `<h2>`s shared it and any focus/aria reference
   *  resolved to the first one. The console owns the id (it is the thing that focuses the
   *  heading after a row selection, by `getElementById`), and passes it down; a standalone
   *  render falls back to its own `useId`. */
  headingId?: string
}) {
  const [resolveOpen, setResolveOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [escalateOpen, setEscalateOpen] = useState(false)
  const fallbackHeadingId = useId()
  const headingId = headingIdProp ?? fallbackHeadingId

  if (!item) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-body text-muted-foreground">Select an escalation.</p>
      </div>
    )
  }

  const reason = REASON_META[item.escalation_type]
  const terminal = item.escalation_status === 'RESOLVED' || item.escalation_status === 'CANCELLED'
  const underTakeover = item.thread_status === 'ESCALATED'

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <header className="flex flex-col gap-2">
        {/* `id` + `tabIndex=-1`: accessibility.md "selecting a queue row -> focus goes to the
            detail pane's primary heading". `ops-console.tsx` focuses this element by id rather
            than the pane's outer wrapper, and supplies the id (see the `headingId` prop). */}
        <h2 id={headingId} tabIndex={-1} className="font-data text-h3 tabular-nums outline-none">
          {item.escalation_id} · {reason.label}
        </h2>
        {/* Focus target after a hand-back completes: accessibility.md's focus table sends focus
            to "the detail pane's stepper/status area -- not the composer, since it just became
            non-interactive again". */}
        <div ref={stepperRef} tabIndex={-1} className="outline-none">
          <EscalationStepper
            status={item.escalation_status}
            position={item.stepper_position}
            severityCode={item.severity_code}
            slaRemainingMin={item.sla_remaining_min}
            owner={item.owner_name}
            variant="full"
          />
        </div>
      </header>

      {alreadyActioned ? (
        <p role="alert" className="rounded-md bg-warning-bg px-3 py-2 text-body text-warning-fg">
          Already actioned
          {alreadyActioned.winningOwnerName ? ` by ${alreadyActioned.winningOwnerName}` : ''} — this
          row has changed since you selected it.
        </p>
      ) : null}

      {liveChange && liveChange.escalationId === item.escalation_id ? (
        <LiveChangeNotice change={liveChange} onDismiss={onDismissLiveChange} />
      ) : null}

      {!terminal ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <OwnerControl ownerName={item.owner_name} onAcknowledge={onAcknowledge} busy={busy} />
            <StartWorkControl
              item={item}
              currentUserId={currentUserId}
              busy={busy}
              onStartWork={onStartWork}
            />
            {sendAsOperationsEnabled ? (
              <TakeoverControl
                item={item}
                busy={busy}
                onTakeOver={onTakeOver}
                onHandBack={onHandBack}
              />
            ) : (
              <UnwiredTakeoverNote />
            )}
            {/* `screens.md` section 3: the overflow appears "once acknowledged", and it is pushed
                to the trailing edge because prompt 7 draws it opposite the primary action rather
                than beside it. */}
            {item.owner_name !== null ? (
              <div className="ml-auto">
                <DetailOverflowMenu
                  busy={busy}
                  onEscalate={() => setEscalateOpen(true)}
                  reassignBlockedReason={REASSIGN_BLOCKED_REASON}
                />
              </div>
            ) : null}
          </div>
          {/* Full width, below the row -- several lines of copy plus, for the recoverable
              hand-back refusal, its own action button. Inside the flex row above it would be
              squeezed to the Take-over button's width. */}
          {sendAsOperationsEnabled && takeoverNotice ? (
            <TakeoverNoticeBanner
              notice={takeoverNotice}
              busy={busy}
              onRecover={onRecoverHandBack}
              onDismiss={onDismissTakeoverNotice}
            />
          ) : null}
        </div>
      ) : null}

      <section className="flex flex-col gap-1">
        <h3 className="text-label tracking-wide text-muted-foreground uppercase">Reason</h3>
        <ReasonSection item={item} />
      </section>

      <section className="flex flex-col gap-1">
        <h3 className="text-label tracking-wide text-muted-foreground uppercase">Shipment</h3>
        <p className="text-body-lg">
          {item.shipment_id} · {facilityDisplayName(item.facility_id)}
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-label tracking-wide text-muted-foreground uppercase">
          {underTakeover ? 'Thread' : 'Thread (read-only until takeover)'}
        </h3>
        <ThreadTranscript
          state={threadState}
          messages={messages}
          pending={pending}
          undelivered={undelivered}
          currentUserId={currentUserId}
          onRetry={onReloadThread}
          onRetryPending={onRetryPending}
          onDiscardPending={onDiscardPending}
        />
      </section>

      {/* The composer only renders where there is a thread to write into. `sendAsOperationsEnabled`
          still gates it, so the flag remains a single switch over the whole reply path. */}
      {!terminal && sendAsOperationsEnabled && item.thread_id !== null ? (
        <ThreadComposer
          ref={composerRef}
          active={underTakeover}
          busy={busy}
          onSend={onSendMessage}
        />
      ) : null}

      {!terminal ? (
        // Prompt 8: Resolve/Cancel "in a group separated from Send by at least 16px and visually
        // grouped apart from it". `mt-4` is 16px. Two different terminal states with two
        // different driver-facing consequences (Flow 6), never interchangeable "done" buttons --
        // and `destructive` is never adjacent to `constructive` (components.md section 1), which
        // the composer's Send sitting in its own group above also satisfies.
        <div className="mt-4 flex gap-3 border-t border-border pt-4">
          <Button variant="constructive" onClick={() => setResolveOpen(true)} disabled={busy}>
            Resolve
          </Button>
          <Button variant="destructive" onClick={() => setCancelOpen(true)} disabled={busy}>
            Cancel
          </Button>
        </div>
      ) : (
        <EmptyState
          icon={Ban}
          title={`This escalation is ${item.escalation_status.toLowerCase()}.`}
          className="items-start px-0 text-left"
        />
      )}

      <EscalateDialog
        item={item}
        open={escalateOpen}
        onOpenChange={setEscalateOpen}
        onEscalated={onEscalated}
      />

      <ResolveDialog
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        onConfirm={(code) => {
          setResolveOpen(false)
          onResolve(code)
        }}
        busy={busy}
      />
      <CancelDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        onConfirm={(code) => {
          setCancelOpen(false)
          onCancel(code)
        }}
        busy={busy}
      />
    </div>
  )
}

/**
 * **Advance to `IN_PROGRESS`** -- `flows-and-states.md` Flow 1 step 4: *"Advancing to
 * `IN_PROGRESS` is a status the coordinator sets explicitly once real work has started, not an
 * automatic side effect of acknowledging."*
 *
 * ## Why this button did not exist until now, and where the design does and does not place it
 *
 * `POST /operations/escalations/{id}/start` (issue #56) and `lib/api.ts::startEscalationWork` have
 * both shipped since E5.2, but the only call site was the hand-back recovery banner in
 * `takeover-control.tsx` -- so the middle stepper dot was reachable only as a side effect of a
 * *failed* hand-back, or of a takeover (which advances the status server-side in the same
 * transaction). A coordinator working a reason that never involves a thread at all
 * (`NOTIFICATION_FAILED`, `WAREHOUSE_REPLY_CONFLICT`) had no way to say they had started.
 *
 * **The design specifies the transition but never draws the control.** `flows-and-states.md`
 * Flow 1 requires it, `components.md` section 5 depends on it (hand-back "requires the escalation
 * to be in `IN_PROGRESS` or later"), and `escalation-stepper.tsx` has always drawn the position --
 * but `screens.md` section 3 and `stitch-prompts.md` prompt 7 both draw only `[ Acknowledge ]`
 * and `[ ⋯ ]`. This build puts it in the same lifecycle action row, immediately after Acknowledge,
 * because that row *is* the pane's lifecycle sequence and the transition is the next step in it.
 * Flagged for the owner rather than treated as a settled placement.
 *
 * **Not a primary button.** Prompt 7 is explicit that "only one primary action exists in this
 * view" and names Acknowledge and Take over as the two decisions the pane foregrounds, so this is
 * `neutral`.
 *
 * ## Three visibility rules, each from a server behaviour rather than a taste
 *
 *  - **Hidden while unowned.** `start_escalation_work` answers `NOT_ACKNOWLEDGED`; the pane
 *    already shows `[ Acknowledge ]`, which is the one thing that makes this reachable.
 *  - **Hidden once past `ACKNOWLEDGED`.** At `IN_PROGRESS` the stepper says so and a second press
 *    would only return `ALREADY_IN_PROGRESS`.
 *  - **Inactive, not hidden, when somebody else owns it** (`components.md` foundations section 18):
 *    the endpoint answers `NOT_OWNER`, and a coordinator looking at a colleague's escalation should
 *    be told that rather than shown a control that fails on press. `currentUserId === null` (the
 *    `/auth/me` read failed, which this console treats as non-fatal) falls back to offering it --
 *    the server is the authority either way, and hiding a legitimate action on a failed read is the
 *    worse of the two errors.
 */
function StartWorkControl({
  item,
  currentUserId,
  busy,
  onStartWork,
}: {
  item: EscalationQueueItem
  currentUserId: string | null
  busy?: boolean
  onStartWork: () => void
}) {
  const explainId = useId()
  if (item.escalation_status !== 'ACKNOWLEDGED') return null

  const someoneElseOwnsIt =
    currentUserId !== null && item.owner_user_id !== null && item.owner_user_id !== currentUserId

  if (someoneElseOwnsIt) {
    return (
      <>
        <Button variant="neutral" aria-disabled aria-describedby={explainId} onClick={(e) => e.preventDefault()}>
          Mark in progress
        </Button>
        <span id={explainId} className="text-supporting text-muted-foreground">
          {item.owner_name ?? 'Another coordinator'} owns this — only the owner can start work on
          it.
        </span>
      </>
    )
  }

  return (
    <Button variant="neutral" onClick={onStartWork} disabled={busy}>
      Mark in progress
    </Button>
  )
}

/**
 * The pre-flag fallback. Kept so flipping `sendAsOperationsEnabled` back to `false` is a genuine
 * one-line revert rather than a rebuild -- the rollback path for this change.
 */
function UnwiredTakeoverNote() {
  return (
    <p className="text-supporting text-muted-foreground">
      Thread takeover is switched off in this build.
    </p>
  )
}

/**
 * `screens.md` prompt 7b. `NOTIFICATION_FAILED` vs `NOTIFICATION_UNROUTABLE` must not look
 * alike (`edge-cases.md` section 6) -- different icon, different text, and `UNROUTABLE` never
 * offers retry (retrying a NULL recipient is pointless and misleading).
 */
function ReasonSection({ item }: { item: EscalationQueueItem }) {
  if (item.escalation_type === 'NOTIFICATION_FAILED') {
    return (
      <div className="flex items-start gap-2">
        <MailWarning className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="flex flex-col gap-2">
          <p className="text-body">The notification send failed in flight and can be retried.</p>
          <Button variant="neutral" size="sm" disabled title="Retry-send has no wired backend action in this build yet.">
            Retry send
          </Button>
        </div>
      </div>
    )
  }
  if (item.escalation_type === 'NOTIFICATION_UNROUTABLE') {
    return (
      <div className="flex items-start gap-2">
        <MailX className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-body">
          There was never a valid recipient for this notification. Retry is not offered — fix the
          contact record instead.
        </p>
      </div>
    )
  }
  if (item.escalation_type === 'WAREHOUSE_REPLY_CONFLICT') {
    // Prompt 9. Rendered generically off `payload` -- the escalation_queue response carries no
    // structured "stored schedule vs. reply" fields, only a free-form payload dict
    // (escalate_exception's `payload: dict[str, Any]`). No one-click reconcile anywhere
    // (edge-cases.md section 10) -- there is no such control here.
    return (
      <div className="flex flex-col gap-2">
        <p className="text-body">
          The warehouse's reply contradicts the stored schedule. Both versions render read-only;
          resolving this still requires a reason and, if needed, a takeover.
        </p>
        <pre className="overflow-auto rounded-md bg-sunken p-2 text-supporting text-muted-foreground">
          {JSON.stringify(item.payload, null, 2)}
        </pre>
      </div>
    )
  }
  const reasonText = (item.payload as { reason?: string }).reason
  return <p className="text-body">{reasonText ?? REASON_META[item.escalation_type].label}</p>
}

/**
 * `edge-cases.md` section 9 -- "the detail pane surfaces the new fact inline ... as soon as it's
 * known", and section 2's race when the same fact is somebody else claiming this escalation.
 *
 * **Inline and non-blocking, never a modal.** Section 9's whole point is that the escalation does
 * *not* auto-resolve and the coordinator is "left to Resolve or Cancel deliberately, with the new
 * fact as visible context for that decision". A modal would take the decision; a toast would
 * disappear before they made it.
 *
 * **`role="alert"` (assertive) when the change is a race**, per section 2 and
 * `accessibility-behaviour.md`'s row for it -- the coordinator has this escalation open in front of
 * them, which is precisely "about to act on a row that just changed underneath them". A change that
 * is not a race (a hand-back, a status advancing to IN_PROGRESS) uses `role="status"`, which is
 * polite: it is context, not an interruption.
 *
 * **The two politeness levels are deliberately NOT unified.** `accessibility-behaviour.md` has a
 * polite, count-only row for a queue arrival and an assertive row for this; the ops queue pill uses
 * the first and this notice uses the second, and collapsing them to one level would break whichever
 * behaviour lost.
 *
 * **What this cannot say**, and it is a real gap rather than a rendering choice: section 9's own
 * example sentence names a *shipment* fact ("SHP1015 was confirmed by another planner at 09:58").
 * `get_exception_queue` returns no shipment or appointment status, so the escalation-level facts
 * below are what the read actually supports. See `lib/live-queue.ts`.
 */
function LiveChangeNotice({
  change,
  onDismiss,
}: {
  change: EscalationChange
  onDismiss: () => void
}) {
  const at = new Date(change.atIso)
  const time = Number.isNaN(at.getTime())
    ? null
    : at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })

  return (
    <div
      role={change.race ? 'alert' : 'status'}
      className="flex items-start gap-2 rounded-md border border-info-border bg-info-bg px-3 py-2 text-body text-info-fg"
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {change.facts.map((fact) => (
          <p key={fact}>
            {fact}
            {time ? ` (${time})` : ''}
          </p>
        ))}
        <p className="text-supporting">
          Nothing has been closed for you — Resolve or Cancel is still yours to choose.
        </p>
      </div>
      <Button variant="ghost" size="sm" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  )
}
