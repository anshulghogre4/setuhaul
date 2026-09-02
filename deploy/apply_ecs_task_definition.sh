#!/usr/bin/env bash
# Issue #111 -- register deploy/ecs-task-definition.json as a new revision of the
# `default-setuhaul-api` family and point the running service at it.
#
# WHY THIS FILE EXISTS
# The live task definition carried no JOB_AUTH_TOKEN, so BOTH internal job routes
# (POST /internal/jobs/expiry-sweep and /internal/jobs/notification-drain) answered
# 503 JOB_AUTH_UNCONFIGURED on production -- verified live 2026-09-02. The token existed
# only in the owner's .env.local. The same revision also adds SENTRY_DSN (#46's gap),
# because a task-def revision is the unit of change here and doing them separately
# would mean two rollouts for one missing-secret class of defect.
#
# Per deploy/README.md's #92 standing rule: the task definition is now a checked-in
# artifact and this script is the only sanctioned way to apply it. Do not edit the
# revision in the console -- the next apply from this file would silently revert you.
#
# Run from the repo root:  bash deploy/apply_ecs_task_definition.sh
#   --skip-sentry   register without the SENTRY_DSN secret (use only while
#                   /setuhaul/sentry-dsn does not exist yet; #46 ships dark)
#   --no-roll       register the revision but do NOT update the service
#
# Git Bash note (deploy/README.md, from #92): MSYS rewrites leading-slash arguments into
# Windows paths. Every SSM parameter name below starts with "/", so every call that passes
# one is prefixed with MSYS_NO_PATHCONV=1. Dropping that prefix produces a baffling
# ParameterNotFound for a parameter that plainly exists.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
CLUSTER="${ECS_CLUSTER:-default}"
SERVICE="${ECS_SERVICE:-setuhaul-api}"
TASKDEF_FILE="${TASKDEF_FILE:-deploy/ecs-task-definition.json}"
CF_ORIGIN="${SETUHAUL_PUBLIC_ORIGIN:-https://d382h70qmz3ife.cloudfront.net}"
SKIP_SENTRY=0
NO_ROLL=0

for arg in "$@"; do
  case "$arg" in
    --skip-sentry) SKIP_SENTRY=1 ;;
    --no-roll)     NO_ROLL=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -f "$TASKDEF_FILE" ]; then
  echo "Task definition not found at $TASKDEF_FILE -- run this from the repo root." >&2
  exit 1
fi

STAGED="$(mktemp)"
trap 'rm -f "$STAGED"' EXIT

# `aws` on this machine is the NATIVE Windows CLI, but Git Bash hands it MSYS paths
# (/tmp/tmp.abc123). `file:///tmp/...` is not openable by aws.exe, and the failure mode is a
# confusing "Expected: '=', received: ':'" style parse error rather than "file not found".
# cygpath -m produces F:/... which the AWS CLI accepts on Windows. Harmless no-op on Linux.
aws_file_url() {
  if command -v cygpath >/dev/null 2>&1; then printf 'file://%s' "$(cygpath -m "$1")"
  else printf 'file://%s' "$1"; fi
}

if [ "$SKIP_SENTRY" -eq 1 ]; then
  echo "[0/6] --skip-sentry: stripping the SENTRY_DSN secret from the staged payload"
  python - "$TASKDEF_FILE" "$STAGED" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
for c in doc["containerDefinitions"]:
    c["secrets"] = [s for s in c.get("secrets", []) if s["name"] != "SENTRY_DSN"]
json.dump(doc, open(sys.argv[2], "w", encoding="utf-8"), indent=2)
PY
else
  cp "$TASKDEF_FILE" "$STAGED"
fi

