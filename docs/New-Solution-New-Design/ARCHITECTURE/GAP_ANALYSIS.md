# SetuHaul — solution design gap analysis

> **What this is**: an adversarial read of `SOLUTION_DESIGN.md` asking *what functional requirements are
> missing*, plus research into requirements a 2026 production system of this shape is expected to carry.
> Distinct from `REQUIREMENTS.md`, which documents what the design *has*.
>
> **Method**: every gap below is **grep-verified** against `SOLUTION_DESIGN.md` — zero occurrences of
> `prompt injection` · `rate limit` · `DPDP` · `GDPR` · `consent` · `retention` · `PII` · `personal data` ·
> `feature flag` · `rollback` · `jailbreak` · `abuse`. Not impressionistic.
>
> Every gap becomes a `NEW`-marked requirement in `REQUIREMENTS.md` so analysis and requirements stay one
> artifact rather than two that drift.

---

## Gaps at a glance

| # | Gap | Severity | Why now |
|---|---|:--:|---|
| 1 | Prompt-injection posture undocumented; rate limits absent | **High** | OWASP LLM01, and the driver chat is an untrusted-text→tool-call path |
| 2 | India DPDP Act — consent, retention, erasure | **High** | Legally binding; core obligations land 13 May 2027 |
| 3 | Rate limiting / abuse protection | **High** | Serves both injection defence and cost control |
| 4 | LLM cost governance | Medium | $5+$5 budget; a runaway loop is a real risk |
| 5 | Release safety — feature flags, rollback, RTO/RPO | Medium | Owner asked how regression is handled; detection exists, recovery doesn't |
| 6 | Multi-language for drivers | Low | Deliberate deferral, but worth restating in an India-deployed driver product |

---

## Gap 1 — Prompt-injection posture

### The finding is unusual: the design is *strong* here, and never says so

**OWASP LLM Top 10 (2026)** keeps **Prompt Injection at LLM01**, and **Excessive Agency escalated to LLM03**
specifically because incidents now cluster around agentic tool-calling. Their prevention guidance is
candid in a way vendor material rarely is:

> *"No reliable prevention mechanism exists today. Input filters degrade against adaptive attackers, and a
> second model asked to police the first is just another model that can be talked around. **What survives
> contact with an attacker is architecture.**"*

Their prescribed architectural controls: **allowlisted tools · scoped credentials · restricted data access
· approval steps for sensitive actions · rate limits · audit logs.**

**SetuHaul already implements five of six — every one built for a correctness reason, none labelled as
security:**

| OWASP control | Existing mechanism | Originally built for |
|---|---|---|
| Allowlisted tools | §7.5.4 — driver allowlist of ~12 of 23 tools | Token efficiency + selection accuracy |
| Scoped credentials / restricted data | **M15** — *"scope is derived from the authenticated identity, never accepted from a client-supplied id"* | Multi-tenancy |
| Approval for sensitive actions | **D6** — *"no code path lets the LLM or a rule confirm"* | Human authority |
| Constrained agency | **M3/M4** — feasibility and ranking are deterministic, in code | Determinism guarantee |
| Audit logs | **M14** + `agent_actions` — *"the AI's own accountability trail"* | Traceability |
| **Rate limits** | ❌ **absent** | — |

### The blast-radius statement worth writing down

A **fully prompt-injected model** in this system:

- **cannot widen its own scope** — the repository ignores client-supplied `facility_id`/`carrier_id` (M15);
- **cannot confirm capacity** — only a human transitions PENDING → CONFIRMED (D6);
- **cannot alter ranking or feasibility** — those never pass through the model (M3/M4);
- **cannot act unobserved** — every tool call is audited (M14).

The worst it achieves is calling an allowlisted read tool within the driver's own scope, or emitting bad
prose — which `voice-and-tone.md`'s templated-not-generated rule already constrains for state messages.

**This is genuine defence-in-depth that no current document claims.** Stating it converts an accidental
strength into a maintained one — a future change that lets the LLM confirm, or accepts a scope id as an
argument, would now visibly break a stated security property rather than quietly removing one.

### The real hole

**Rate limiting is absent** (Gap 3). Without it, injection attempts are unbounded and free to iterate, and
a single driver can exhaust the LLM budget.

### Requirements this creates

- `NEW` — document the injection blast-radius model as a maintained security property.
- `NEW` — per-driver / per-thread rate limits (Gap 3).
- `NEW` — treat any future change that grants the LLM write authority or accepts client-supplied scope as
  a **security regression**, gated in review.

---

## Gap 2 — India DPDP Act 2023 / DPDP Rules 2025

### Applicability is not optional

The product processes personal data of Indian data principals: driver names, phone numbers, declared ETAs,
free-text chat messages, and check-in movement records. **The Act applies to any entity processing the
personal data of individuals in India to offer them goods or services** — including entities based outside
India.

**Zero coverage in `SOLUTION_DESIGN.md`.**

### Obligations that create requirements

| Obligation | Detail |
|---|---|
| **Purpose-specific consent** | Free, specific, informed, unconditional, unambiguous, by **clear affirmative action**. Blanket consent is non-compliant |
| **Privacy notice contents** | Purpose(s) · data categories · **retention periods** · withdrawal mechanism |
| **Erasure** | On purpose fulfilment **or** consent withdrawal, whichever is first — unless another law requires retention |
| **Log retention floor** | **Minimum 1 year** for access logs and processing records, even after purpose completion |
| **Timeline** | Phased; **core business obligations effective 13 May 2027** |

