import { useId, useState } from 'react'
import { CircleAlert } from 'lucide-react'

import type { Identity } from '@/core/auth/identity'
import { useTheme, type ThemeChoice } from '@/shared/lib/theme'
import { SegmentedControl } from '@/shared/ui/segmented-control'
import { cn } from '@/shared/lib/utils'

const THEME_SEGMENTS = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const satisfies readonly { value: ThemeChoice; label: string }[]

export type NotificationCategory =
  | 'Exception raised'
  | 'Escalation triggered'
  | 'Appointment changed'
  | 'Policy changed'

export type NotificationPrefs = Record<NotificationCategory, { push: boolean; email: boolean }>

export const DEFAULT_PREFS: NotificationPrefs = {
  'Exception raised': { push: true, email: false },
  'Escalation triggered': { push: true, email: true },
  'Appointment changed': { push: true, email: false },
  'Policy changed': { push: false, email: true },
}

/** The three settings states (artboards 22-24). */
export type SettingsState = 'default' | 'muted' | 'save-failed'

/**
 * Artboards 22-24.  One route, one continuous scroll, five sections in a fixed order,
 * 720px single column left-aligned in a 24px-padded region.
 *
 * Deliberately small: identity comes from the auth provider and account lifecycle is an
 * admin job, so almost nothing here is editable.  No security section, no danger zone, no
 * sub-navigation, no password form, no MFA, no sessions list, no data export.  All of those
 * were evaluated and rejected for this product -- their absence is the design.
 *
 * **Sections 1 and 5 are Read-only in U83's sense: zero interactive affordance.**  No field
 * boxes, no hover, no focus ring, no cursor change, no greyed-out inputs pretending to be
 * editable.  Plain labelled text.  A read-only view that LOOKS clickable and does nothing
 * reads as broken, not as scoped.
 *
 * **Preferences save immediately.**  No Save button, no sticky save bar.  A failure surfaces
 * inline on the affected row.
 *
 * **No facility swatch beside a facility name** -- accent lives on the rail stripe and in the
 * switcher, and nowhere else.
 */
