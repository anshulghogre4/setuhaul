import { Construction } from 'lucide-react'

import { EmptyState } from '@/shared/ui/empty-state'

/**
 * The honest stub for a tab whose entire live path is flag-gated off
 * (`plannerQueueLiveEnabled` / `dockBoardEnabled`) rather than merely one action inside it --
 * same posture as E5.1/E5.2's Inactive controls, scaled up to a whole region because there is no
 * queue row or occupancy bar to render at all without the backend gap closing first.
 *
 * Never a fake queue or a fake board -- `AGENTS.md`: "Never invent shipment, ETA, dock,
 * appointment, capacity, or operational data."
 */
export function NotYetAvailable({ title, body }: { title: string; body: string }) {
  return <EmptyState icon={Construction} title={title} body={body} />
}
