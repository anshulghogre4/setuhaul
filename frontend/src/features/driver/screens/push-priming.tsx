import { Bell, BellOff } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/shared/ui/button'
import { copy } from '../lib/copy'

/**
 * Screens 14A and 14B — push-permission priming, and push denied.
 *
 * ## 14A: the pre-permission explainer
 *
 * The browser's own permission prompt is one-shot and unrecoverable: a driver who dismisses it
 * cannot be asked again by script. So the explainer earns its place by stating **what the
 * notification is for** before the OS prompt appears.
 *
 * F4 flagged that no notification *preview* exists on this screen and called it the
 * highest-leverage item on that checklist. Built here as a real preview of the actual push copy,
 * which is the same template as the in-app message — **a notification that says something
 * different from what the app says is a second source of truth**
 * (`flows-and-states.md`, "Notifications"). The preview is `aria-hidden` and the same words are
 * in the body text, so it is illustration rather than a duplicate announcement.
 *
 * ## 14B: consequence stated once
 *
 * *"Notifications are off — you'll need to keep this page open to see changes."* Plus a Profile
 * re-entry point. **Re-ask only after a genuinely missed event** (`edge-cases.md` section 14) —
 * which is why there is no retry button here and no interval-based nag: this screen states the
 * cost and gets out of the way.
 *
 * ## The accepted gap, recorded not solved
 *
 * A driver who never granted push — or who is on iOS without adding the PWA to their home screen
 * — **gets no proactive alert at all** for the four high-priority events (pending expired,
 * planner rejected, dock down / option withdrawn, hold lapsed). SMS was dropped from v1 because
 * India's DLT registration with TRAI is a multi-step regulatory precondition, not a config flag.
 * Nothing is lost (the thread list shows current promise state on next open) but nothing is
 * pushed either. This is stated in the design as an accepted limitation and it is not
 * work-aroundable here.
 *
 * Note also `pushSubscriptionEnabled` in `flags.ts`: the permission works today, but **nothing
 * server-side writes a `notifications` row yet** (no producer wired on any write path, E3.5's
 * own documented gap), so subscribing would create a channel with no sender. The permission
 * request is real; the subscription is flagged off.
 */
export function DriverPushPriming({ onDone }: { onDone?: () => void }) {
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(() =>
    typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
  )

  if (permission === 'denied') return <DriverPushDenied />

  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center p-(--content-p)">
      <Bell size={32} strokeWidth={2} aria-hidden="true" className="text-primary" />
      <h1 className="mt-4 text-h1 text-balance">{copy.pushPrimingTitle}</h1>
      <p className="mt-2 text-body-lg text-muted-foreground">{copy.pushPrimingBody}</p>

      {/* F4's answer: a real preview, using the SAME template as the in-app system notice. */}
      <div
        aria-hidden="true"
        className="mt-6 rounded-lg border border-floating-border bg-popover p-4 shadow-floating"
      >
        <p className="text-body font-semibold">SetuHaul</p>
        <p className="mt-1 text-body">
          No planner responded in time, so Dock D1 · 13:00–14:15 has been released.
        </p>
      </div>

      <div className="mt-8 flex flex-col gap-3">
        {/* Safer action first in DOM order (U79). Visually the primary is below it, which is the
            thumb-zone position -- order in the DOM and order on screen are allowed to differ;
            what U79 constrains is keyboard/AT traversal. */}
        <Button variant="neutral" onClick={onDone}>
          {copy.pushPrimingNotNow}
        </Button>
        <Button
          variant="constructive"
          onClick={() => {
            if (permission === 'unsupported') return
            void Notification.requestPermission().then((next) => {
              setPermission(next)
              if (next === 'granted') onDone?.()
            })
          }}
          disabled={permission === 'unsupported'}
        >
          {copy.pushPrimingEnable}
        </Button>
      </div>
    </div>
  )
}

export function DriverPushDenied() {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center p-(--content-p)">
      <BellOff size={32} strokeWidth={2} aria-hidden="true" className="text-subtle-foreground" />
      {/* role="status", not alert: this is informational, and the driver just made this choice
          deliberately. accessibility.md splits system notices exactly this way. */}
      <p role="status" className="mt-4 text-body-lg">
        {copy.pushDeniedStatus}
      </p>
      <p className="mt-2 text-body text-muted-foreground">{copy.pushDeniedReentry}</p>
      <div className="mt-8">
        <Button variant="neutral" asChild>
          <Link to="/driver/profile">{copy.navProfile}</Link>
        </Button>
      </div>
    </div>
  )
}
