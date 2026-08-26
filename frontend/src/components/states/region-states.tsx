import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { MapPinOff, OctagonAlert, ShieldOff, Wrench } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'

/**
 * Artboards 25-29.  These replace the whole CONTENT REGION.
 *
 * The shell -- rail, top bar, status bar -- **never unmounts** (U71).  Only this region
 * changes.  That is why each of these is a plain component rendered inside the shell's
 * <main>, not a route that swaps the whole tree.
 */

/**
 * Artboard 25.  Never a bare 403.
 *
 * **Names the facilities the user DOES have; never the one they hit.**  Naming what they
 * have is safe and gives them a route forward; naming what they hit confirms it exists.
 * Repeated scope failures are logged to `audit_logs` -- a signal worth having.
 */
export function OutOfScope({
  facilities,
  primaryHref,
  primaryLabel,
}: {
  facilities: string[]
  primaryHref: string
  primaryLabel: string
}) {
  const list =
    facilities.length <= 1
      ? facilities.join('')
      : `${facilities.slice(0, -1).join(', ')} and ${facilities.at(-1)}`

  return (
    <EmptyState
      icon={ShieldOff}
      title="This facility isn’t in your access scope"
      body={facilities.length ? `You have access to ${list}.` : undefined}
      actions={
        <Button asChild variant="constructive">
          <Link to={primaryHref}>{primaryLabel}</Link>
        </Button>
      }
    />
  )
}

/**
 * Artboard 26.  **Deliberately the same string** whether the record genuinely doesn't exist
 * or exists outside the viewer's scope.
 *
 * This is correct behaviour, not vagueness: a 404 that distinguishes the two cases is a
 * record-enumeration tool.  Do not "improve" it by adding detail.
 */
export function NotFound({ backHref = '/', backLabel = 'Back to your queue' }: {
  backHref?: string
  backLabel?: string
}) {
  return (
    <EmptyState
      icon={MapPinOff}
      title="That shipment doesn’t exist, or isn’t somewhere you have access to see."
      actions={
        <Button asChild variant="constructive">
          <Link to={backHref}>{backLabel}</Link>
        </Button>
      }
    />
  )
}

/**
 * Artboard 27.  **Scoped per region, never whole-app.**  The queue, the dock board and the
 * co-pilot each get their own boundary -- a planner mid-decision on the queue must not lose
 * that queue because the dock board threw.
 *
 * "Report this" attaches the region name and a trace id, never a stack trace shown to the
 * person using it.
 *
 * **Report comes before Try again in DOM order** (U79): the safer action first, so a fast
 * keyboard user who overshoots lands on the harmless one.
 */
export function RegionError({
  regionName,
  traceId,
  onReport,
  onRetry,
}: {
  regionName: string
  traceId?: string
  onReport?: (payload: { region: string; traceId?: string }) => void
  onRetry?: () => void
}) {
  return (
    <EmptyState
      icon={OctagonAlert}
      title="Something broke loading this."
      body="The rest of the app is unaffected."
      actions={
        <>
          <Button variant="neutral" onClick={() => onReport?.({ region: regionName, traceId })}>
            Report this
          </Button>
          <Button variant="constructive" onClick={onRetry}>
            Try again
          </Button>
        </>
      }
    />
  )
}

type BoundaryProps = { regionName: string; children: ReactNode }
type BoundaryState = { error: Error | null }

/** The class component exists only because React has no hook equivalent for
 *  `componentDidCatch`.  One per region, not one per app. */
export class RegionErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The trace id and region go to the reporter; the stack never reaches the user.
    console.error(`[${this.props.regionName}]`, error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <RegionError
          regionName={this.props.regionName}
          onRetry={() => this.setState({ error: null })}
        />
      )
    }
    return this.props.children
  }
}

/**
 * Artboard 28.  **Always states a duration** -- a maintenance page that doesn't reads as
 * indefinite, which is worse than the wait itself.
 *
 * **No retry button.**  Retrying does not shorten a migration, and a button that reloads
 * into the same page teaches people to distrust buttons.
 *
 * Not hypothetical: SOLUTION_DESIGN.md section 9.3's live-database migration is exactly the
 * event this announces.
 */
export function Maintenance({ estimatedMinutes = 15 }: { estimatedMinutes?: number }) {
  return (
    <EmptyState
      icon={Wrench}
      title="SetuHaul Dock Command is being updated."
      body={`Expect this to take about ${estimatedMinutes} minutes. Anything you were doing has been saved — just come back and pick up where you left off.`}
    />
  )
}