echo "[1/6] preflight: every SSM parameter the payload references must already exist"
# This check is the difference between a clean abort and a broken rollout. ECS resolves
# `secrets` at task START; a missing parameter is a ResourceInitializationError on every
# new task, so the service never reaches steady state and `wait services-stable` blocks
# until it times out. Checking first costs one API call per secret.
# --with-decryption is deliberately NOT passed: we only need existence, and asking for the
# plaintext would put production secrets in this terminal's scrollback.
PARAMS="$(python - "$STAGED" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
for c in doc["containerDefinitions"]:
    for s in c.get("secrets", []):
        v = s["valueFrom"]
        print(s["name"], "/" + v.split(":parameter/", 1)[1] if ":parameter/" in v else v)
PY
)"
MISSING=0
while read -r NAME PARAM; do
  [ -z "$NAME" ] && continue
  TYPE="$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --region "$REGION" --name "$PARAM" \
            --query 'Parameter.Type' --output text 2>/dev/null || true)"
  if [ -z "$TYPE" ] || [ "$TYPE" = "None" ]; then
    echo "  MISSING  $NAME  <- $PARAM (region $REGION)"
    MISSING=1
  else
    echo "  ok       $NAME  <- $PARAM ($TYPE)"
  fi
done <<< "$PARAMS"

if [ "$MISSING" -eq 1 ]; then
  cat >&2 <<'MSG'

Refusing to register: at least one referenced SSM parameter does not exist in this region.
Create it first (see the "#111 runbook" section of deploy/README.md), e.g.:

  python -c "import secrets;print(secrets.token_urlsafe(32))"      # generate, keep it secret
  aws ssm put-parameter --region ap-south-1 --name /setuhaul/job-auth-token \
      --type SecureString --value '<the token>' --overwrite

and put the SAME value in .env.local's JOB_AUTH_TOKEN so the local runner and the
EventBridge connection agree. If /setuhaul/sentry-dsn is the only thing missing, re-run
this script with --skip-sentry.
MSG
  exit 1
fi

echo "[2/6] register the new revision (first write this script performs)"
NEW_ARN="$(aws ecs register-task-definition --region "$REGION" \
             --cli-input-json "$(aws_file_url "$STAGED")" \
             --query 'taskDefinition.taskDefinitionArn' --output text)"
if [ -z "$NEW_ARN" ] || [ "$NEW_ARN" = "None" ]; then
  echo "register-task-definition FAILED -- the service was NOT touched" >&2
  exit 1
fi
echo "  registered: $NEW_ARN"

if [ "$NO_ROLL" -eq 1 ]; then
  echo "[3/6] --no-roll: stopping here. Point the service at $NEW_ARN when ready."
  exit 0
fi

echo "[3/6] point the service at the new revision"
aws ecs update-service --region "$REGION" --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$NEW_ARN" \
  --query 'service.deployments[0].{status:status,taskDefinition:taskDefinition}' --output table

echo "[4/6] wait for stability (this is the step that catches a bad secret reference)"
aws ecs wait services-stable --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE"

echo "[5/6] read back what the service is actually running -- never trust an exit code"
LIVE="$(aws ecs describe-services --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE" \
          --query 'services[0].taskDefinition' --output text)"
echo "  service task definition: $LIVE"
aws ecs describe-task-definition --region "$REGION" --task-definition "$LIVE" \
  --query 'taskDefinition.containerDefinitions[0].secrets[].name' --output json

echo "[6/6] prove the regression this issue exists for is closed"
# A 503 JOB_AUTH_UNCONFIGURED here means the token did not reach the container. Any other
# status (401 without a token, 200 with one) means the guard is configured and working.
CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$CF_ORIGIN/internal/jobs/expiry-sweep")"
if [ "$CODE" = "503" ]; then
  echo "STILL 503 from $CF_ORIGIN/internal/jobs/expiry-sweep -- JOB_AUTH_TOKEN did not land." >&2
  echo "Check that the running tasks were replaced (secrets resolve at task start, not live)." >&2
  exit 1
fi
echo "  unauthenticated POST now answers $CODE (401 expected) -- the token is configured."
echo
echo "TASK DEFINITION APPLIED -- $NEW_ARN is live."
echo "Next: docs/scripts/run_internal_job.py expiry-sweep --base $CF_ORIGIN"
