/**
 * `bulk_confirm`'s single `snapshot_hash`, composed from the per-row ones the queue already
 * handed us.
 *
 * ## This is not a client-side approximation of a server check
 *
 * That distinction matters, because `implementation-spec.md` section 7 item 9 says in terms: *"the
 * server-side predicate re-check at press time is the whole point; do not ship a client-side
 * approximation as a stopgap."* This composes an **identity token**, not a verdict. The five
 * safe-batch predicates are still evaluated server-side at press time by
 * `allocation.evaluate_safe_batch_predicates`, and nothing here influences them.
 *
 * `bulk_confirm` takes `appointment_ids[]` and exactly one `snapshot_hash`, so the batch token has
 * to be derivable by the client from the per-row tokens -- `snapshot.py::batch_snapshot_hash`'s
 * own docstring states that as the design. Each row's `snapshot_hash` is still round-tripped
 * verbatim; only their *composition* happens here.
 *
 * ## Byte-compatibility with the server, verified rather than assumed
 *
 * `batch_snapshot_hash` canonicalises with Python's
 * `json.dumps(..., sort_keys=True, separators=(",", ":"))` over `{"v": 1, "rows": ["<id>:<hash>"]}`
 * and hashes the UTF-8 bytes with SHA-256. Two details would silently break a naive port:
 *
 *  1. `sort_keys=True` emits `"rows"` **before** `"v"`. `JSON.stringify` preserves insertion
 *     order for string keys, so the object literal below is written in that order deliberately --
 *     writing `{ v: 1, rows: [...] }` would produce a different string and a different digest.
 *  2. `separators=(",", ":")` is exactly `JSON.stringify`'s own spacing, so no post-processing is
 *     needed. (Python's default would have inserted spaces; the server does not use the default.)
 *
 * Verified 2026-08-29 by running both implementations on the same input: Python emitted
 * `{"rows":["APT-1:aa","APT-2:bb"],"v":1}` / `c98a7328...8ead` and this canonicalisation produced
 * the byte-identical string and the identical digest.
 *
 * One residual assumption, stated rather than buried: Python's `sorted()` compares by Unicode code
 * point and JavaScript's default string comparison by UTF-16 code unit. These agree for every
 * appointment id this product generates (`ids.new_id` emits ASCII `APT-` + hex), and would only
 * diverge on ids containing astral-plane characters, which none do.
 */

/**
 * `crypto.subtle` is **secure-context only** -- MDN, `Crypto.subtle`: *"This feature is available
 * only in secure contexts (HTTPS), in some or all supporting browsers"*, verified against the live
 * page 2026-08-29. `localhost` counts as secure, and production is HTTPS behind Vercel, so this is
 * available on every path this app actually runs on. It is checked anyway because the failure mode
 * of assuming it -- sending a wrong batch token -- would make the server report
 * `snapshot_hash_matched: false` on a batch that had not moved at all, i.e. it would manufacture a
 * false "the board changed under you" every single time.
 */
export function batchHashAvailable(): boolean {
  return typeof crypto !== 'undefined' && typeof crypto.subtle?.digest === 'function'
}

export async function batchSnapshotHash(rowHashes: Record<string, string>): Promise<string> {
  const pairs = Object.entries(rowHashes).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
  // Key order is load-bearing -- see (1) in this file's header. Do not reorder these two.
  const canonical = JSON.stringify({
    rows: pairs.map(([appointmentId, rowHash]) => `${appointmentId}:${rowHash}`),
    v: 1,
  })
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical))
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}
