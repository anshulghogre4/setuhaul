import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { IconRail } from '@/components/shell/icon-rail'
import { NotificationsPanel } from '@/components/shell/notifications-panel'
import { SearchPalette } from '@/components/shell/search-palette'
import { StatusBar } from '@/components/shell/status-bar'
import { TopBar } from '@/components/shell/top-bar'
import { FacilitySwitcher } from '@/components/shell/facility-switcher'
import { UserMenu } from '@/components/shell/user-menu'
import { IdleWarning } from '@/components/states/idle-warning'
import {
  Maintenance,
  NotFound,
  OutOfScope,
  RegionError,
} from '@/components/states/region-states'
import { PasswordReset } from '@/features/auth/password-reset'
import { RolePicker } from '@/features/auth/role-picker'
import { SignIn } from '@/features/auth/sign-in'
import { SettingsPage } from '@/features/settings/settings-page'
import {
  CARRIER,
  FACILITIES,
  GATE_SINGLE_ROLE,
  NOTIFICATIONS,
  OPS_MANAGER,
  PLANNER_MULTI_ROLE,
  RECENT_SEARCHES,
  SEARCH_RESULTS,
} from '@/features/gallery/fixtures'
import { Button } from '@/shared/ui/button'
import { useTheme } from '@/shared/lib/theme'
import { useUndo } from '@/shared/lib/undo'

/**
 * A rendering of all 32 shared-shell artboards, one plate each, on one page.
 *
 * This exists because "it type-checks and looks plausible in code" is not the same as "it
 * has been seen working" -- the design phase found three real defects (a contrast failure,
 * an invalid listbox content model, a status bar that would have swallowed a connection
 * drop) that were only caught by rendering and measuring, never by reading markup.  This is
 * the equivalent gate on the built components.
 *
 * Route: /_states.  Not linked from anywhere in the app.
 */
