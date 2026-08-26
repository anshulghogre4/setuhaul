import { useState } from 'react'
import { Bell, CircleHelp, Search } from 'lucide-react'

import type { Identity, RoleGrant } from '@/core/auth/identity'
import { FacilitySwitcher } from '@/components/shell/facility-switcher'
import {
  NotificationsPanel,
  type NotificationItem,
  type NotificationsState,
} from '@/components/shell/notifications-panel'
import { UserMenu } from '@/components/shell/user-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/shared/ui/tooltip'

/**
 * Artboards 11-18.  56px.  Facility switcher (left) · global search (centre) ·
 * notifications, help, user menu (right).
 *
 * **The unread count is spoken in the bell's accessible name** ("Notifications, 3 unread"),
 * so the badge is never the only carrier of that fact.
 *
 * **Help is a contact route and nothing more** (U73, artboard 12).  Activating it goes
 * STRAIGHT to contact -- no menu, no popover, no panel, no intermediate choice.  This
 * product has no help centre, no article library and no FAQ; explanations attach to the
 * thing that confuses people, inline, elsewhere.  No badge ever appears on this icon: it is
 * not a feed.
 */
export function TopBar({
  identity,
  notificationsState,
  notifications,
  unreadCount,
  onOpenSearch,
  onFacilityChange,
  onSwitchRole,
  onSignOut,
  onSignOutEverywhere,
  supportHref = 'mailto:support@setuhaul.in',
}: {
  identity: Identity
  notificationsState: NotificationsState
  notifications: NotificationItem[]
  unreadCount: number
  onOpenSearch: () => void
  onFacilityChange: (facilityId: string) => void
  onSwitchRole?: (grant: RoleGrant) => void
  onSignOut?: () => void
  onSignOutEverywhere?: () => void
  supportHref?: string
}) {
  const [bellOpen, setBellOpen] = useState(false)

  return (
    <header className="flex h-14 w-full shrink-0 items-center gap-4 border-b border-input bg-card px-4">
      <FacilitySwitcher
        role={identity.activeRole}
        facilities={identity.facilities}
        activeFacilityId={identity.activeFacilityId}
        canSelectAll={identity.canSelectAllFacilities}
        onChange={onFacilityChange}
      />

      <button
        type="button"
        onClick={onOpenSearch}
        aria-label="Search shipments, appointments, drivers, carriers, facilities"
        className="mx-auto flex h-10 min-w-0 max-w-105 flex-1 items-center gap-2 rounded-md border border-border bg-background px-3 text-left text-body text-subtle-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:border-input focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <Search className="size-4 shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate">
          Search shipments, appointments, drivers, carriers, facilities
        </span>
        <kbd
          aria-hidden="true"
          className="rounded-sm border border-input bg-card px-2 py-1 font-mono text-[11px] leading-none font-medium text-subtle-foreground"
        >
          ⌘&nbsp;K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1">
        <Popover open={bellOpen} onOpenChange={setBellOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={
                unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications, no unread'
              }
              aria-expanded={bellOpen}
              className="relative grid size-8 place-items-center rounded-md text-muted-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <Bell className="size-6" aria-hidden="true" />
              {unreadCount > 0 ? (
                <span
                  aria-hidden="true"
                  // text-primary-foreground, NOT a hardcoded white.  In dark,
                  // interactive-default is blue-500 and white on it is ~3.7:1 -- below AA
                  // for 10px badge text.  The token flips to neutral-950 and passes.
                  className="absolute -top-0.5 -right-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-primary px-1 font-mono text-[10px] leading-4 font-semibold text-primary-foreground"
                >
                  {unreadCount}
                </span>
              ) : null}
            </button>
          </PopoverTrigger>
          <PopoverContent
            align="end"
            sideOffset={8}
            className="w-100 overflow-hidden rounded-md border border-floating-border bg-popover p-0 shadow-floating"
          >
            <NotificationsPanel state={notificationsState} items={notifications} />
          </PopoverContent>
        </Popover>

        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={supportHref}
              aria-label="Contact support"
              className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <CircleHelp className="size-6" aria-hidden="true" />
            </a>
          </TooltipTrigger>
          <TooltipContent>Contact support</TooltipContent>
        </Tooltip>

        <UserMenu
          identity={identity}
          onSwitchRole={onSwitchRole}
          onSignOut={onSignOut}
          onSignOutEverywhere={onSignOutEverywhere}
        />
      </div>
    </header>
  )
}
