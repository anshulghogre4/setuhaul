# `deploy/` — SetuHaul deployment artifacts

## The standing rule (issue #92, adopted 2026-09-02)

**The IAM grants SetuHaul's runtime and BFF depend on are version-controlled artifacts. Applying
one by hand to a live role is forbidden.**

This is not a style preference. On 2026-09-01 chat was down in production for two reasons, both of
which were hand-applied policies that had quietly stopped being true:

| # | Defect | Symptom | Root cause |
|---|---|---|---|
| 1 | `setuhaul-bff-task-role`'s `SetuHaulInvokeAgentCore` allowed `InvokeAgentRuntime` only on the **retired `us-east-1`** runtime | every BFF invoke → `AccessDeniedException` → **503** | E7.1 moved the runtime to `ap-south-1`; nobody re-pointed the grant |
| 2 | The AgentCore runtime execution role lost its `/setuhaul/*` SSM read grant | `ssm hydrate miss` ×8, no `DATABASE_URL`, no LLM key → **502** | the wrapper's own CloudFormation deploy **recreated the role**, silently wiping a policy that had been attached by hand |

Defect 2 is the one to internalise: nothing failed. `agentcore deploy` reported success, the stack
updated cleanly, the container booted. The grant simply ceased to exist, because a hand-patched
inline policy on an IaC-managed role survives exactly until the next stack update.

**Where each grant lives now:**

| Grant | Owner | File |
|---|---|---|
| Runtime execution role → `ssm:GetParameter` on `/setuhaul/*` | CDK (auto-applied on every wrapper deploy) | `agentcore/cdk/lib/cdk-stack.ts` (`SetuHaulSsmHydrateRead`) |
| BFF task role → `bedrock-agentcore:InvokeAgentRuntime` | checked-in JSON + one-command apply | `deploy/bff-task-role-invoke-policy.json` |

If a grant is missing, **change the artifact and re-apply the artifact**. Do not
`aws iam put-role-policy` from your shell history, and do not edit the policy in the console.

### One cleanup step is still owed, after the next AgentCore deploy

Verified read-only on 2026-09-02: the runtime execution role
(`AgentCore-SetuHaulAgent-d-ApplicationAgentSetuHaulA-WhTuGOyFcRID`) currently carries **two**
inline policies —

* `ApplicationAgentSetuHaulAgentRuntimeExecutionRoleDefaultPolicy…` — CDK-managed, and it contains
  **no SSM actions at all** today. That is the gap `cdk-stack.ts` now closes.
* `SetuHaulSsmHydrate` — the hand-applied hot-fix from the incident. Still the only thing keeping
  chat alive, and still the time bomb: it is not in any template, so the next stack update can
  remove it exactly as the last one did.

So after the next `python docs/scripts/agentcore_deploy.py`:

