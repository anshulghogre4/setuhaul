import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { CapacityIncidentRow } from '../components/capacity-incident-row'
import { CopilotPane } from '../components/copilot-pane'
import { DetailPane } from '../components/detail-pane'
import { QueuePane } from '../components/queue-pane'
import { CancelDialog, ResolveDialog } from '../components/reason-picker-dialog'
import {
  ESCALATION_AMBIGUOUS_SOFT,
  ESCALATION_CAPACITY_INCIDENT,
  ESCALATION_OWNED_NOTIFICATION_FAILED,
  ESCALATION_RESOLVED,
  ESCALATION_UNOWNED_BREACHING,
  ESCALATION_UNROUTABLE,
  ESCALATION_WAREHOUSE_CONFLICT,
  QUEUE_FIXTURE,
} from './fixtures'

/**
 * Every ops-console screen `implementation-spec.md` section 3 marks 🟢 or 🟡, rendered by the
 * **built components** against fixture data -- route `/ops/_states`, not linked from the app.
 * Same purpose as `/driver/_states` and `/_states`: "it type-checks" is not "it has been seen
 * rendering."
 *
 * 🔴 screens (3, G6; 12/13, G4; 8's send path, G2) render an honest note instead of a fake plate
 * -- the brief for this build is explicit that a screen with nothing to call must not look like
 * it works.
 */