### The architectural tension — flagged prominently because it is unresolved

> **M14 requires every state change to be reconstructable. DPDP requires erasure on purpose fulfilment.**

These pull in opposite directions, and the design has never confronted it. The 1-year log-retention floor
partially reconciles them, but the following are genuinely undecided:

- When a driver withdraws consent, what happens to `chat_messages` — the free-text record of *their own*
  conversation?
- What happens to `agent_actions` and `allocation_decisions`, which reference that driver but exist to make
  a *capacity decision* auditable — arguably a separate purpose with an independent retention basis?
- Does `appointment_history` survive erasure as an operational record, or is it personal data?

**A defensible position exists** — separate *personal* data (name, phone, free text) from *operational
records* (which dock, which interval, which policy version), erase the former and retain the latter
pseudonymised. But it must be **decided and written**, not assumed.

### Requirements this creates

`NEW` — consent capture at driver onboarding · privacy notice with retention periods · erasure request
handling · a documented personal-vs-operational data classification · 1-year minimum log retention ·
retention-period definitions per data category.

---

## Gap 3 — Rate limiting and abuse protection

**Zero coverage.** Does double duty: bounds prompt-injection iteration (Gap 1) *and* protects the LLM
budget (Gap 4).

| Layer | Requirement |
|---|---|
| Per-driver | Messages per minute / hour |
| Per-thread | Turn cap, so one conversation can't loop indefinitely |
| Global | Circuit-breaker-adjacent ceiling on total in-flight LLM calls (`SYSTEM_DESIGN.md` §6.4's bulkhead) |
| **User-visible copy** | `voice-and-tone.md` has **no template** for a rate-limited driver — a gap in the gap |

**Design note**: the limit must be framed as a system state, not an accusation. A driver hitting a limit
during a genuine emergency is a plausible case, and the copy has to hold up there.

---

## Gap 4 — LLM cost governance

`SOLUTION_DESIGN.md`'s 13 "cost" references are the **scheduling churn cost** (`P_churn`, §5.1) — not token
spend. With a **$5 + $5 credit budget** (`TECH_STACK.md`), an unbounded loop is a live operational risk.

| Requirement | Status |
|---|---|
| Bounded loop iterations | **Partially exists** — "bounded manual loop" is stated but **never quantified** |
| Per-conversation token ceiling | Absent |
| Cost observability per turn | Partially — LangSmith traces cost, but no budget alarm |
| Behaviour at budget exhaustion | Absent — does it fail, degrade, or fall back? |

---

## Gap 5 — Release safety: feature flags, rollback, DR

Owner explicitly asked how regression is tackled. **`TESTING_STRATEGY.md` covers detection; nothing covered
recovery** until `SYSTEM_DESIGN.md` §9 was written this pass. Remaining gaps:

| Item | Status |
|---|---|
| Feature flags | Absent — no mechanism to ship a model change or policy change dark |
| Application rollback | Implied (redeploy prior artifact), never stated |
| **Migration rollback** | **Genuinely hard** — the D1 GiST constraint migration cannot be cleanly reversed once data depends on it. Forward-fix only, and that should be explicit |
| **RTO / RPO** | **Undefined.** For the business record of committed capacity, this is a real omission |
| Policy rollback | ✅ Free by design — `policy_versions` is append-only (D7) |

---

## Gap 6 — Multi-language for drivers

Not a defect — a **deliberate deferral** worth restating rather than a gap in the ordinary sense.

U31 locks English UI with i18n-ready structure (copy externalised, ~30% expansion tolerance, locale
formatting). C3 lists Hindi/Hinglish templates as a COULD.

**Worth stating plainly**: in an India-deployed product, the **driver** is the persona least likely to read
English comfortably, and also the one operating under the worst conditions — roadside, time pressure,
one-handed. Of all six surfaces, driver chat has the strongest case for localisation and is the only one
where language is a *usability* rather than a *preference* issue. Deferring is defensible for v1; deferring
without noting that asymmetry is not.

---

## What the design gets right that is worth not losing

An honest gap analysis says what is already strong, so a later change doesn't quietly discard it:

- **The injection blast-radius model** (Gap 1) — accidental, real, and stronger than most systems achieve deliberately.
- **Idempotency keys everywhere** (M9, U70) — makes the entire retry/resilience story safe.
- **Determinism as a testable property** (M4, §10) — byte-identical replay is a rare and valuable guarantee.
- **Templated-not-generated copy** (`voice-and-tone.md`) — would have satisfied India's DLT SMS template
  requirement for free, had SMS stayed (`TECH_STACK.md` §6).
- **Append-only policy versions** (D7) — makes policy rollback trivial where most systems make it terrifying.

---

## Open items

| # | Item |
|---|---|
| 1 | The personal-vs-operational data classification (Gap 2) needs an actual decision, not a stated tension |
| 2 | Rate-limit thresholds are unquantified. **Partially unblocked 2026-08-21** — the model is chosen and measured (`gemini-3.7-flash`: ~1.5 s single-shot, ~7.4 s for a 4-hop turn). What remains is a *policy* decision about acceptable per-driver request rates, not a missing latency profile |
| 3 | RTO/RPO targets need an owner decision; they are a business call, not a technical default |
| 4 | DPDP applicability assumes this reaches production with real driver data — if it stays a classroom build, Gap 2 is documentation-only. **That distinction should be stated explicitly rather than left ambiguous** |