export function StatesGallery() {
  const { choice, setChoice, resolved } = useTheme()
  const undo = useUndo()
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('kota')
  const [idleOpen, setIdleOpen] = useState(false)
  const [facility, setFacility] = useState<string>('FAC-JAI-01')

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="mx-auto flex max-w-320 flex-wrap items-end justify-between gap-6 px-6 pt-10 pb-2">
        <div>
          <p className="text-label uppercase text-primary">SetuHaul Dock Command · shared shell</p>
          <h1 className="mt-2 text-display text-balance">
            32 artboards, rendered from the built components
          </h1>
          <p className="mt-2 max-w-[62ch] text-body text-muted-foreground">
            Every state in <code className="font-mono text-supporting">mockup-shared-shell.html</code>,
            rendered by the real React components rather than the reference markup. Toggle the
            theme to check both at once — light is the shipped default for every role (U69).
            Popover artboards are click-to-open: only one popover can be open at a time, because
            the click that opens a second is a click outside the first.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="neutral"
            onClick={() => setChoice(resolved === 'dark' ? 'light' : 'dark')}
          >
            Switch to {resolved === 'dark' ? 'Light' : 'Dark'}
          </Button>
          <span className="text-supporting text-subtle-foreground">
            stored choice: <span className="font-mono">{choice}</span>
          </span>
        </div>
      </header>

      <main className="mx-auto grid max-w-320 grid-cols-1 gap-x-8 gap-y-11 px-6 pt-8 pb-18 lg:grid-cols-6">
        <SectionHeading
          title="A · Signing in"
          body="One shared sign-in for all six roles; the role decides the landing surface. Errors never disclose whether an account exists."
        />

        <Plate span={2} title="1 · Sign-in — at rest" note="One field, not two tabs. No Remember me, no SSO, no Sign up.">
          <Framed><SignIn /></Framed>
        </Plate>

        <Plate
          span={2}
          title="2 · Sign-in — password revealed"
          note="Toggle is a button with aria-pressed, not a checkbox. Click the eye to see the accessible name flip."
        >
          <Framed><SignIn initialIdentifier="priya.nair@setuhaul.in" /></Framed>
        </Plate>

        <Plate
          span={2}
          title="3 · Sign-in — “Those details don’t match”"
          note="Identical wording whichever half was wrong. Neither field is marked — singling one out is the disclosure."
        >
          <Framed><SignIn state="error" initialIdentifier="priya.nair@setuhaul.in" /></Framed>
        </Plate>

        <Plate
          span={2}
          title="4 · Sign-in — rate limited"
          note="Sign in is Disabled with the reason above it. “Forgotten your password?” stays live."
        >
          <Framed><SignIn state="rate-limited" initialIdentifier="priya.nair@setuhaul.in" /></Framed>
        </Plate>

        <Plate
          span={2}
          title="5 · Role picker — multi-role only"
          note="Whole row is the target; activating proceeds immediately. Never renders with one row."
        >
          <Framed>
            <RolePicker grants={PLANNER_MULTI_ROLE.grants} onChoose={(g) => toast(`Role: ${g.roleLabel}`)} />
          </Framed>
        </Plate>

        <SectionHeading
          title="B · Password reset"
          body="Email-only for v1. Neither screen ever confirms an account exists, and “sent” is informational blue, not success green."
        />

        <Plate span={2} title="6 · Reset — request a link">
          <Framed><PasswordReset state="request" /></Framed>
        </Plate>
        <Plate span={2} title="7 · Reset — link sent" note="Informational blue. No green, no checkmark, no confetti.">
          <Framed><PasswordReset state="sent" /></Framed>
        </Plate>
        <Plate span={2} title="8 · Set a new password" note="Requirements carry a marker per line, never colour alone.">
          <Framed><PasswordReset state="set-new" /></Framed>
        </Plate>
        <Plate span={2} title="9 · Set a new password — mismatch" note="This one can name the field; which field is wrong is not a secret here.">
          <Framed><PasswordReset state="mismatch" /></Framed>
        </Plate>
        <Plate span={2} title="10 · Reset link expired or already used" note="The form is not rendered at all behind it.">
          <Framed><PasswordReset state="expired" /></Framed>
        </Plate>

        <SectionHeading
          title="C · Top bar, help and the two popovers"
          body="56px. Both popovers are tier-3 Floating, opaque, non-modal — no scrim, Escape closes and returns focus to the trigger."
        />

        <Plate span={6} title="11 · Top bar — anatomy at rest" note="Unread count is in the bell's accessible name, not just the badge. Click search or press Cmd/Ctrl+K.">
          <div className="w-full">
            <TopBar
              identity={PLANNER_MULTI_ROLE}
              notificationsState="items"
              notifications={NOTIFICATIONS}
              unreadCount={3}
              onOpenSearch={() => setSearchOpen(true)}
              onFacilityChange={setFacility}
              onSignOut={() => toast('Signed out (demo)')}
            />
            <div className="h-24 bg-background" />
          </div>
        </Plate>

        <Plate span={3} title="12 · Help — a contact route, nothing more" note="Hover or focus the ? — tooltip only. No menu, no panel. No help centre, ever (U73).">
          <div className="w-full">
            <TopBar
              identity={GATE_SINGLE_ROLE}
              notificationsState="caught-up"
              notifications={[]}
              unreadCount={0}
              onOpenSearch={() => setSearchOpen(true)}
              onFacilityChange={setFacility}
            />
            <div className="h-24 bg-background" />
          </div>
        </Plate>

        <Plate span={3} title="13 · User menu — multi-role" note="Click the avatar. Identity header is inert. Appearance is inline and live — it really re-themes the page.">
          <PopoverPlate>
            <UserMenu identity={PLANNER_MULTI_ROLE} onSignOut={() => toast('Signed out (demo)')} />
          </PopoverPlate>
        </Plate>

        <Plate span={3} title="14 · User menu — single role, sign-out-everywhere expanded" note="Click the avatar. “Switch role” is absent from the DOM entirely, not greyed (U83). Sign-out-everywhere expands in place — no modal.">
          <PopoverPlate>
            <UserMenu
              identity={GATE_SINGLE_ROLE}
              onSignOutEverywhere={() => toast('Signed out everywhere (demo)')}
            />
          </PopoverPlate>
        </Plate>

        <Plate span={3} title="15 · Notifications — unread present" note="Rendered inline here so all four states are comparable at once. Unread on three channels: dot, weight 600, aria-label starting “Unread”. No per-item buttons at all.">
          <Floating width={400}>
            <NotificationsPanel state="items" items={NOTIFICATIONS} onMarkAllRead={() => toast('Marked all read')} />
          </Floating>
        </Plate>
        <Plate span={3} title="16 · Notifications — loading" note="Three skeletons shaped like real items, animate-shim at 1600ms. Never a centred spinner.">
          <Floating width={400}><NotificationsPanel state="loading" /></Floating>
        </Plate>
        <Plate span={3} title="17 · Notifications — caught up" note="A good state. No CTA — a control with nothing to act on is not a control.">
          <Floating width={400}><NotificationsPanel state="caught-up" /></Floating>
        </Plate>
        <Plate span={3} title="18 · Notifications — nothing yet" note="Distinct from 17, and the distinction is a server-side history check, never count === 0.">
          <Floating width={400}><NotificationsPanel state="nothing-yet" /></Floating>
        </Plate>

        <SectionHeading
          title="D · Search palette"
          body="640px, ~15% from the top, flat scrim. Facility-scoped for v1 and the scope line says so. Open it with the buttons below or Cmd/Ctrl+K."
        />

        <Plate span={2} title="19 · Search palette — grouped results" note="Fixed group order. Empty groups absent, never an empty header. Highlight is background AND a 2px left edge.">
          <PaletteLauncher label="Open with query “kota”" onOpen={() => { setSearchQuery('kota'); setSearchOpen(true) }} />
        </Plate>
        <Plate span={2} title="20 · Search palette — first open" note="Empty query is the recent list. The one control in the product with no visible label — it carries an aria-label.">
          <PaletteLauncher label="Open empty" onOpen={() => { setSearchQuery(''); setSearchOpen(true) }} />
        </Plate>
        <Plate span={2} title="21 · Search palette — no results" note="Echoes the query, states the scope, one Clear search.">
          <PaletteLauncher label="Open with query “RJ14”" onOpen={() => { setSearchQuery('RJ14'); setSearchOpen(true) }} />
        </Plate>

        <SectionHeading
          title="E · Account settings"
          body="One route, one scroll, five sections, 720px left-aligned. Saves immediately; no Save button. Sections 1 and 5 are Read-only in U83's sense."
        />

        <Plate span={6} title="22 · Settings — the whole page">
          <div className="w-full bg-background p-6" data-density="comfortable">
            <SettingsPage identity={PLANNER_MULTI_ROLE} />
          </div>
        </Plate>
        <Plate span={3} title="23 · Settings — “Mute everything” on" note="Rows dim, toggles disable, reason inline. Muted toggles keep their true values rather than snapping to Off.">
          <div className="w-full bg-background p-6" data-density="comfortable">
            <SettingsPage identity={PLANNER_MULTI_ROLE} state="muted" />
          </div>
        </Plate>
        <Plate span={3} title="24 · Settings — a preference failed to save" note="“Nothing has changed” is the load-bearing half of the message.">
          <div className="w-full bg-background p-6" data-density="comfortable">
            <SettingsPage identity={PLANNER_MULTI_ROLE} state="save-failed" />
          </div>
        </Plate>

        <SectionHeading
          title="F · States that replace the whole content region"
          body="The shell — rail, top bar, status bar — never unmounts (U71). Only this region changes."
        />

        <Plate span={2} title="25 · Out of scope" note="Names the facilities the user does have; never the one they hit.">
          <Framed pad>
            <OutOfScope
              facilities={['Jaipur DC', 'Gurugram Cross-Dock']}
              primaryHref="/_states"
              primaryLabel="Go to Jaipur DC"
            />
          </Framed>
        </Plate>
        <Plate span={2} title="26 · 404 — resource not found" note="Same string whether absent or out of scope — a distinguishing 404 is an enumeration tool.">
          <Framed pad><NotFound backHref="/_states" /></Framed>
        </Plate>
        <Plate span={2} title="27 · Error boundary — scoped" note="Per region, never whole-app. Report is first in DOM order (U79).">
          <Framed pad>
            <RegionError regionName="queue" traceId="trc-demo" onReport={() => toast('Reported')} onRetry={() => toast('Retrying')} />
          </Framed>
        </Plate>
        <Plate span={3} title="28 · Maintenance" note="Always states a duration. No retry button — retrying doesn't shorten a migration.">
          <Framed pad><Maintenance /></Framed>
        </Plate>
        <Plate span={3} title="29 · Idle warning" note="Initial focus is “Stay signed in” — never the countdown, never the destructive option. Drivers never see this.">
          <Framed pad>
            <Button variant="neutral" onClick={() => setIdleOpen(true)}>
              Open idle warning
            </Button>
          </Framed>
        </Plate>

        <SectionHeading
          title="G · The rest of the shell"
          body="The two regions on screen 100% of the time for five of six roles, plus the switcher's open state."
        />

        <Plate span={2} title="30a · Icon rail — planner" note="One destination, facility-scoped. The 4px stripe is Jaipur DC's violet; the 2px active marker clears it by a measured 2px.">
          <RailFrame>
            <IconRail role="WAREHOUSE_PLANNER" activeFacility={FACILITIES[0]} />
          </RailFrame>
        </Plate>
        <Plate span={2} title="30b · Icon rail — carrier, hover for the tooltip" note="No stripe: carriers are scoped by carrier_id, so there is no facility to colour. Hover the icon — the tooltip must paint ON TOP of the content bars.">
          <RailFrame>
            <IconRail role="TRANSPORT_MANAGER" activeFacility={null} landmarkSuffix="at rest" />
          </RailFrame>
        </Plate>
        <Plate span={2} title="30c · Icon rail — carrier, expanded" note="240px tier-3 overlay sitting on top of content that has NOT moved.">
          <RailFrame expandedPad>
            <IconRail role="TRANSPORT_MANAGER" activeFacility={null} expanded landmarkSuffix="expanded" />
          </RailFrame>
        </Plate>

        <Plate
          span={3}
          title="31 · Status bar — connection states, and per-role field presence"
          note="Icon AND text, never a dot. Only the connection field is a live region. Offline is the only state taking danger colour. Field presence follows the owner's 2026-08-27 rule: only roles that have a facility show the policy version."
        >
          <div className="w-full">
            <div className="h-10 bg-background" />
            <StatusBarRow label="Planner · connected" role="WAREHOUSE_PLANNER" connection="connected" lastSync="09:52:14" facilityName="Jaipur DC" pendingCount={14} policyVersion="v12" />
            <StatusBarRow label="Planner · offline" role="WAREHOUSE_PLANNER" connection="offline" lastSync="6m ago" facilityName="Jaipur DC" pendingCount={14} policyVersion="v12" />
            <StatusBarRow label="Planner · syncing" role="WAREHOUSE_PLANNER" connection="syncing" lastSync="09:52:14" facilityName="Jaipur DC" pendingCount={14} policyVersion="v12" />
            <StatusBarRow label="Gate · facility-scoped, SO it shows policy" role="GATE_OFFICER" connection="connected" lastSync="09:52:14" facilityName="Gurugram Cross-Dock" pendingCount={7} policyVersion="v12" />
            <StatusBarRow label="Carrier · no facility_id, so NO facility and NO policy" role="TRANSPORT_MANAGER" connection="connected" lastSync="09:52:14" facilityName={null} pendingCount={3} policyVersion="v12" />
          </div>
        </Plate>

        <Plate span={3} title="32 · Facility switcher — open" note="Click the trigger. Swatch here and the rail stripe are the only two places facility accent may appear. “All facilities” is a dashed outline, not a hue.">
          <div className="w-full">
            <div className="flex h-14 items-center bg-card px-4">
              <FacilitySwitcher
                role={OPS_MANAGER.activeRole}
                facilities={FACILITIES}
                activeFacilityId={facility}
                canSelectAll
                onChange={(id) => {
                  setFacility(id)
                  toast(`Facility → ${id}`)
                }}
              />
            </div>
            <div className="h-72 bg-background" />
          </div>
        </Plate>

        <Plate span={6} title="32b · Facility switcher — absent for carrier (U83)" note="Not disabled, not greyed: absent from the DOM entirely. Inspect the top bar below — there is no switcher element to find.">
          <div className="w-full">
            <TopBar
              identity={CARRIER}
              notificationsState="nothing-yet"
              notifications={[]}
              unreadCount={0}
              onOpenSearch={() => setSearchOpen(true)}
              onFacilityChange={setFacility}
            />
            <div className="h-16 bg-background" />
          </div>
        </Plate>

        <SectionHeading
          title="Cross-cutting checks"
          body="Two things that are only observable at runtime and were the whole reason for building this page."
        />

        <Plate span={6} title="z-index: an undo toast must be reachable over a modal" note="U41's time-boxed undo that can be hidden is no undo. Open the modal, then fire the toast — the toast must sit above it and be clickable.">
          <div className="flex w-full flex-wrap items-center gap-4 p-6">
            <Button variant="neutral" onClick={() => setIdleOpen(true)}>
              1. Open a modal
            </Button>
            <Button
              variant="constructive"
              onClick={() =>
                undo.fire({
                  message: 'Confirmed SHP1014 · Dock D1 13:00',
                  onUndo: () => toast('Undone'),
                })
              }
            >
              2. Fire an undo toast
            </Button>
            <span className="text-supporting text-muted-foreground">
              The toast is bottom-left, 5s, and must be hittable with the modal open. It is
              also reachable by <span className="font-mono">Cmd/Ctrl+Z</span> regardless of
              focus — the keyboard path U41 needs to be real for a screen-reader user.
            </span>
          </div>
        </Plate>
      </main>

      <SearchPalette
        open={searchOpen}
        onOpenChange={setSearchOpen}
        query={searchQuery}
        onQueryChange={setSearchQuery}
        results={searchQuery.trim().toLowerCase() === 'kota' ? SEARCH_RESULTS : []}
        recent={RECENT_SEARCHES}
        scopeLabel="Jaipur DC only"
      />

      <IdleWarning
        open={idleOpen}
        remainingLabel="5:00"
        onStay={() => setIdleOpen(false)}
        onSignOut={() => setIdleOpen(false)}
      />
    </div>
  )
}

