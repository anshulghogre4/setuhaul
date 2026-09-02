#!/usr/bin/env bash
# Issue #111 / the #20 EventBridge leg -- create the once-a-minute triggers for the two
# internal job routes from the checked-in payloads in this folder.
#
# WHY THIS SHAPE (verified against current AWS docs 2026-09-02, not from memory)
# EventBridge *Scheduler* cannot call an HTTPS endpoint. Its targets are the templated
# AWS-service set (CodeBuild, ECS RunTask, EventBridge PutEvents, Lambda, SNS, SQS, Step
# Functions, ...) plus the universal target, which invokes AWS SDK API operations -- an API
# destination is on neither list, and passing an api-destination ARN to CreateSchedule is
# rejected with "Provided Arn is not in correct format".
#   https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-templated.html
#   https://docs.aws.amazon.com/scheduler/latest/APIReference/API_Target.html
# The documented way to hit an HTTPS endpoint on a schedule with a custom auth header is an
# EventBridge *scheduled rule* whose target is an API destination backed by a connection:
#   connection (API_KEY: header name + value, stored by EventBridge in Secrets Manager)
#     -> API destination (POST https://<cloudfront>/internal/jobs/<name>)
#       -> scheduled rule rate(1 minute) on the DEFAULT bus -> that destination
#   https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations.html
#   https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-target-connection.html
#   https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html
#     ("You can only create scheduled rules using the default event bus"; "the minimum
#      precision for a schedule is one minute"; API destination is an offered target type)
# API destinations to public HTTPS endpoints are supported in Asia Pacific (Mumbai).
#
# Why CloudFront and not the ALB: API destination endpoints must start with https, and the
# ap-south-1 ALB has a single HTTP:80 listener (verified read-only 2026-09-02). CloudFront
# fronts it with Managed-AllViewerExceptHostHeader, so the X-SetuHaul-Job-Token header
# reaches the origin unchanged, and Managed-CachingDisabled means nothing is cached.
#
# Run from the repo root:  bash deploy/eventbridge-scheduler/apply_eventbridge_jobs.sh
#   --skip-live-check   apply even if the endpoint is still answering 503 (not recommended)
#
# Git Bash note (deploy/README.md, from #92): MSYS rewrites leading-slash arguments. The SSM
# parameter name below is prefixed with MSYS_NO_PATHCONV=1 for that reason.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGIN="${SETUHAUL_PUBLIC_ORIGIN:-https://d382h70qmz3ife.cloudfront.net}"
ROLE_NAME="setuhaul-eventbridge-jobs-role"
POLICY_NAME="SetuHaulInvokeInternalJobApiDestinations"
CONNECTION_NAME="setuhaul-internal-jobs"
SKIP_LIVE_CHECK=0

for arg in "$@"; do
  case "$arg" in
    --skip-live-check) SKIP_LIVE_CHECK=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# `aws` on this machine is the NATIVE Windows CLI, but Git Bash hands it MSYS paths
# (/tmp/tmp.abc123, /f/Preparation/...). `file:///tmp/...` is not openable by aws.exe, and the
# failure mode is a confusing parse error rather than "file not found". cygpath -m produces
# F:/... which the AWS CLI accepts on Windows. Harmless no-op on Linux.
aws_file_url() {
  if command -v cygpath >/dev/null 2>&1; then printf 'file://%s' "$(cygpath -m "$1")"
  else printf 'file://%s' "$1"; fi
}

# render <template> <output> -- substitutions come from $SUBST_JSON in the ENVIRONMENT, never
# from argv, because argv is world-readable in a process listing and one of the values is the
# job token.
render() {
  python - "$1" "$2" <<'PY'
import json, os, sys
text = open(sys.argv[1], encoding="utf-8").read()
for key, value in json.loads(os.environ["SUBST_JSON"]).items():
    text = text.replace(key, value)
open(sys.argv[2], "w", encoding="utf-8").write(text)
PY
}

json_field() { python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))[sys.argv[2]])" "$1" "$2"; }

