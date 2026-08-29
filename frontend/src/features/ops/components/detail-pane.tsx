import { useState } from 'react'
import { Ban, Mail, MailWarning, MailX } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { facilityDisplayName } from '../lib/facility-names'
import { REASON_META } from '../lib/reasons'
import { sendAsOperationsEnabled } from '../lib/flags'
import type { CancelReasonCode, EscalationQueueItem, ResolveReasonCode } from '../lib/types'
import { EscalationStepper } from './escalation-stepper'
import { OwnerControl } from './owner-control'
import { CancelDialog, ResolveDialog } from './reason-picker-dialog'

/**
 * `screens.md` sections 3/3b, `edge-cases.md`. The flexible centre pane -- empty state when no
 * row is selected, otherwise the escalation's full detail.
 */
export function DetailPane({
  item,
  onAcknowledge,
  onResolve,
  onCancel,
  busy,
  alreadyActioned,
}: {
  item: EscalationQueueItem | null
  onAcknowledge: () => void
  onResolve: (reasonCode: ResolveReasonCode) => void
  onCancel: (reasonCode: CancelReasonCode) => void
  busy?: boolean
  /** edge-cases.md section 2 -- this exact row was acted on elsewhere while focused. */
  alreadyActioned?: { winningOwnerName: string | null } | null
}) {
  const [resolveOpen, setResolveOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)

  if (!item) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-body text-muted-foreground">Select an escalation.</p>
      </div>
    )
  }

  const reason = REASON_META[item.escalation_type]
  const terminal = item.escalation_status === 'RESOLVED' || item.escalation_status === 'CANCELLED'

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <header className="flex flex-col gap-2">
        {/* `id` + `tabIndex=-1`: accessibility.md "selecting a queue row -> focus goes to the
            detail pane's primary heading". `ops-console.tsx` focuses this element by id rather
            than the pane's outer wrapper. */}
        <h2 id="ops-detail-heading" tabIndex={-1} className="font-data text-h3 tabular-nums outline-none">
          {item.escalation_id} · {reason.label}
        </h2>
        <EscalationStepper
          status={item.escalation_status}
          position={item.stepper_position}
          severityCode={item.severity_code}
          slaRemainingMin={item.sla_remaining_min}
          owner={item.owner_name}
          variant="full"
        />
      </header>

      {alreadyActioned ? (
        <p role="alert" className="rounded-md bg-warning-bg px-3 py-2 text-body text-warning-fg">
          Already actioned
          {alreadyActioned.winningOwnerName ? ` by ${alreadyActioned.winningOwnerName}` : ''} — this
          row has changed since you selected it.
        </p>
      ) : null}

      {!terminal ? (
        <div className="flex flex-wrap items-center gap-2">
          <OwnerControl
            ownerName={item.owner_name}
            onAcknowledge={onAcknowledge}
            busy={busy}
          />
          <TakeOverControl />
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

      <section className="flex flex-col gap-1">
        <h3 className="text-label tracking-wide text-muted-foreground uppercase">Thread</h3>
        {/* G7 -- found during this build, not in the spec's G1-G6 list: no endpoint anywhere
            lets an ops-scoped caller read a thread's chat_messages. `GET /api/v1/chat/history`
            is `require_roles(RoleName.DRIVER)`-only (backend/app/api/v1/routers/chat.py:30), and
            no other router exposes thread content. Rendering a transcript here would mean
            inventing driver messages, which AGENTS.md forbids outright. Named honestly instead
            of silently omitted. */}
        <p className="rounded-md border border-dashed border-border p-3 text-body text-muted-foreground">
          Thread preview isn't available yet — there is no backend read for operations to view a
          driver conversation (found during this build; no tracked issue number yet, related to
          #55/#58).
        </p>
      </section>

      {!terminal ? (
        <div className="mt-2 flex gap-3">
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
 * `components.md` (this folder) section 5, U94. Take-over is real end to end in the backend
 * (`take_over_thread` in `escalation_service.py`) -- but wiring it needs `chat_threads.thread_id`,
 * which nothing in `GET /operations/escalation-queue`'s response (or any other read this build
 * found) ever returns. `hand_back_thread` has the same requirement. This is a second, related
 * gap found during this build (compounds #55/G2 and #58/G5, since a takeover with no way to send
 * or reach the driver would not be useful even if it could be wired) -- Inactive, not Disabled,
 * per components.md foundations section 18: fully focusable, explains itself.
 */
function TakeOverControl() {
  // Take-over has no ownership precondition server-side (escalation_service.py::take_over_thread
  // checks only facility scope + role + thread status, never owner_user_id) -- unlike Hand-back,
  // which requires IN_PROGRESS/ACKNOWLEDGED. Available from read-only-thread mode regardless of
  // who (if anyone) has acknowledged, matching Flow 2 step 1.
  if (sendAsOperationsEnabled) {
    return <Button variant="cautionary">Take over thread</Button>
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="neutral">Take over thread</Button>
      </PopoverTrigger>
      <PopoverContent role="dialog" aria-label="Why this isn't available">
        <Mail className="mb-2 size-4 text-muted-foreground" aria-hidden="true" />
        Not wired yet: no tool posts a message as OPERATIONS (issue #55), and this pane has no
        way to look up the thread id a takeover needs (found during this build). Acknowledge,
        Resolve and Cancel work today regardless.
      </PopoverContent>
    </Popover>
  )
}
