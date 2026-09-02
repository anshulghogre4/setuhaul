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

## The ECS task definition is now a checked-in artifact (#111)

`deploy/ecs-task-definition.json` is the source of truth for what the `setuhaul-api` service
runs. It was pulled read-only from the live `default-setuhaul-api:1` on 2026-09-02
(`aws ecs describe-task-definition --region ap-south-1`) and is that revision verbatim, minus
the server-populated fields you cannot pass back to `RegisterTaskDefinition`
(`taskDefinitionArn`, `revision`, `status`, `requiresAttributes`, `compatibilities`,
`registeredAt`, `registeredBy`), plus three additions:

| Added | Kind | Why |
|---|---|---|
| `JOB_AUTH_TOKEN` | secret ← SSM `/setuhaul/job-auth-token` | #111 — without it both internal job routes answer 503 |
| `JOB_ACTOR_USER_ID=USR-SYSTEM-SWEEPER` | plain env | the sweeper refuses to run without an actor to attribute its `audit_logs` rows to (`SWEEPER_ACTOR_UNCONFIGURED`); the account is seeded by `supabase/migrations/20260823080000_m8_sweeper_finishing.sql` |
| `SENTRY_DSN` | secret ← SSM `/setuhaul/sentry-dsn` | #46 — the same missing-secret class, done in the same revision rather than a second rollout |

The `runtimePlatform` stays `ARM64`/`LINUX`, matching what `deploy_m5_ecs.*` builds
(`docker build --platform linux/arm64`). Do not edit the revision in the console: the next
apply from this file silently reverts you, which is defect 2 above wearing a different hat.

**Region note.** The two new parameters go in **`ap-south-1`**, written as full ARNs
(`arn:aws:ssm:ap-south-1:118490268011:parameter/setuhaul/...`) rather than bare names. The
seven pre-existing secrets use bare names, which is legal — *"If the Systems Manager Parameter
Store parameter exists in the same Region as the task you are launching, then you can use
either the full ARN or name of the parameter"* ([ECS: Pass Systems Manager parameters through
environment variables](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-ssm-paramstore.html))
— but the explicit ARN is what makes the region a reviewable fact in the diff. Do **not** use
`docs/scripts/put_hosting_ssm.py` for these: it is still hard-coded to `--region us-east-1`
(the #45 legacy recorded above), so it would write a region the running task does not read.

**Execution-role permissions — checked, nothing to add.** `ecsTaskExecutionRole` already
carries the AWS managed `AmazonSSMReadOnlyAccess` (`ssm:Describe*`/`Get*`/`List*` on `*`), so
`ssm:GetParameters` on the new parameters is covered (verified read-only 2026-09-02). No
`kms:Decrypt` grant is needed either: all `/setuhaul/*` parameters are `SecureString` under the
AWS-managed key `alias/aws/ssm`, and ECS documents `kms:Decrypt` as *"Required only if your
secret uses a customer managed key and not the default key"*
([ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)).
That is also why the seven existing SecureStrings already resolve today with no KMS statement
anywhere. **If anyone ever re-keys `/setuhaul/*` onto a customer-managed key, this stops being
true** and the role needs `kms:Decrypt` on that key ARN before the next task starts.

## #111 runbook — make the internal jobs actually run

The gap, verified live 2026-09-02: `POST /internal/jobs/expiry-sweep` and
`/internal/jobs/notification-drain` both answered **503 `JOB_AUTH_UNCONFIGURED`** on production,
because the task definition had no `JOB_AUTH_TOKEN` — and nothing called them anyway, because
the #20 EventBridge leg was never built (`aws events list-rules` / `list-api-destinations` /
`aws scheduler list-schedules` in `ap-south-1` all returned empty). Producers wrote outbox rows;
nothing drained them.

Run these once, in order. Steps 1–2 are the only ones that need a fresh `aws login`.

