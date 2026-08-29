/**
 * Ops-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature, per E5.1's precedent
 * (`features/driver/lib/flags.ts`) -- so it is obvious what removes a flag rather than obvious
 * what it hides. All three below default OFF and each names the issue that has to close before
 * it can flip.
 */

/**
 * Gates "Request sequencer proposal" (prompt 14's only action on a capacity incident) and the
 * post-request handoff state ("Proposal requested · routed to Planner queue").
 *
 * **Default OFF, and it must stay off until issue #54 lands.**
 *
 * Why (issue #54, G1, filed 2026-08-29): `request_sequencer_proposal` does not exist --
 * `SOLUTION_DESIGN.md` section 7.5.5 defines it as a thin delegate to section 7.5.3's
 * `propose_facility_schedule`, and section 7.5.3 (the Sequencer) is entirely unbuilt, tracked
 * separately as issue #49. There is nothing to request a proposal FROM. The collapsed incident
 * row, its expanded read-only affected-shipment list, and the scope-denied state all render
 * regardless -- only the action button and its handoff state are behind this flag.
 *
 * **Exit criterion:** issue #54 (and its parent #49) closed, then flip to `true` and delete the
 * flag and its one call site in `capacity-incident-row.tsx`.
 */
export const sequencerProposalEnabled = false

/**
 * Gates the takeover thread composer's Send action (prompt 8, prompt 12's second gate).
 *
 * **Default OFF, and it must stay off until issue #55 lands.**
 *
 * Why (issue #55, G2, filed 2026-08-29): no tool or endpoint anywhere in `backend/app/` writes a
 * `chat_messages` row with `sender_type = 'OPERATIONS'` -- grepped, zero hits. `take_over_thread`
 * (SS7.5.5) is real and IS wired here for real (it sets `thread_status='ESCALATED'` and posts the
 * SYSTEM join divider), but the composer that takeover enables has nowhere to send a coordinator's
 * own reply. Rendering an enabled composer that silently drops what is typed into it would be
 * exactly the "looks functional, does nothing" failure this flag exists to prevent -- the composer
 * renders Read-only (per `components.md` foundations section 18, not Disabled) with the reason
 * named, instead.
 *
 * **Exit criterion:** issue #55 closed (a real send path exists), then flip to `true`.
 */
export const sendAsOperationsEnabled = false

/**
 * Gates the co-pilot's active capabilities (Summarise / Fetch context / Draft a reply --
 * prompts 12 and 13). The Inactive state (prompt 11) is NOT behind this flag; it ships
 * unconditionally, since it is genuinely buildable today (a real focusable control that explains
 * itself, Fork B) and is what a coordinator sees most of the time regardless.
 *
 * **Default OFF, and it must stay off until issue #57 lands.**
 *
 * Why (issue #57, G4 / Fork A, filed 2026-08-29): the co-pilot's three capabilities have no
 * backend contract at all -- no endpoint, no request shape, no error taxonomy, no owner.
 * `SOLUTION_DESIGN.md` section 7.5.5 deliberately excludes them from its tool table on the
 * grounds they are "LLM-assisted actions... not new mutating tools," which is sound reasoning
 * for mutation but leaves nothing to call. Building the Active-state UI against a contract that
 * does not exist would mean either faking a response (forbidden by this build's own brief) or
 * silently inventing an endpoint (forbidden by `AGENTS.md`: the LLM orchestrates typed tools it
 * does not invent client-side).
 *
 * **Exit criterion:** issue #57 closed with a scoped, owner-approved contract (Fork A option (a)
 * or (b) in `implementation-spec.md` section 6), then flip to `true`.
 */
export const copilotActiveEnabled = false
