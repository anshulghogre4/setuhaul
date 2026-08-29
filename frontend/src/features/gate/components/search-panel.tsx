import { useRef, useState } from 'react'
import { Construction, TriangleAlert } from 'lucide-react'

import { KioskField } from './kiosk-field'
import { OutcomeBlock, OutcomeFact } from './outcome-block'
import { PrimaryAction } from './primary-action'
import { MIN_QUERY_LENGTH, searchTrucks } from '../lib/api'
import { gateSearchEnabled } from '../lib/flags'
import type { GateTruckMatch } from '../lib/types'

/** One id for the field's `aria-describedby` and the message it points at -- a literal, not a
 *  `useId()`, because only one search field ever exists on this surface at a time. */
const MESSAGE_ID = 'gate-search-no-match'

/**
 * Flow 1 (U109). Typed entry only -- shipment ID **or** plate number, no scan, camera or NFC path,
 * because nothing in the schema establishes that a scannable code exists.
 *
 * The match / no-match / multiple-match flow is real code against `GET /api/v1/gate/trucks`
 * (issue #67), branching on the **server's own `code`** rather than on array length: `NO_MATCH` is a
 * 200 carrying an empty list, not a 404, precisely so Flow 1.3 can keep the officer on this screen
 * with the field still focused. Treating an empty result as a transport failure would throw that
 * away.
 *
 * `MULTIPLE_MATCHES` is a **common** path, not a rare one -- a plate genuinely can have several
 * in-window shipments -- so `DisambiguationList` is a fully-built screen, not an edge case bolted on.
 *
 * **The `gateSearchEnabled` branch below is the one place on this surface where an honest "not yet
 * available" belongs**, and it sits here rather than spread across the nineteen screens behind it:
 * this field is the single entry point to all of them, so the gap gets stated exactly once, where an
 * officer would actually meet it. The flag is now on; the branch is kept rather than deleted because
 * it is the honest state to fall back to if #67 is reverted.
 *
 * No autocomplete, no type-ahead, no recent-searches list -- this is a shared device, and surfacing
 * the previous officer's lookups across a shift boundary leaks operational context to the wrong
 * person.
 *
 * `mockup.html` screen 4: on a no-match the field **keeps its failed value and retains focus** so
 * the officer can retype immediately rather than re-tapping into it; the message sits *below* the
 * field it refers to and nothing above it shifts. A routine mistype, not a system failure -- no
 * shake, no flash, no full-screen error page, and no dismiss X (warning and error messages are not
 * dismissible on this surface).
 */