**1. Generate the token and put it in SSM (ap-south-1).**

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"     # do not paste this anywhere else
MSYS_NO_PATHCONV=1 aws ssm put-parameter --region ap-south-1 \
  --name /setuhaul/job-auth-token --type SecureString --value '<token>' --overwrite
```

Put the **same value** in `.env.local`'s `JOB_AUTH_TOKEN`. Three things must agree: the SSM
parameter (what the server gets), `.env.local` (what the runner and the deploy smoke send), and
the EventBridge connection (which step 4 reads *from SSM*, so it cannot drift on its own).

**2. Optionally put the Sentry DSN** (`#46`; skip and use `--skip-sentry` in step 3 if you have
no Sentry project yet — the app treats a blank DSN as "disabled", it does not fail):

```bash
MSYS_NO_PATHCONV=1 aws ssm put-parameter --region ap-south-1 \
  --name /setuhaul/sentry-dsn --type SecureString --value '<dsn>' --overwrite
```

**3. Apply the task definition** (registers a revision, rolls the service, waits, reads back,
then proves the 503 is gone):

```bash
bash deploy/apply_ecs_task_definition.sh                    # add --skip-sentry if step 2 skipped
powershell -ExecutionPolicy Bypass -File deploy\apply_ecs_task_definition.ps1   # PowerShell
```

It refuses to register if any referenced SSM parameter is missing. That preflight is the whole
point: ECS resolves `secrets` at task *start*, so a bad reference is a `ResourceInitializationError`
on every replacement task and the rollout just never stabilises.

**4. Apply the scheduler:**

```bash
bash deploy/eventbridge-scheduler/apply_eventbridge_jobs.sh
powershell -ExecutionPolicy Bypass -File deploy\eventbridge-scheduler\apply_eventbridge_jobs.ps1
```

It refuses to run while the endpoint still answers 503 — scheduling 1440 failed calls a day is
not progress. Do step 3 first.

**5. Verify by hand:**

```bash
python docs/scripts/run_internal_job.py expiry-sweep
python docs/scripts/run_internal_job.py notification-drain
# local backend instead of production:
python docs/scripts/run_internal_job.py expiry-sweep --base http://127.0.0.1:8000
```

The routes are mounted at `/internal/jobs/<name>` with **no `/api/v1` prefix** —
`app.include_router(internal.router)` in `backend/app/main.py` does not add the versioned
prefix the business routers get. `/api/v1/internal/jobs/...` 404s.

**6. From then on it is automatic.** `deploy_m5_ecs.sh`/`.ps1` end with a guarded smoke step
that POSTs `/internal/jobs/expiry-sweep` with your local token and **fails the deploy** on
`JOB_AUTH_UNCONFIGURED`. Without a local token it skips — loudly, in a box, on purpose.

### The scheduler's shape, and why it is not "EventBridge Scheduler"

`TECH_STACK.md` §5/§6 describe this as *EventBridge Scheduler → the FastAPI route*, and #20's
closing comment already flagged that as not buildable. Re-verified against current AWS docs on
2026-09-02:

* EventBridge **Scheduler**'s targets are the templated AWS-service set (CodeBuild, ECS
  `RunTask`, EventBridge `PutEvents`, Lambda, SNS, SQS, Step Functions, …) plus the *universal
  target*, which invokes AWS SDK API operations. An API destination is on neither list, and
  passing an `api-destination` ARN to `CreateSchedule` is rejected with *"Provided Arn is not in
  correct format"*.
  [Templated targets](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-templated.html) ·
  [Target API reference](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_Target.html)
* A **scheduled rule** *can* target an API destination, and one minute is EventBridge's finest
  resolution. *"You can only create scheduled rules using the default event bus."*
  [Creating a scheduled rule](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html)