/** One status bar with a caption naming the role, so per-role field presence is visible
 *  side by side rather than only assertable from the predicate. */
function StatusBarRow({
  label,
  ...props
}: { label: string } & React.ComponentProps<typeof StatusBar>) {
  return (
    <div data-statusbar-role={props.role}>
      <p className="bg-background px-3 pt-3 pb-1 text-micro uppercase text-subtle-foreground">
        {label}
      </p>
      <StatusBar {...props} />
    </div>
  )
}

function SectionHeading({ title, body }: { title: string; body: string }) {
  return (
    <div className="col-span-full mt-2 border-t border-border pt-6">
      <h2 className="text-h2">{title}</h2>
      <p className="mt-1.5 max-w-[78ch] text-supporting text-muted-foreground">{body}</p>
    </div>
  )
}

function Plate({
  span,
  title,
  note,
  children,
}: {
  span: 2 | 3 | 6
  title: string
  note?: string
  children: ReactNode
}) {
  const cls = span === 6 ? 'lg:col-span-6' : span === 3 ? 'lg:col-span-3' : 'lg:col-span-2'
  return (
    <section className={`flex min-w-0 flex-col gap-3 ${cls}`}>
      <div>
        <h3 className="text-body font-semibold">{title}</h3>
        {note ? <p className="mt-1 text-supporting text-muted-foreground">{note}</p> : null}
      </div>
      <div className="flex justify-center overflow-hidden rounded-xl border border-border bg-background">
        {children}
      </div>
    </section>
  )
}

