#!/usr/bin/env bash
# Issue #92 — restore the ECS BFF task role's AgentCore invoke grant from the checked-in artifact.
#
# WHY THIS FILE EXISTS
# The ECS side of SetuHaul is AWS ECS Express Mode, created through raw AWS APIs and the
# `deploy/*.json` payloads — there is no Terraform/CDK/CloudFormation stack that owns
# `setuhaul-bff-task-role`. So the invoke grant cannot live in IaC the way the AgentCore runtime's
# SSM grant now does (`agentcore/cdk/lib/cdk-stack.ts`). This script plus
# `deploy/bff-task-role-invoke-policy.json` is the next best thing: a one-command, reviewable,
# version-controlled restore, so a recreated role is a 10-second fix instead of a 40-minute
# outage diagnosis.
#
# The 2026-09-01 incident this prevents: the inline policy allowed InvokeAgentRuntime on the
# RETIRED us-east-1 runtime only. E7.1 moved the runtime to ap-south-1 and nobody re-pointed the
# grant, so every BFF invoke returned AccessDeniedException and chat 503'd.
#
# Run from the repo root:  bash deploy/apply_bff_invoke_policy.sh
# Git Bash note (recorded on #92): MSYS mangles leading-slash AWS arguments. Nothing here has one,
# but if you hand-edit this to pass an ARN-ish or path-ish literal, prefix with MSYS_NO_PATHCONV=1.
set -euo pipefail

ROLE_NAME="${ROLE_NAME:-setuhaul-bff-task-role}"
POLICY_NAME="${POLICY_NAME:-SetuHaulInvokeAgentCore}"
POLICY_FILE="${POLICY_FILE:-deploy/bff-task-role-invoke-policy.json}"

if [ ! -f "$POLICY_FILE" ]; then
  echo "Policy document not found at $POLICY_FILE -- run this from the repo root." >&2
  exit 1
fi

echo "[1/3] show what is on the role RIGHT NOW (read-only; may legitimately not exist yet)"
# Deliberately non-fatal: NoSuchEntity is the expected answer after a role recreation, which is
# the exact case this script is for.
aws iam get-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --query 'PolicyDocument' \
  --output json || echo "(no existing $POLICY_NAME on $ROLE_NAME -- that is what we are fixing)"

echo "[2/3] put the checked-in policy (this is the only write this script performs)"
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://$POLICY_FILE"

echo "[3/3] read it back and prove it took -- never trust an unexamined exit code (AGENTS.md)"
aws iam get-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --query 'PolicyDocument' \
  --output json

echo
echo "Applied. The grant is now live for NEW ECS tasks and for existing ones (role policies are"
echo "evaluated per request, not baked into the task), but a warm AgentCore container keeps its"
echo "half-hydrated environment -- see deploy/README.md for the warm-container caveat."