export function SearchPanel({
  onFound,
  onDisambiguate,
}: {
  onFound: (truck: GateTruckMatch) => void
  /** The query is handed on with the matches: screen 5's heading echoes what was actually matched
   *  ("2 trucks match RJ14 GH 2211"), which is how an officer notices a stray character. */
  onDisambiguate: (query: string, matches: GateTruckMatch[]) => void
}) {
  const [query, setQuery] = useState('')
  const [state, setState] = useState<'idle' | 'searching' | 'no-match' | 'lookup-failed'>('idle')
  const inputRef = useRef<HTMLInputElement>(null)

  /**
   * The real Flow 1 branch: match -> Flow 2, no match -> named cause + retry, multiple -> the
   * disambiguation list. All three branches are live code against `GET /api/v1/gate/trucks`,
   * mapped from the server's own `code` rather than from the array length -- `NO_MATCH` is a 200
   * with an empty list, not a 404. `gateSearchEnabled` (issue #67) is what still guards it.
   */
  async function search() {
    const typed = query.trim()
    // Guarded client-side: the service raises QUERY_TOO_SHORT (422) under two characters, and a
    // round trip that can only be rejected is a second of an officer's time for no information.
    if (typed.length < MIN_QUERY_LENGTH || !gateSearchEnabled) return
    setState('searching')
    try {
      const found = await searchTrucks(typed)
      if (found.code === 'NO_MATCH') {
        setState('no-match')
        // Flow 1.3: the field retains focus so the officer can immediately retype rather than
        // re-tapping into it.
        inputRef.current?.focus()
        return
      }
      setState('idle')
      if (found.code === 'MATCH') onFound(found.matches[0])
      else onDisambiguate(typed, found.matches)
    } catch {
      // A lookup that could not RUN is not the same fact as a truck that does not exist. Saying
      // "no shipment matches" for a transport failure would send an officer chasing paperwork for
      // a truck standing in front of them, so the two get different states and different copy.
      //
      // No artboard exists for this case -- `mockup.html` screen 4 is a genuine no-match only --
      // so the copy is inferred from foundations `components.md` section 13's named-cause-plus-next
      // -action anatomy and is flagged in the build report rather than presented as specified.
      setState('lookup-failed')
    }
  }

  // Flag off: the heading and the stub, and **no field at all**.
  //
  // Caught by looking at a real render rather than at the source, while the flag was still off.
  // Keeping the field visible preserved screen 3's designed shape, but it produced a 56px input an
  // officer could type a real plate into, press Enter on, and get silence from -- a control that
  // looks like it works and does not, which is the exact failure `components.md` foundations
  // section 18 spends its whole Disabled-vs-Inactive distinction trying to prevent.
  if (!gateSearchEnabled) {
    return (
      <div className="flex flex-col gap-4">
        <h2 className="text-h1 text-balance">Search</h2>
        <SearchNotYetAvailable />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-h1 text-balance">Search</h2>

      <KioskField
        label="Shipment ID or plate number"
        variant="lookup"
        value={query}
        onChange={(v) => {
          setQuery(v)
          if (state !== 'idle') setState('idle')
        }}
        onSubmit={() => void search()}
        inputRef={inputRef}
        invalid={state === 'no-match'}
        describedBy={state === 'no-match' ? MESSAGE_ID : undefined}
      />

      {state === 'no-match' ? (
        <div id={MESSAGE_ID}>
          <OutcomeBlock
            tone="danger"
            live="alert"
            icon={TriangleAlert}
            headline="No shipment matches that ID or plate."
            align="inline"
          >
            <OutcomeFact>Check the number and try again.</OutcomeFact>
          </OutcomeBlock>
        </div>
      ) : null}

      {state === 'lookup-failed' ? (
        <OutcomeBlock
          tone="warning"
          live="alert"
          icon={TriangleAlert}
          headline="Couldn’t look that truck up."
          align="inline"
        >
          <OutcomeFact>Check the connection and try again.</OutcomeFact>
        </OutcomeBlock>
      ) : null}

      <PrimaryAction
        // "Try again" after a failure, "Search" otherwise -- `mockup.html` screen 4's own button
        // label. The in-flight state freezes the label rather than showing a bare spinner.
        label={state === 'idle' || state === 'searching' ? 'Search' : 'Try again'}
        state={state === 'searching' ? 'submitting' : 'default'}
        onClick={() => void search()}
      />
    </div>
  )
}

/**
 * The honest stub, at the actual entry point and nowhere else.
 *
 * Not an empty state pretending the yard is empty, and not a disabled Search button -- a disabled
 * control would say "not right now", which is Disabled's meaning (`components.md` foundations
 * section 18) and is false: this is not temporarily unavailable pending a prerequisite the officer
 * could satisfy. It is not built. Saying so plainly is the only accurate option.
 */
function SearchNotYetAvailable() {
  return (
    <div className="flex flex-col gap-4 rounded-md border border-input bg-hover p-6">
      <p className="flex items-center gap-3 text-h2">
        <Construction className="size-6 text-muted-foreground" aria-hidden="true" />
        Truck lookup is not available yet
      </p>
      <p className="text-body-lg">
        Every gate and yard action is built and connected, but truck lookup by shipment ID or plate
        is not switched on yet. Tracked as issue #67.
      </p>
    </div>
  )
}