* The auth header is carried by a **connection** with `API_KEY` authorization, where
  `ApiKeyName` is the literal header name — here `X-SetuHaul-Job-Token`, matching
  `JOB_TOKEN_HEADER` in `backend/app/api/v1/routers/internal.py`. EventBridge stores the value
  in Secrets Manager through its own service-linked role, so the token is never in this repo.
  [Connections](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-target-connection.html) ·
  [API destinations](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations.html)
  (API destinations to public HTTPS endpoints are supported in Asia Pacific (Mumbai).)

So the wiring is:

```
connection  setuhaul-internal-jobs           API_KEY: X-SetuHaul-Job-Token
  -> api destination  setuhaul-expiry-sweep        POST <cloudfront>/internal/jobs/expiry-sweep
  -> api destination  setuhaul-notification-drain  POST <cloudfront>/internal/jobs/notification-drain
       <- scheduled rule  setuhaul-expiry-sweep-every-minute        rate(1 minute), default bus
       <- scheduled rule  setuhaul-notification-drain-every-minute  rate(1 minute), default bus
            via role  setuhaul-eventbridge-jobs-role  (events:InvokeApiDestination)
```

The folder is still named `eventbridge-scheduler/` because that is the design's name for this
leg; the resources inside it are scheduled rules. Rename it only together with `TECH_STACK.md`.

**Why CloudFront and not the ALB directly:** an API destination's `InvocationEndpoint` must
start with `https`, and the `ap-south-1` ALB has a single **HTTP:80** listener (verified
read-only 2026-09-02). CloudFront `E3B1GUEQF3U9U4` fronts it with
`Managed-AllViewerExceptHostHeader`, so `X-SetuHaul-Job-Token` reaches the origin unchanged, and
`Managed-CachingDisabled` means nothing is cached.

**Retry policy, deliberately short.** `MaximumEventAgeInSeconds: 60`, `MaximumRetryAttempts: 2`,
against EventBridge's defaults of 24 hours / 185 attempts. For a job that fires every minute the
correct retry *is the next minute's invocation*; a day-long backlog of stale sweep triggers has
no value and would only fight the live schedule. There is no DLQ for the same reason — a queue
of expired "please sweep" nudges has no consumer. Note the API destination's **5-second client
timeout**; the sweeper is batch-bounded (`EXPIRY_SWEEP_BATCH_LIMIT`) and commits per row exactly
so a timeout mid-batch loses nothing (see the module docstring in `routers/internal.py`).

**To pause without deleting anything:**

```bash
aws events disable-rule --region ap-south-1 --name setuhaul-expiry-sweep-every-minute
aws events disable-rule --region ap-south-1 --name setuhaul-notification-drain-every-minute
```

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
| `deploy_m5_ecs.sh` / `.ps1` | the ECS half of a backend deploy (build ARM64 → ECR → roll → wait → #111 internal-jobs smoke) |
| `ecs-task-definition.json` | #111 — the `default-setuhaul-api` task definition as an artifact; the source of truth for env + secrets |
| `apply_ecs_task_definition.sh` / `.ps1` | register a revision from the above and roll the service (SSM preflight, read-back, 503 smoke) |
| `eventbridge-scheduler/*.json` | #111/#20 — connection, API destinations, scheduled rules, targets and the invoke role for the two once-a-minute internal jobs |
| `eventbridge-scheduler/apply_eventbridge_jobs.sh` / `.ps1` | one-command apply of the above from the checked-in payloads |
| `ecs-express-infra-trust.json`, `ecs-task-execution-trust.json` | trust policies used when the Express Mode roles were created |
| `express-create.json`, `express-primary-container.json` | the ECS Express Mode creation payloads |
| `apply_*.py`, `hotfix_*.py` | one-off, dated migration/hotfix scripts — not part of a routine deploy |
| `deprecated/` | retired artifacts kept for history (e.g. the App Runner creation payload) |

**The AgentCore half of a deploy is not in this folder and must not be run by hand:**
`python docs/scripts/agentcore_deploy.py` — see `AGENTS.md` for why that rule has no exceptions.
