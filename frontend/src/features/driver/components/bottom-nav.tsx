import { MessageSquare, User } from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { copy } from '../lib/copy'
import './bottom-nav.css'

/**
 * Two items. Threads and Profile — `screens.md` section 1's own footer, and nothing else:
 * *"Two screens and a profile. Nothing else."*
 *
 * **Icon-only controls are forbidden on the driver surface** (`iconography.md`: *"an icon
 * augments a label; it does not replace one in this product"*), so both items carry their word.
 * That is also what makes the 56px height honest rather than a large empty box.
 *
 * `aria-current="page"` comes from `NavLink` and is what the CSS keys off — see `bottom-nav.css`
 * on why that specific coupling.
 */
export function BottomNav() {
  return (
    <nav
      aria-label="Driver"
      className="driver-nav flex shrink-0 items-stretch border-t border-border bg-card"
    >
      <Item to="/driver" icon={MessageSquare} label={copy.navThreads} />
      <Item to="/driver/profile" icon={User} label={copy.navProfile} />
    </nav>
  )
}

function Item({
  to,
  icon: Icon,
  label,
}: {
  to: string
  icon: typeof MessageSquare
  label: string
}) {
  return (
    <NavLink
      to={to}
      // `end` so /driver does not stay marked current while the driver is inside
      // /driver/profile -- react-router matches prefixes by default and the nav would show two
      // active items, which is worse than none.
      end
      className="driver-nav-item flex flex-1 flex-col items-center justify-center gap-0.5 text-body focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
    >
      <Icon size={20} strokeWidth={2} aria-hidden="true" />
      {label}
    </NavLink>
  )
}