export function SettingsPage({
  identity,
  state = 'default',
  prefs = DEFAULT_PREFS,
  onPrefChange,
  onRetrySave,
}: {
  identity: Identity
  state?: SettingsState
  prefs?: NotificationPrefs
  onPrefChange?: (category: NotificationCategory, channel: 'push' | 'email', value: boolean) => void
  onRetrySave?: () => void
}) {
  const [muted, setMuted] = useState(state === 'muted')
  const { choice, setChoice } = useTheme()
  const digestId = useId()
  const appearanceId = useId()

  const activeGrant = identity.grants.find((g) => g.role === identity.activeRole)

  return (
    <div className="max-w-180">
      <h1 className="text-h1">Settings</h1>

      {/* SECTION 1 — Personal info (read-only) */}
      <Section title="Personal info">
        <ReadOnlyPairs
          pairs={[
            ['Name', identity.fullName],
            ['Email', identity.email],
            ['Role', activeGrant?.roleLabel ?? identity.activeRoleLabel],
          ]}
        />
        <Helper>These come from your SetuHaul account. Ask an admin to change them.</Helper>
      </Section>

      {/* SECTION 2 — Notification preferences */}
      <Section title="Notification preferences">
        <div className="flex items-center justify-between gap-4 pb-3">
          <span className="text-body">Mute everything</span>
          <Toggle
            checked={muted}
            onChange={setMuted}
            label="Mute everything"
          />
        </div>
        {muted ? (
          <p className="mb-3 text-supporting text-subtle-foreground">
            All notifications are off. Turn this off to use the settings below.
          </p>
        ) : null}
        <hr className="h-px border-0 bg-border" />

        {/* When muted, the category rows dim and their toggles disable, with the reason
            stated inline.  The toggles keep their TRUE values rather than snapping to Off --
            the mute is a switch over the top, not a wipe of what someone configured. */}
        <table className={cn('w-full border-collapse', muted && 'opacity-50')}>
          <thead>
            <tr>
              <Th align="left">Category</Th>
              <Th>Web push</Th>
              <Th>Email</Th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(prefs) as NotificationCategory[]).map((category) => (
              <tr key={category} className="border-t border-border first:border-t-0">
                <td className="py-3 text-left text-body">{category}</td>
                <Td>
                  <Toggle
                    checked={prefs[category].push}
                    disabled={muted}
                    onChange={(v) => onPrefChange?.(category, 'push', v)}
                    label={`Web push — ${category}`}
                    disabledReason="Muted — turn off ‘Mute everything’ to change this"
                  />
                </Td>
                <Td>
                  <Toggle
                    checked={prefs[category].email}
                    disabled={muted}
                    onChange={(v) => onPrefChange?.(category, 'email', v)}
                    label={`Email — ${category}`}
                    disabledReason="Muted — turn off ‘Mute everything’ to change this"
                  />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Artboard 24.  "Nothing has changed" is the load-bearing half of the message, not
            padding: in a system where a click can commit capacity, a user must know a
            failure left no partial state.  Inline on the affected row, never a toast
            carrying the only copy of that fact, and never a silent revert. */}
        {state === 'save-failed' ? (
          <div
            role="alert"
            className="mt-3 flex items-center justify-between gap-4 border-t border-border py-3"
          >
            <span className="flex items-start gap-2 text-supporting text-danger-fg">
              <CircleAlert className="mt-px size-4 shrink-0" aria-hidden="true" />
              That didn’t save — nothing has changed.
            </span>
            <button
              type="button"
              onClick={onRetrySave}
              className="text-supporting text-link underline underline-offset-2 hover:text-primary-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              Try again
            </button>
          </div>
        ) : null}
      </Section>

      {/* SECTION 3 — Email digest.  Dims with its reason when muted, rather than silently
          no-opping when changed. */}
      <Section title="Email digest" className={cn(muted && 'opacity-50')}>
        <div role="radiogroup" aria-labelledby={digestId} className="flex flex-col gap-3">
          <span id={digestId} className="text-supporting font-medium text-muted-foreground">
            Email delivery
          </span>
          <label className="flex items-center gap-2 text-body">
            <input
              type="radio"
              name="digest"
              defaultChecked
              disabled={muted}
              className="size-4 accent-[var(--color-primary)]"
            />
            As it happens
          </label>
          <label className="flex items-center gap-2 text-body">
            <input
              type="radio"
              name="digest"
              disabled={muted}
              className="size-4 accent-[var(--color-primary)]"
            />
            Once daily digest
          </label>
        </div>
        <Helper>
          {muted
            ? 'Everything is muted, so no email is being sent. Turn off “Mute everything” above to change this.'
            : 'Applies to email only. Web push is always sent as it happens.'}
        </Helper>
      </Section>

      {/* SECTION 4 — Appearance */}
      <Section title="Appearance" titleId={appearanceId}>
        <SegmentedControl
          segments={THEME_SEGMENTS}
          value={choice}
          onValueChange={setChoice}
          labelledBy={appearanceId}
          className="max-w-80"
        />
        {/* Corrected 2026-08-26 from "follows you between devices", which was a false
            promise: theme is client-only localStorage per section 7.5.8, with no server
            state and no user_id binding.  A user who read the old copy, set dark on their
            laptop and opened the kiosk to light had been told something untrue. */}
        <Helper>This is saved on this device.</Helper>
      </Section>

      {/* SECTION 5 — Your access (read-only) */}
      <Section title="Your access">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-supporting font-medium text-muted-foreground">Role</span>
            <span className="text-body">{activeGrant?.roleLabel ?? identity.activeRoleLabel}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-supporting font-medium text-muted-foreground">Facilities</span>
            <ul className="flex list-none flex-col gap-1 p-0">
              {identity.facilities.map((f) => (
                <li key={f.id} className="text-body">
                  {f.name}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <Helper>Access is set by an admin. If this looks wrong, contact them.</Helper>
      </Section>
    </div>
  )
}

function Section({
  title,
  titleId,
  className,
  children,
}: {
  title: string
  titleId?: string
  className?: string
  children: React.ReactNode
}) {
  const fallbackId = useId()
  const id = titleId ?? fallbackId
  return (
    <section
      aria-labelledby={id}
      className={cn(
        'mt-6 rounded-lg border border-border bg-card p-4 shadow-raised',
        className,
      )}
    >
      <h2 id={id} className="mb-3 text-h3">
        {title}
      </h2>
      {children}
    </section>
  )
}

/** Read-only: plain labelled text.  No boxes, no hover, no cursor change. */
function ReadOnlyPairs({ pairs }: { pairs: [string, string][] }) {
  return (
    <div className="flex flex-col gap-3">
      {pairs.map(([k, v]) => (
        <div key={k} className="flex flex-col gap-0.5">
          <span className="text-supporting font-medium text-muted-foreground">{k}</span>
          <span className="text-body">{v}</span>
        </div>
      ))}
    </div>
  )
}

function Helper({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-supporting text-subtle-foreground">{children}</p>
}

function Th({ children, align = 'right' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      scope="col"
      className={cn(
        'py-2 text-label uppercase whitespace-nowrap text-subtle-foreground',
        align === 'left' ? 'pl-0 text-left' : 'pl-4 text-right',
      )}
    >
      {children}
    </th>
  )
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="py-3 pl-4 text-right align-middle">{children}</td>
}

/**
 * Toggle carrying state through position AND a text label ("On"/"Off") beside it -- never
 * colour alone.
 *
 * Built on tokens rather than raw values on purpose: the reference mockup hardcoded
 * neutral-300 for the off-track and never redefined it for dark, so in dark mode the OFF
 * state was a light-grey pill on a near-black card -- inverted, and because it reached a
 * primitive, no theme override COULD reach it.  `switch-track-off` fixes that at the token
 * level (implementation-spec 4.2).
 *
 * Disabled is always paired with the reason (components.md section 1).
 */
function Toggle({
  checked,
  onChange,
  label,
  disabled,
  disabledReason,
}: {
  checked: boolean
  onChange?: (next: boolean) => void
  label: string
  disabled?: boolean
  disabledReason?: string
}) {
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        title={disabled ? disabledReason : undefined}
        onClick={() => onChange?.(!checked)}
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full border-0 p-0 transition-colors duration-(--d-base) ease-(--e-out)',
          // Hit area, not appearance.  Measured in a real render (2026-08-31): the visible
          // track is 36x20, so the pointer target was 20px on a `comfortable` surface whose
          // own `--tap` is 44px (`spacing-and-layout.md` density table).  It cleared WCAG 2.2
          // SC 2.5.8 only via the Spacing exception -- neighbouring targets are >24px away --
          // which is a technicality, not a comfortable switch to hit on a tablet.
          //
          // A transparent `::before` extends the button's own hit region to 44x60 without
          // moving, resizing or recolouring one visible pixel.  `-inset-y-3` = 20+24 = 44px
          // tall; the knob keeps using `::after`, so the two do not collide.
          'before:absolute before:-inset-x-3 before:-inset-y-3 before:content-[""]',
          'after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:transition-transform after:duration-(--d-base) after:ease-(--e-out) after:content-[""]',
          'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
          checked ? 'bg-primary' : 'bg-switch-track-off',
          checked ? 'after:translate-x-4' : '',
          disabled
            ? 'cursor-not-allowed bg-disabled after:bg-disabled-foreground'
            : 'cursor-pointer after:bg-switch-knob hover:shadow-[0_0_0_2px_var(--color-border)]',
        )}
      />
      <span className="min-w-[22px] text-left text-supporting text-muted-foreground">
        {checked ? 'On' : 'Off'}
      </span>
    </span>
  )
}
