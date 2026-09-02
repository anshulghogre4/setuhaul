#!/usr/bin/env bash
# M5 backend deploy -- ECS half (ap-south-1). 2026-09-01.
# Run from repo root in Git Bash:  bash deploy/deploy_m5_ecs.sh
#
# Prereqs already verified by the coordinator: image setuhaul-api:m5 built locally
# (ARM64, 116MB, from current source at 879e5bd), aws login fresh, ECR repo exists.
# The AgentCore half is separate and runs via docs/scripts/agentcore_deploy.py -- never by hand.
set -euo pipefail
export AWS_DEFAULT_REGION=ap-south-1
ACCT=118490268011
ECR="$ACCT.dkr.ecr.ap-south-1.amazonaws.com"

echo "[1/5] ECR login"
aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR"

echo "[2/5] tag + push (m5 and latest)"
docker tag setuhaul-api:m5 "$ECR/setuhaul-api:m5"
docker tag setuhaul-api:m5 "$ECR/setuhaul-api:latest"
docker push "$ECR/setuhaul-api:m5"
docker push "$ECR/setuhaul-api:latest"

echo "[3/5] verify the pushed image manifest exists (the deleted-ECR incident's lesson)"
aws ecr describe-images --repository-name setuhaul-api \
  --image-ids imageTag=latest --query 'imageDetails[0].imagePushedAt' --output text

echo "[4/5] roll the service"
aws ecs update-service --cluster default --service setuhaul-api \
  --force-new-deployment --query 'service.deployments[0].{status:status,desired:desiredCount}' --output table

echo "[5/5] wait for stability (this is the step that catches a CannotPullContainerError)"
aws ecs wait services-stable --cluster default --services setuhaul-api
echo "ECS DEPLOY COMPLETE -- service stable on the new image."

# ---------------------------------------------------------------------------------------
# POST-DEPLOY SMOKE (issue #111, added 2026-09-02): the internal-jobs guard.
#
# On 2026-09-02 both internal job routes answered 503 JOB_AUTH_UNCONFIGURED on production for
# an unknown length of time, because the task definition simply had no JOB_AUTH_TOKEN. Nothing
# errored -- the service was healthy, /health/live was 200, the deploy "succeeded". The only
# symptom was that the outbox never drained and no expiry escalations were ever produced.
# This step turns that silent class of defect into a failed deploy.
#
# It is guarded, not mandatory: the token is deliberately not in the repo, so a machine that
# does not have it locally cannot run this check. That skip is LOUD on purpose -- a quiet skip
# would recreate exactly the false confidence this step exists to remove.
CF_ORIGIN="${SETUHAUL_PUBLIC_ORIGIN:-https://d382h70qmz3ife.cloudfront.net}"
SMOKE_TOKEN="${JOB_AUTH_TOKEN:-}"
if [ -z "$SMOKE_TOKEN" ] && [ -f .env.local ]; then
  # \042 = double quote, \047 = single quote, \r for CRLF files -- tr's octal escapes keep
  # this readable instead of a nest of shell quoting.
  SMOKE_TOKEN="$(sed -n 's/^JOB_AUTH_TOKEN=//p' .env.local | head -1 | tr -d '\042\047\r')"
fi

if [ -z "$SMOKE_TOKEN" ]; then
  echo
  echo "########################################################################"
  echo "# SMOKE SKIPPED: no JOB_AUTH_TOKEN in this environment or .env.local.  #"
  echo "# The deploy is NOT verified against issue #111's regression -- the    #"
  echo "# internal job routes could be answering 503 and you would not know.   #"
  echo "# Verify by hand:                                                      #"
  echo "#   python docs/scripts/run_internal_job.py expiry-sweep               #"
  echo "########################################################################"
else
  echo
  echo "[smoke] POST $CF_ORIGIN/internal/jobs/expiry-sweep (issue #111 regression guard)"
  SMOKE_BODY="$(curl -s -w '\n%{http_code}' -X POST "$CF_ORIGIN/internal/jobs/expiry-sweep" \
                  -H "X-SetuHaul-Job-Token: $SMOKE_TOKEN")"
  SMOKE_CODE="$(printf '%s' "$SMOKE_BODY" | tail -1)"
  SMOKE_JSON="$(printf '%s' "$SMOKE_BODY" | sed '$d')"
  echo "  status $SMOKE_CODE"
  case "$SMOKE_JSON" in
    *JOB_AUTH_UNCONFIGURED*)
      echo "  $SMOKE_JSON" >&2
      echo "DEPLOY FAILED THE #111 SMOKE: the running task has no JOB_AUTH_TOKEN." >&2
      echo "Fix: bash deploy/apply_ecs_task_definition.sh (the token is an SSM-sourced secret" >&2
      echo "on the task definition; a new image alone will never add it)." >&2
      exit 1 ;;
  esac
  if [ "$SMOKE_CODE" != "200" ]; then
    echo "  $SMOKE_JSON" >&2
    echo "DEPLOY FAILED THE #111 SMOKE: expected 200, got $SMOKE_CODE." >&2
    exit 1
  fi
  echo "  $SMOKE_JSON"
  echo "  internal jobs are callable on production."
fi
