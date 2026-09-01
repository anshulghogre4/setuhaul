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
