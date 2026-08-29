import { apiGet, apiPost } from '@/core/http/api'
import type { Dock, DockBlockImpact, DockBlockResult } from './types'

/**
 * Real calls against the endpoints M3/E3.6 shipped (`backend/app/api/v1/routers/planner.py`) plus
 * the one existing ops-portal read the block-dock form's dock select borrows
 * (`backend/app/api/v1/routers/operations.py::dock_snapshot` -- `WAREHOUSE_PLANNER` is inside
 * `OPS_PORTAL_ROLES`, `core/deps.py:42`). No fixture data here -- this file is the one used by
 * the live `/planner` route; `gallery/fixtures.ts` is the separate, explicitly-fixture-only file
 * for `/planner/_states`.
 *
 * Every mutation the backend requires an `Idempotency-Key` for (`planner.py:40-46`, U70) gets one
 * generated with `crypto.randomUUID()`, the same mechanism `features/ops/lib/api.ts` already uses.
 * `end_dock_block` takes none -- `planner.py:110`'s own comment states the catalog names none for
 * it, and this file does not invent one.
 */

export async function fetchDocksForFacility(facilityId: string): Promise<Dock[]> {
  const res = await apiGet<{ docks: Dock[] }>(
    `/api/v1/operations/dock-snapshot?facility_id=${encodeURIComponent(facilityId)}`,
  )
  return res.data.docks
}

export async function fetchDockBlockImpact(
  dockId: string,
  windowStart: string,
  windowEnd: string,
): Promise<DockBlockImpact> {
  const params = new URLSearchParams({ window_start: windowStart, window_end: windowEnd })
  const res = await apiGet<DockBlockImpact>(
    `/api/v1/planner/docks/${encodeURIComponent(dockId)}/block-impact?${params.toString()}`,
  )
  return res.data
}

export async function blockDock(
  dockId: string,
  payload: { window_start: string; window_end: string; reason: string },
): Promise<DockBlockResult> {
  const res = await apiPost<DockBlockResult>(
    `/api/v1/planner/docks/${encodeURIComponent(dockId)}/block`,
    payload,
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function endDockBlock(dockStatusEventId: string): Promise<DockBlockResult> {
  const res = await apiPost<DockBlockResult>(
    `/api/v1/planner/dock-status-events/${encodeURIComponent(dockStatusEventId)}/end`,
    {},
  )
  return res.data
}