/** Auth screens render full-bleed; the frame stops them stretching the whole page. */
function Framed({ children, pad }: { children: ReactNode; pad?: boolean }) {
  return (
    <div className={`w-full ${pad ? 'flex items-center justify-center bg-background p-6' : ''}`}>
      {children}
    </div>
  )
}

/**
 * Popover artboards are CLICK-TO-OPEN here, not pre-opened, and that is a faithful
 * rendering rather than a shortcut.
 *
 * Two things were established by measurement while building this page:
 *
 *  1. A `defaultOpen` prop was tried on both popover components and removed.  It set the
 *     state correctly -- instrumented with a temporary `data-dbg` attribute, which read
 *     `defaultOpen=true` while `open` was already `false` a frame later -- but Radix's
 *     DismissableLayer dismissed it during mount.  It was dead weight that existed only for
 *     this gallery and did not actually work, so the shipped components keep one code path.
 *  2. Even opening them programmatically, **only one popover can be open at a time**: the
 *     click that opens the second is, by definition, a click outside the first, so Radix
 *     correctly dismisses it.  A board showing three simultaneously-open popovers would be
 *     depicting something the real shell cannot do.
 *
 * The reference mockup could show three at once because it is flat HTML with no dismiss
 * layer.  Here, click the trigger.
 */