export function OpsStatesGallery() {
  return (
    <div className="min-h-dvh bg-background p-6 text-foreground" data-density="compact">
      <header className="mb-8">
        <p className="text-label text-primary uppercase">SetuHaul · ops exception console (E5.2)</p>
        <h1 className="mt-2 text-display text-balance">9 screens ship now, 3 + 4 are honestly stubbed</h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Gated: prompt 14's action (issue #54/G1), prompt 8's composer + takeover (issue #55/G2,
          plus a thread-id lookup gap found during this build), prompts 12/13 (issue #57/G4). Not
          built at all: prompt 3's live-arrival pill and prompt 10b's inline notice — both need a
          live-update transport this product does not have (issue #59/G6).
        </p>
      </header>

      <div className="flex flex-col gap-10">
        <Plate n="1" title="Queue row — default / hover / focus / selected">
          <div className="w-[360px]">
            <QueuePane
              state="ready"
              items={[ESCALATION_UNOWNED_BREACHING, ESCALATION_OWNED_NOTIFICATION_FAILED]}
              selectedId={ESCALATION_OWNED_NOTIFICATION_FAILED.escalation_id}
              onSelect={() => {}}
              onRetry={() => {}}
            />
          </div>
        </Plate>

        <FilteredDemo />

        <Note n="3" title="Live arrivals held behind the frozen sort">
          Not built. Needs a live-update transport (issue #59, G6) that does not exist anywhere in
          this product outside driver-chat's single-consumer `/chat` SSE stream, which does not
          extend to a multi-viewer queue. The queue is a snapshot, refreshed by an explicit action.
        </Note>

        <Plate n="4" title="Queue loading — shell never unmounts">
          <div className="w-[360px]">
            <QueuePane state="loading" items={[]} selectedId={null} onSelect={() => {}} onRetry={() => {}} />
          </div>
        </Plate>

        <Plate n="5a/5b" title="Queue load failed — regional, not global">
          <div className="w-[360px]">
            <QueuePane state="error" items={[]} selectedId={null} onSelect={() => {}} onRetry={() => {}} />
          </div>
        </Plate>

        <Plate n="6a" title="Empty — caught up">
          <div className="w-[360px]">
            <QueuePane state="ready" items={[]} selectedId={null} onSelect={() => {}} onRetry={() => {}} />
          </div>
        </Plate>

        <Plate n="7a" title="Detail — escalation selected, before takeover">
          <div className="h-[520px] w-[420px] overflow-auto border border-border">
            <DetailPane
              item={ESCALATION_AMBIGUOUS_SOFT}
              onAcknowledge={() => {}}
              onResolve={() => {}}
              onCancel={() => {}}
            />
          </div>
        </Plate>

        <Plate n="7b" title="Reason section — NOTIFICATION_FAILED vs NOTIFICATION_UNROUTABLE">
          <div className="flex gap-4">
            <div className="h-[420px] w-[380px] overflow-auto border border-border">
              <DetailPane item={ESCALATION_OWNED_NOTIFICATION_FAILED} onAcknowledge={() => {}} onResolve={() => {}} onCancel={() => {}} />
            </div>
            <div className="h-[420px] w-[380px] overflow-auto border border-border">
              <DetailPane item={ESCALATION_UNROUTABLE} onAcknowledge={() => {}} onResolve={() => {}} onCancel={() => {}} />
            </div>
          </div>
        </Plate>

        <Note n="8" title="Under takeover — composer + Resolve/Cancel">
          The pane, take-over control, Resolve and Cancel are all real (see plate 7a — Take over
          renders Inactive with an explanation). The live composer is not demonstrated here: it
          has nowhere to send (issue #55, G2), and this build's brief is explicit that a control
          with nothing to call must not be shown as if it works.
        </Note>

        <Plate n="9" title="WAREHOUSE_REPLY_CONFLICT — two accounts, no auto-reconcile">
          <div className="h-[420px] w-[420px] overflow-auto border border-border">
            <DetailPane item={ESCALATION_WAREHOUSE_CONFLICT} onAcknowledge={() => {}} onResolve={() => {}} onCancel={() => {}} />
          </div>
        </Plate>

        <Plate n="10a" title="ALREADY_ACTIONED — lost the acknowledge race">
          <div className="h-[420px] w-[420px] overflow-auto border border-border">
            <DetailPane
              item={ESCALATION_AMBIGUOUS_SOFT}
              onAcknowledge={() => {}}
              onResolve={() => {}}
              onCancel={() => {}}
              alreadyActioned={{ winningOwnerName: 'Priya N.' }}
            />
          </div>
        </Plate>

        <Note n="10b" title="The underlying shipment changed under the coordinator">
          Not built. This is an inline notice that arrives without a page reload — the same
          missing live-update transport as prompt 3 (issue #59, G6).
        </Note>

        <Plate n="11" title="Co-pilot — Inactive">
          <div className="h-[300px] w-[320px] border border-border">
            <CopilotPane takeoverActive={false} />
          </div>
        </Plate>

        <Note n="12/13" title="Co-pilot active — draft-reply, degradations">
          Behind `copilotActiveEnabled` (issue #57, G4 / Fork A): no endpoint, request shape or
          error taxonomy exists for summarise / fetch-context / draft-reply anywhere in
          `backend/app/`. Building the two-gate draft flow against nothing would mean faking an
          LLM response.
        </Note>

        <Plate n="14" title="Capacity incident — collapsed / expanded / gated action">
          <div className="w-[360px] border border-border">
            <CapacityIncidentRow
              rowId={ESCALATION_CAPACITY_INCIDENT.escalation_id}
              dockLabel="DOCK-JAI-D3"
              affected={ESCALATION_CAPACITY_INCIDENT.affected_shipments ?? []}
            />
          </div>
        </Plate>

        <ReasonPickerDemo />

        <Plate n="16a/16b" title="Toast stack + inline failed write">
          <div className="flex gap-3">
            <button
              type="button"
              className="rounded-md border border-input px-3 py-2 text-body"
              onClick={() => toast.success(`Resolved ${ESCALATION_RESOLVED.escalation_id}.`)}
            >
              Fire success toast
            </button>
            <button
              type="button"
              className="rounded-md border border-input px-3 py-2 text-body"
              onClick={() => toast.error("That didn't save. Nothing has changed.")}
            >
              Fire failed-write toast
            </button>
          </div>
        </Plate>
      </div>
    </div>
  )
}

function FilteredDemo() {
  return (
    <Plate n="2a/2b" title="Queue filtered — active chips / filtered to zero">
      <div className="flex gap-4">
        <div className="w-[360px]">
          <QueuePane
            state="ready"
            items={QUEUE_FIXTURE}
            selectedId={null}
            onSelect={() => {}}
            onRetry={() => {}}
          />
        </div>
      </div>
      <p className="mt-2 text-supporting text-muted-foreground">
        Use the Filter menu above to reach both the active-chip state and the filtered-to-zero
        state live in this plate.
      </p>
    </Plate>
  )
}

function ReasonPickerDemo() {
  const [resolveOpen, setResolveOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  return (
    <Plate n="15a/15b" title="Reason picker — Cancel / Resolve">
      <div className="flex gap-3">
        <button
          type="button"
          className="rounded-md border border-input px-3 py-2 text-body"
          onClick={() => setResolveOpen(true)}
        >
          Open Resolve dialog
        </button>
        <button
          type="button"
          className="rounded-md border border-input px-3 py-2 text-body"
          onClick={() => setCancelOpen(true)}
        >
          Open Cancel dialog
        </button>
      </div>
      <ResolveDialog open={resolveOpen} onOpenChange={setResolveOpen} onConfirm={() => setResolveOpen(false)} />
      <CancelDialog open={cancelOpen} onOpenChange={setCancelOpen} onConfirm={() => setCancelOpen(false)} />
    </Plate>
  )
}

function Plate({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <figure className="m-0">
      <figcaption className="mb-2 text-body">
        <span className="font-mono text-primary">{n}</span>{' '}
        <span className="text-muted-foreground">{title}</span>
      </figcaption>
      {children}
    </figure>
  )
}

function Note({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <figure className="m-0 max-w-[70ch]">
      <figcaption className="mb-2 text-body">
        <span className="font-mono text-primary">{n}</span>{' '}
        <span className="text-muted-foreground">{title}</span>
      </figcaption>
      <p className="rounded-md border border-dashed border-border p-4 text-body text-muted-foreground">
        {children}
      </p>
    </figure>
  )
}