echo "[1/8] refuse to schedule against a route that is still refusing"
# 1440 invocations a day into a 503 is not a schedule, it is a metrics generator. The
# task-definition half of #111 (deploy/apply_ecs_task_definition.sh) must land first.
CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$ORIGIN/internal/jobs/expiry-sweep")"
echo "  unauthenticated POST $ORIGIN/internal/jobs/expiry-sweep -> $CODE"
if [ "$CODE" = "503" ] && [ "$SKIP_LIVE_CHECK" -eq 0 ]; then
  echo "  503 JOB_AUTH_UNCONFIGURED: JOB_AUTH_TOKEN is not on the running task yet." >&2
  echo "  Run deploy/apply_ecs_task_definition.sh first. (--skip-live-check to override.)" >&2
  exit 1
fi

echo "[2/8] read the job token from SSM (single source of truth; never printed)"
TOKEN="$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --region "$REGION" \
           --name /setuhaul/job-auth-token --with-decryption \
           --query 'Parameter.Value' --output text)"
if [ -z "$TOKEN" ] || [ "$TOKEN" = "None" ]; then
  echo "/setuhaul/job-auth-token is missing in $REGION -- see deploy/README.md #111 runbook." >&2
  exit 1
fi
echo "  got ${#TOKEN} characters from /setuhaul/job-auth-token"

echo "[3/8] the invoke role EventBridge assumes to call the API destinations"
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "  role exists -- refreshing its trust policy from the artifact"
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" \
    --policy-document "$(aws_file_url "$HERE/invoke-role-trust.json")"
else
  aws iam create-role --role-name "$ROLE_NAME" \
    --description "Issue #111: lets EventBridge scheduled rules invoke the SetuHaul internal-job API destinations." \
    --assume-role-policy-document "$(aws_file_url "$HERE/invoke-role-trust.json")" \
    --query 'Role.Arn' --output text
fi
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
  --policy-document "$(aws_file_url "$HERE/invoke-role-policy.json")"

echo "[4/8] the connection (API_KEY -> X-SetuHaul-Job-Token header)"
# EventBridge stores ApiKeyValue in Secrets Manager on its own side, through its service-linked
# role. The token is never written into this repo, the rule, or the API destination.
export TOKEN
export SUBST_JSON
SUBST_JSON="$(python -c 'import json,os;print(json.dumps({"__JOB_AUTH_TOKEN__": os.environ["TOKEN"]}))')"
render "$HERE/connection.json" "$WORK/connection.json"
unset SUBST_JSON TOKEN
if aws events describe-connection --region "$REGION" --name "$CONNECTION_NAME" >/dev/null 2>&1; then
  echo "  connection exists -- updating its API key to the current SSM value"
  aws events update-connection --region "$REGION" \
    --cli-input-json "$(aws_file_url "$WORK/connection.json")" --query 'ConnectionArn' --output text
else
  aws events create-connection --region "$REGION" \
    --cli-input-json "$(aws_file_url "$WORK/connection.json")" --query 'ConnectionArn' --output text
fi
rm -f "$WORK/connection.json"

echo "  waiting for the connection to reach AUTHORIZED"
for _ in $(seq 1 30); do
  STATE="$(aws events describe-connection --region "$REGION" --name "$CONNECTION_NAME" \
             --query 'ConnectionState' --output text)"
  echo "    state=$STATE"
  [ "$STATE" = "AUTHORIZED" ] && break
  sleep 2
done
CONN_ARN="$(aws events describe-connection --region "$REGION" --name "$CONNECTION_NAME" \
              --query 'ConnectionArn' --output text)"