1. Confirm the CDK grant landed (read-only):
   ```bash
   aws iam get-role-policy \
     --role-name AgentCore-SetuHaulAgent-d-ApplicationAgentSetuHaulA-WhTuGOyFcRID \
     --policy-name ApplicationAgentSetuHaulAgentRuntimeExecutionRoleDefaultPolicyE49DD353 \
     --query 'PolicyDocument.Statement[?Sid==`SetuHaulSsmHydrateRead`]' --output json
   ```
   (the DefaultPolicy's logical-id suffix can change if the construct tree changes — list the
   role's policies first if that name 404s).
2. **Only once step 1 returns the statement**, delete the orphan:
   `aws iam delete-role-policy --role-name <role> --policy-name SetuHaulSsmHydrate`.

Order matters. Deleting first would take chat down for the window between the two commands, and
the whole point of #92 is to stop doing that to ourselves.

---

## Why the two grants are handled differently

They are not managed by the same thing, and pretending otherwise would be worse than the split.

* **AgentCore is CDK.** `agentcore deploy` runs `npm run build` (tsc) inside `agentcore/cdk/` and
  then synthesises and deploys the CloudFormation stack `AgentCore-SetuHaulAgent-default`. So a
  grant added to `lib/cdk-stack.ts` is picked up automatically by the next
  `python docs/scripts/agentcore_deploy.py` run — no separate `cdk deploy` step.
* **ECS is not.** The backend runs on **AWS ECS Express Mode**, created through raw AWS APIs and
  the `deploy/*.json` payloads in this folder. There is no Terraform/CDK/CloudFormation stack that
  owns `setuhaul-bff-task-role`, so there is nowhere to *put* the invoke grant as real IaC today.
  The checked-in policy plus `apply_bff_invoke_policy.{sh,ps1}` is the honest second-best: a
  reviewable, diffable artifact and a one-command restore, instead of institutional memory.

## Restore the BFF invoke grant

```bash
bash deploy/apply_bff_invoke_policy.sh                     # Git Bash
powershell -File deploy\apply_bff_invoke_policy.ps1        # PowerShell
```

Both print the current policy, put the checked-in one, and read it back.

### Verify it without changing anything

```bash
aws iam get-role-policy \
  --role-name setuhaul-bff-task-role \
  --policy-name SetuHaulInvokeAgentCore \
  --query 'PolicyDocument' --output json
```

The deploy wrapper now runs this check for you after every deploy and fails loudly if the policy
does not mention the runtime ARN it just deployed (`check_bff_invoke_grant` in
`docs/scripts/agentcore_deploy.py`).

### Provenance of `bff-task-role-invoke-policy.json`

**This file is the live policy, not a reconstruction.** It was pulled read-only with
`aws iam get-role-policy` on 2026-09-02 and is semantically identical to what
`setuhaul-bff-task-role` carries in production right now (verified by parsing both and comparing;
the only textual difference is CRLF line endings). That includes the `runtime/<id>/*` suffixes,
which is how the hot-fix covered the endpoint-qualified invoke the BFF actually makes
(`qualifier="DEFAULT"` in `backend/app/assistant/agentcore_runtime.py`).

Re-run the comparison any time — it is read-only and takes a second:

```bash
aws iam get-role-policy --role-name setuhaul-bff-task-role \
  --policy-name SetuHaulInvokeAgentCore --query 'PolicyDocument' --output json > live-policy.json
python -c "import json;print(json.load(open('live-policy.json'))==json.load(open('deploy/bff-task-role-invoke-policy.json')))"
```

If that prints `False`, someone changed the live policy by hand — reconcile *into this file*, then
re-apply from it.

## Region-migration checklist (E7.1 is not finished)

When the AgentCore runtime moves region, **four** things must move with it. Missing the second one
is what caused defect 1.

1. `agentcore/aws-targets.json` — the deploy target's `region`.
2. `deploy/bff-task-role-invoke-policy.json` — add the new runtime ARN, and keep the old one only
   while it is genuinely the rollback target. Re-apply with the script.
3. `AGENTCORE_RUNTIME_ARN` on the ECS task definition (the BFF derives its client region from this
   ARN — `_region_from_arn`).
4. `agentcore/agentcore.json`'s `AWS_REGION` env var — this is what the runtime hydrates SSM from
   (`agentcore_main.py::_hydrate_ssm_into_env`), and the SSM parameters must exist in that region.

**Current, deliberately-unfinished state (verified live read-only, 2026-09-02):** the runtime reads
SSM from `ap-south-1`; the same eight `/setuhaul/*` parameters exist in **both** `ap-south-1` and
`us-east-1`, all `SecureString` under the AWS-managed key `alias/aws/ssm`; and the CDK grant covers
both regions so a rollback does not lose its secrets. Drop the `us-east-1` half when E7.1's
decommission item (#45) closes.

> **Two live divergences found while verifying this, neither fixed here:**
>
> 1. `docs/scripts/put_hosting_ssm.py` still writes parameters to **`us-east-1` only** (hard-coded
>    `--region us-east-1`). Rotating a secret with that script today updates a region the live
>    runtime does not read — the new value would silently never reach production.
> 2. `agentcore_main.py::_SSM_ENV` reads **nine** names, but only eight exist in SSM.
>    `/setuhaul/gcp-project` and `/setuhaul/gcp-sa-key` (added for #103's Gemini credential ladder)
>    are **absent from both regions**, so every cold start logs `ssm hydrate miss` for them. The
>    `/setuhaul/*` grant already covers them, so creating them is all that is needed — but until
>    someone does, the Vertex credential path depends on whatever else is in the environment.
>
> Both are outside #92's scope. They are recorded here so the next person does not rediscover them
> during an outage.

## Operational notes worth keeping (from #92)

* `aws login` OAuth grants are short-lived — they expired three times in one session mid-operation.
  Assume the session can die between two steps of any script here.
* Git Bash mangles leading-slash AWS arguments via MSYS path conversion. Prefix with
  `MSYS_NO_PATHCONV=1` when passing anything path-shaped (log group names, some ARNs).
* **AgentCore hydrates SSM per cold start.** After an IAM fix, a *warm* container keeps its
  half-hydrated environment until it recycles — it will keep failing and that is not evidence the
  fix failed. A fresh session (or a different user) proves it immediately.

## Files in this folder

| File | What it is |
|---|---|
| `bff-task-role-invoke-policy.json` | #92 — the BFF task role's AgentCore invoke grant, as an artifact |
| `apply_bff_invoke_policy.sh` / `.ps1` | one-command restore of the above |
| `deploy_m5_ecs.sh` / `.ps1` | the ECS half of a backend deploy (build ARM64 → ECR → roll → wait) |
| `ecs-express-infra-trust.json`, `ecs-task-execution-trust.json` | trust policies used when the Express Mode roles were created |
| `express-create.json`, `express-primary-container.json` | the ECS Express Mode creation payloads |
| `apply_*.py`, `hotfix_*.py` | one-off, dated migration/hotfix scripts — not part of a routine deploy |
| `deprecated/` | retired artifacts kept for history (e.g. the App Runner creation payload) |

**The AgentCore half of a deploy is not in this folder and must not be run by hand:**
`python docs/scripts/agentcore_deploy.py` — see `AGENTS.md` for why that rule has no exceptions.
