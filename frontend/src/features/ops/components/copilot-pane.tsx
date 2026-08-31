import { useEffect, useState } from 'react'
import { Bot, CircleSlash, Lightbulb } from 'lucide-react'

import { Skeleton } from '@/shared/ui/skeleton'
import { fetchResolutionSuggestion } from '../lib/api'
import { copilotActiveEnabled } from '../lib/flags'
import type { ResolutionSuggestion } from '../lib/types'

/**
 * `screens.md` section 4, `components.md` (this folder) section 3, U57 -- **rescoped by the owner
 * on 2026-08-31 (issue #57).**
 *
 * ## What this pane does now, and what it deliberately does not
 *
 * It shows **one recommended resolution action and the facts that point at it**. It does not
 * summarise the thread, and it does not draft the coordinator's reply -- so the three capabilities
 * `components.md` section 3 specifies, and `REQUIREMENTS.md`'s `FR-OPS-003`, are *not* what ships
 * here. That divergence is real and is recorded in the issue rather than papered over: the value
 * of a co-pilot beside a console that already exposes every button is the *reasoning*, not another
 * button.
 *
 * ## It suggests. It never acts.
 *
 * There is no control in this pane that writes anything, and there is no auto-apply path anywhere
 * behind it -- `lib/api.ts` exports a single `GET` for this feature and nothing else.
 * `AGENTS.md`: the assistant layer "orchestrates typed tools and never... directly mutates
 * business tables". The recommendation names a tool by the same label the detail pane's own button
 * carries; the coordinator presses that button.
 *
 * ## Gated on selection, not on takeover -- a deliberate departure, flagged
 *
 * `screens.md` section 4 and `components.md` section 3 both gate this pane on an *active takeover*
 * (U94). That rule was written for three capabilities that all operate on a thread the coordinator
 * has already joined. This one operates on an **escalation**, which is readable the moment a row
 * is selected -- and keeping the takeover gate would make the pane structurally unable to ever
 * recommend `take_over_thread`, which is exactly what Flow 1 step 4 prescribes for
 * `AMBIGUOUS_SHIPMENT`. So the gate moved to "a row is selected". The Inactive state is preserved
 * verbatim for the no-selection case.
 *
 * ## Degradation
 *
 * `edge-cases.md` #5: "the console is **fully operable with the co-pilot entirely down**". A
 * failure here renders one line of text and nothing else changes -- the queue, the detail pane,
 * the transcript, the composer and every action are untouched. That is `auth-and-scoping.md`'s
 * U84 secondary-region policy, and it is why this component owns its own fetch rather than the
 * console owning it: a failing suggestion cannot take the console's load path down with it.
 */
export function CopilotPane({
  escalationId,
  escalationStatus,
}: {
  escalationId: string | null
  /** Not used for fetching -- it is a cache key. A suggestion is a statement about a lifecycle
   *  state, so acknowledging or taking over must re-derive it rather than leave a stale card
   *  recommending the step that was just taken. */
  escalationStatus?: string | null
}) {
  const [explaining, setExplaining] = useState(false)
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [suggestion, setSuggestion] = useState<ResolutionSuggestion | null>(null)

  useEffect(() => {
    if (!escalationId || !copilotActiveEnabled) {
      setSuggestion(null)
      setState('idle')
      return
    }
    // The `ignore` flag is React's own documented cleanup for fetching in an effect
    // (react.dev/reference/react/useEffect, "Fetching data") -- responses can arrive out of order
    // when a coordinator arrows down the queue quickly, and without this the third row's card can
    // be overwritten by the first row's late response.
    let ignore = false
    setState('loading')
    setSuggestion(null)
    fetchResolutionSuggestion(escalationId)
      .then((res) => {
        if (ignore) return
        setSuggestion(res)
        setState('ready')
      })
      .catch(() => {
        if (!ignore) setState('error')
      })
    return () => {
      ignore = true
    }
  }, [escalationId, escalationStatus])

  if (!escalationId || !copilotActiveEnabled) {
    return (
      <PaneShell>
        {/* `components.md` foundations section 18 **Inactive**, not Disabled and not Hidden: a
            real focusable control that explains itself on activation (Fork B, applied). A
            coordinator must never have to wonder whether the co-pilot exists. */}
        <button
          type="button"
          onClick={() => setExplaining((v) => !v)}
          aria-expanded={explaining}
          className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border p-4 text-center text-body text-muted-foreground hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Bot className="size-6" aria-hidden="true" />
          <span>
            {copilotActiveEnabled
              ? 'Select an escalation to see a suggested next step.'
              : 'Suggestions are switched off in this build.'}
          </span>
          {explaining ? (
            <span className="text-supporting">
              {copilotActiveEnabled
                ? 'The co-pilot reads the escalation and recommends which action to take, with the facts behind it. It never acts for you.'
                : 'Re-enable with the copilotActiveEnabled flag (issue #57).'}
            </span>
          ) : null}
        </button>
      </PaneShell>
    )
  }

  return (
    <PaneShell>
      {/* `accessibility.md`'s announcement table gives the co-pilot a **polite** live region --
          the result itself is read when a screen-reader user navigates into the panel, not pushed
          in full. Fix R11 in the implementation spec: `aria-live` was absent file-wide. */}
      <div role="status" aria-live="polite" className="flex min-h-0 flex-col gap-4 overflow-auto">
        {state === 'loading' ? <LoadingCard /> : null}

        {state === 'error' ? (
          <p className="text-supporting text-muted-foreground">
            Couldn’t load a suggestion — the escalation is still fully readable and every action
            still works.
          </p>
        ) : null}

        {state === 'ready' && suggestion ? <CopilotSuggestionCard suggestion={suggestion} /> : null}
      </div>
    </PaneShell>
  )
}

function PaneShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <h2 className="text-label tracking-wide text-muted-foreground uppercase">Co-pilot</h2>
      {children}
    </div>
  )
}

/** `components.md` section 13: loading never removes the thing's own label. The heading above
 *  stays put and only the result area shows placeholders. */
function LoadingCard() {
  return (
    <div className="flex flex-col gap-2">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  )
}

/**
 * Exported so `gallery/ops-gallery.tsx` can render prompts 12 and 13 against a fixture rather
 * than against the network. The gallery at `/ops/_states` is fixture-only by construction; a
 * component that fetched inside it would make the state board depend on a live backend.
 */
export function CopilotSuggestionCard({ suggestion }: { suggestion: ResolutionSuggestion }) {
  const recommended = suggestion.actions.find((a) => a.status === 'recommended')
  const suppressed = suggestion.actions.filter((a) => a.status === 'suppressed')
  const notBuilt = suggestion.actions.filter((a) => a.reason_code === 'NOT_IMPLEMENTED')

  return (
    <div className="flex flex-col gap-4">
      {recommended ? (
        <section className="flex flex-col gap-2 rounded-md border border-border bg-sunken p-3">
          <div className="flex items-center gap-2">
            <Lightbulb className="size-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-label tracking-wide text-muted-foreground uppercase">
              Suggested next step
            </span>
          </div>
          <p className="text-body font-medium">{recommended.label}</p>
          <p className="text-supporting text-muted-foreground">{suggestion.rationale}</p>
          {/* Deliberately not a button. The control that performs this action already exists in
              the detail pane under this exact label; duplicating it here would make the co-pilot
              an actor rather than an adviser. */}
          <p className="text-supporting text-muted-foreground">
            Use the “{recommended.label}” control in the escalation detail when you’re ready.
          </p>
        </section>
      ) : (
        <section className="flex flex-col gap-2 rounded-md border border-dashed border-border p-3">
          <div className="flex items-center gap-2">
            <CircleSlash className="size-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-label tracking-wide text-muted-foreground uppercase">
              No suggestion
            </span>
          </div>
          {/* An abstention is the designed outcome for six of §7.4's nine reasons, not a failure.
              It says *why* rather than showing an empty panel. */}
          <p className="text-supporting text-muted-foreground">
            {suggestion.abstain_reason?.label ?? 'Nothing points clearly at one action.'}
          </p>
        </section>
      )}

      {suggestion.evidence.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-label tracking-wide text-muted-foreground uppercase">
            What this is based on
          </h3>
          <ul className="flex flex-col gap-2">
            {suggestion.evidence.map((item) => (
              <li key={`${item.code}-${item.label}`} className="flex flex-col gap-0.5">
                <span className="text-supporting">{item.label}</span>
                {/* The source column travels with the fact, on screen. That is what makes "never
                    invent operational data" something a coordinator can check rather than trust:
                    every sentence above names the column it came from, including the SLA number's
                    `Source: assumption, untested` caveat. */}
                <span className="text-supporting text-muted-foreground">{item.source}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {suppressed.length > 0 ? (
        <section className="flex flex-col gap-1">
          <h3 className="text-label tracking-wide text-muted-foreground uppercase">
            Not suggested here
          </h3>
          {/* §7.4: `SAFETY_OR_REGULATED` is "Immediate, human-only". The buttons still work — the
              co-pilot simply will not point at them, and says so rather than going quiet. */}
          <p className="text-supporting text-muted-foreground">
            {suppressed.map((a) => a.label).join(', ')} — safety and regulated escalations are
            closed by a person’s judgement. The controls still work.
          </p>
        </section>
      ) : null}

      {notBuilt.length > 0 ? (
        <section className="flex flex-col gap-1">
          <h3 className="text-label tracking-wide text-muted-foreground uppercase">Not built yet</h3>
          {/* `request_sequencer_proposal` is §7.5.5's eighth tool and the Sequencer is unbuilt
              (#54, #49). Reported rather than hidden, so a capacity-cascade row says plainly that
              the right move is unavailable instead of steering to a wrong one. */}
          <p className="text-supporting text-muted-foreground">
            {notBuilt.map((a) => a.label).join(', ')}
          </p>
        </section>
      ) : null}

      <p className="text-supporting text-muted-foreground">
        {/* Provenance, shown rather than assumed. If this ever becomes model-backed the response
            shape does not change, so this line is the only thing that would tell a coordinator. */}
        {suggestion.generator === 'deterministic:v1'
          ? 'Derived from the records above. No model was called.'
          : `Generated by ${suggestion.generator}.`}
      </p>
    </div>
  )
}