echo "[5/8] the two API destinations"
DEST_EXPIRY=""
DEST_DRAIN=""
for JOB in expiry-sweep notification-drain; do
  DEST_FILE="$HERE/api-destination-$JOB.json"
  DEST_NAME="$(json_field "$DEST_FILE" Name)"
  export CONN_ARN SUBST_JSON
  SUBST_JSON="$(python -c 'import json,os;print(json.dumps({"__CONNECTION_ARN__": os.environ["CONN_ARN"]}))')"
  render "$DEST_FILE" "$WORK/dest.json"
  if aws events describe-api-destination --region "$REGION" --name "$DEST_NAME" >/dev/null 2>&1; then
    aws events update-api-destination --region "$REGION" --cli-input-json "$(aws_file_url "$WORK/dest.json")" >/dev/null
  else
    aws events create-api-destination --region "$REGION" --cli-input-json "$(aws_file_url "$WORK/dest.json")" >/dev/null
  fi
  ARN="$(aws events describe-api-destination --region "$REGION" --name "$DEST_NAME" \
           --query 'ApiDestinationArn' --output text)"
  echo "  $DEST_NAME -> $ARN"
  if [ "$JOB" = "expiry-sweep" ]; then DEST_EXPIRY="$ARN"; else DEST_DRAIN="$ARN"; fi
done

echo "[6/8] the two scheduled rules (rate(1 minute), default bus)"
aws events put-rule --region "$REGION" --cli-input-json "$(aws_file_url "$HERE/rule-expiry-sweep.json")" \
  --query 'RuleArn' --output text
aws events put-rule --region "$REGION" --cli-input-json "$(aws_file_url "$HERE/rule-notification-drain.json")" \
  --query 'RuleArn' --output text

echo "[7/8] attach each destination to its rule"
# A freshly created role is not always visible to EventBridge's PassRole check yet; this short
# wait turns an intermittent ValidationException into a non-event.
sleep 10
for JOB in expiry-sweep notification-drain; do
  if [ "$JOB" = "expiry-sweep" ]; then DEST="$DEST_EXPIRY"; else DEST="$DEST_DRAIN"; fi
  export DEST SUBST_JSON
  SUBST_JSON="$(python -c 'import json,os;print(json.dumps({"__API_DESTINATION_ARN__": os.environ["DEST"]}))')"
  render "$HERE/targets-$JOB.json" "$WORK/targets.json"
  FAILED="$(aws events put-targets --region "$REGION" --cli-input-json "$(aws_file_url "$WORK/targets.json")" \
              --query 'FailedEntryCount' --output text)"
  echo "  $JOB put-targets FailedEntryCount=$FAILED"
  if [ "$FAILED" != "0" ]; then
    aws events put-targets --region "$REGION" --cli-input-json "$(aws_file_url "$WORK/targets.json")" \
      --query 'FailedEntries' --output json >&2
    echo "put-targets reported failures for $JOB -- the rule will not fire." >&2
    exit 1
  fi
done

echo "[8/8] read it all back -- never trust an unexamined exit code (AGENTS.md)"
for RULE in setuhaul-expiry-sweep-every-minute setuhaul-notification-drain-every-minute; do
  aws events describe-rule --region "$REGION" --name "$RULE" \
    --query '{Name:Name,Schedule:ScheduleExpression,State:State}' --output json
  aws events list-targets-by-rule --region "$REGION" --rule "$RULE" \
    --query 'Targets[].{Id:Id,Arn:Arn,Role:RoleArn}' --output json
done

cat <<MSG

SCHEDULER APPLIED. Both jobs now fire once a minute.

Confirm delivery in ~3 minutes (read-only):
  aws cloudwatch get-metric-statistics --region $REGION --namespace AWS/Events \\
    --metric-name InvocationsSentToApiDestination --period 60 --statistics Sum \\
    --start-time \$(date -u -d '-10 minutes' +%Y-%m-%dT%H:%M:%SZ) \\
    --end-time \$(date -u +%Y-%m-%dT%H:%M:%SZ)
  aws logs tail /aws/ecs/default/setuhaul-api-ap-south-1 --since 5m --region $REGION | grep internal/jobs

If invocations are attempted but failing, look at AWS/Events FailedInvocations and remember an
API destination request times out after 5 seconds (the sweeper is batch-bounded for exactly
this reason -- see the module docstring in backend/app/api/v1/routers/internal.py).

To pause without deleting anything:
  aws events disable-rule --region $REGION --name setuhaul-expiry-sweep-every-minute
  aws events disable-rule --region $REGION --name setuhaul-notification-drain-every-minute
MSG
