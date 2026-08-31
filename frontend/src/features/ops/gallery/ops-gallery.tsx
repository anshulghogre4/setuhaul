import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { CapacityIncidentRow } from '../components/capacity-incident-row'
import { TakeoverNoticeBanner, type TakeoverNotice } from '../components/takeover-control'
import { CopilotPane, CopilotSuggestionCard } from '../components/copilot-pane'
import { DetailPane } from '../components/detail-pane'
import { QueuePane } from '../components/queue-pane'
import { CancelDialog, ResolveDialog } from '../components/reason-picker-dialog'
import {
  ESCALATION_AMBIGUOUS_SOFT,
  ESCALATION_CAPACITY_INCIDENT,
  ESCALATION_OWNED_NOTIFICATION_FAILED,
  ESCALATION_RESOLVED,
  ESCALATION_UNDER_TAKEOVER,
  ESCALATION_UNMAPPED_REASON,
  ESCALATION_UNOWNED_BREACHING,
  ESCALATION_UNROUTABLE,
  ESCALATION_WAREHOUSE_CONFLICT,
  QUEUE_FIXTURE,
  SUGGESTION_ABSTAINED,
  SUGGESTION_RECOMMENDED,
  THREAD_FIXTURE,
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
        <h1 className="mt-2 text-display text-balance">14 screens ship now, 2 are honestly stubbed</h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Prompt 8 is now live: #55/#56/#58 shipped the reply path, so the composer, take-over,
          hand-back and the durable transcript are all wired for real. Prompts 12/13 are now live
          too: issue #57 scoped the co-pilot to a resolution-action suggestion (not summarise, not
          draft-reply) and gave it a contract. Still gated: prompt 14's action (issue #54/G1). Not
          built: prompt 3's live-arrival pill and prompt 10b's inline notice — both need a
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

        <Plate n="8" title="Under takeover — divider, OPERATIONS message, live composer">
          <div className="h-[720px] w-[460px] overflow-auto border border-border">
            <DetailPane
              item={ESCALATION_UNDER_TAKEOVER}
              onAcknowledge={() => {}}
              onResolve={() => {}}
              onCancel={() => {}}
              threadState="ready"
              messages={THREAD_FIXTURE}
              currentUserId="USR-DEMO-OPS"
            />
          </div>
          <p className="mt-2 max-w-[70ch] text-supporting text-muted-foreground">
            Fork G&rsquo;s gap, now renderable: the board never showed an AGENT or OPERATIONS
            message, so a coordinator could not see what their own reply looks like beside the
            assistant&rsquo;s and the driver&rsquo;s. All three tiers plus the centred takeover
            divider are here.
          </p>
        </Plate>

        <Plate n="8b" title="Take over — blocked on its prerequisite (NOT_ACKNOWLEDGED)">
          <div className="h-[420px] w-[460px] overflow-auto border border-border">
            <DetailPane
              item={ESCALATION_UNOWNED_BREACHING}
              onAcknowledge={() => {}}
              onResolve={() => {}}
              onCancel={() => {}}
              threadState="ready"
              messages={THREAD_FIXTURE.slice(0, 2)}
            />
          </div>
          <p className="mt-2 max-w-[70ch] text-supporting text-muted-foreground">
            take_over_thread refuses an unowned escalation with NOT_ACKNOWLEDGED (issue #56), so
            Take over renders aria-disabled — focusable, explains itself — with Acknowledge beside
            it as the fix. Flow 1&rsquo;s own order, enforced.
          </p>
        </Plate>

        <Plate n="8c" title="No thread attached — takeover genuinely unavailable">
          <div className="h-[420px] w-[460px] overflow-auto border border-border">
            <DetailPane
              item={ESCALATION_OWNED_NOTIFICATION_FAILED}
              onAcknowledge={() => {}}
              onResolve={() => {}}
              onCancel={() => {}}
              threadState="none"
            />
          </div>
        </Plate>

        <TakeoverNoticeDemo />

        <UndeliveredMessageDemo />

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

        <Plate n="1c" title="Queue row — a reason outside §7.4's nine (live data, 151 rows)">
          <div className="w-[360px]">
            <QueuePane
              state="ready"
              items={[ESCALATION_UNMAPPED_REASON]}
              selectedId={null}
              onSelect={() => {}}
              onRetry={() => {}}
            />
          </div>
        </Plate>

        <Plate n="11" title="Co-pilot — Inactive (no escalation selected)">
          <div className="h-[300px] w-[320px] border border-border">
            <CopilotPane escalationId={null} />
          </div>
        </Plate>

        <Plate n="12" title="Co-pilot — a recommended resolution action (issue #57)">
          <div className="w-[320px] border border-border p-4">
            <CopilotSuggestionCard suggestion={SUGGESTION_RECOMMENDED} />
          </div>
        </Plate>

        <Plate n="13" title="Co-pilot — an honest abstention (issue #57)">
          <div className="w-[320px] border border-border p-4">
            <CopilotSuggestionCard suggestion={SUGGESTION_ABSTAINED} />
          </div>
        </Plate>

        <Note n="12/13 — scope" title="Suggest a resolution action, not summarise or draft">
          The owner scoped the co-pilot on 2026-08-31 to one capability: recommend which action to
          take, with the facts behind it. Summarise-thread and draft-reply — `components.md`
          section 3 and `FR-OPS-003` — are deliberately NOT built, so the two-gate draft-reply card
          and its stale marker have nothing to render. The abstention plate above is the designed
          outcome for six of §7.4's nine reasons, not an error state.
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

/**
 * Every `TakeoverNotice` variant side by side -- the states hardest to reach by clicking, and the
 * ones most worth reviewing, since each is a refusal or a partial success a coordinator must act
 * on.
 *
 * `handback-needs-start` is the one to look at: `hand_back_thread` now requires `IN_PROGRESS`, so
 * a thread taken over before issue #56 made that value writable refuses -- and this is the real
 * one-call recovery rather than a dead end.
 */
function TakeoverNoticeDemo() {
  const notices: { label: string; notice: TakeoverNotice }[] = [
    { label: 'NOT_ACKNOWLEDGED', notice: { kind: 'not-acknowledged' } },
    { label: 'ALREADY_TAKEN_OVER', notice: { kind: 'already-taken-over' } },
    { label: 'NOT_IN_PROGRESS - already handed back', notice: { kind: 'handback-noop' } },
    { label: 'NOT_IN_PROGRESS - recoverable', notice: { kind: 'handback-needs-start' } },
    { label: 'NOT_OWNER', notice: { kind: 'not-owner', ownerName: 'Neha B.' } },
    { label: 'NOT_TAKEN_OVER (post refused)', notice: { kind: 'post-refused' } },
    {
      label: 'divider undelivered - Redis down',
      notice: { kind: 'divider-undelivered', reason: 'REDIS_UNAVAILABLE', event: 'joined' },
    },
    {
      label: 'divider undelivered - no live session',
      notice: {
        kind: 'divider-undelivered',
        reason: 'NO_LIVE_DRIVER_SESSION',
        event: 'handed-back',
      },
    },
    {
      label: 'thrown request (409 THREAD_UNSCOPED)',
      notice: {
        kind: 'failed',
        message: 'This thread has no shipment, so it cannot be scoped to a facility.',
      },
    },
  ]

  return (
    <Plate n="8d" title="Takeover refusals and undelivered dividers — every notice variant">
      <div className="flex max-w-[560px] flex-col gap-4">
        {notices.map(({ label, notice }) => (
          <div key={label} className="flex flex-col gap-1">
            <span className="font-mono text-micro text-muted-foreground">{label}</span>
            <TakeoverNoticeBanner
              notice={notice}
              onRecover={() => {}}
              onDismiss={() => {}}
            />
          </div>
        ))}
      </div>
    </Plate>
  )
}

/**
 * The `delivered: false` marker in situ, plus the two pending-send states. Issue #58's residual:
 * the row is durable in `chat_messages`, the driver's live feed never got it, and nothing
 * back-fills -- so the marker is permanent and per-message, not a toast that vanishes in five
 * seconds taking the only trace with it.
 */
function UndeliveredMessageDemo() {
  return (
    <Plate n="8e" title="Posted, durable, and the driver never saw it (#58's residual)">
      <div className="h-[560px] w-[460px] overflow-auto border border-border">
        <DetailPane
          item={ESCALATION_UNDER_TAKEOVER}
          onAcknowledge={() => {}}
          onResolve={() => {}}
          onCancel={() => {}}
          threadState="ready"
          messages={THREAD_FIXTURE}
          currentUserId="USR-DEMO-OPS"
          undelivered={{ 'MSG-004': 'NO_LIVE_DRIVER_SESSION' }}
          pending={[
            { key: 'k1', text: 'Are you still at the gate?', state: 'sending' },
            { key: 'k2', text: 'Checking with the yard now.', state: 'failed' },
          ]}
        />
      </div>
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