function PopoverPlate({ children }: { children: ReactNode }) {
  return (
    <div className="w-full">
      <div className="flex h-14 items-center justify-end bg-card px-4">{children}</div>
      <div className="h-96 bg-background" />
    </div>
  )
}

function Floating({ width, children }: { width: number; children: ReactNode }) {
  return (
    <div className="w-full bg-background p-6">
      <div
        style={{ width }}
        className="mx-auto max-w-full overflow-hidden rounded-md border border-floating-border bg-popover shadow-floating"
      >
        {children}
      </div>
    </div>
  )
}

function PaletteLauncher({ label, onOpen }: { label: string; onOpen: () => void }) {
  return (
    <div className="flex w-full items-center justify-center bg-background p-10">
      <Button variant="neutral" onClick={onOpen}>
        {label}
      </Button>
    </div>
  )
}

/** A slice of app surface: rail beside content, so the tooltip's paint order and the active
 *  marker's clearance of the facility stripe are both actually observable. */
function RailFrame({ children, expandedPad }: { children: ReactNode; expandedPad?: boolean }) {
  return (
    <div className="w-full bg-background p-6">
      <div className="relative flex min-h-45 overflow-hidden rounded-lg border border-border bg-background">
        {children}
        <div className={`min-w-0 flex-1 p-4 ${expandedPad ? 'pl-18' : ''}`}>
          <div className="h-3 w-[45%] rounded-sm bg-border" />
          <div className="mt-3 h-3 w-[80%] rounded-sm bg-border" />
          <div className="mt-3 h-3 w-[65%] rounded-sm bg-border" />
        </div>
      </div>
    </div>
  )
}
