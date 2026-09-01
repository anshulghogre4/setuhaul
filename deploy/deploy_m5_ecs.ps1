# M5 backend deploy -- ECS half (ap-south-1). PowerShell variant of deploy_m5_ecs.sh.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File deploy\deploy_m5_ecs.ps1
$ErrorActionPreference = "Stop"
$env:AWS_DEFAULT_REGION = "ap-south-1"
$ECR = "118490268011.dkr.ecr.ap-south-1.amazonaws.com"

Write-Host "[1/5] ECR login"
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR
if ($LASTEXITCODE -ne 0) { throw "ECR login failed" }

Write-Host "[2/5] tag + push (m5 and latest)"
docker tag setuhaul-api:m5 "$ECR/setuhaul-api:m5"
docker tag setuhaul-api:m5 "$ECR/setuhaul-api:latest"
docker push "$ECR/setuhaul-api:m5"
if ($LASTEXITCODE -ne 0) { throw "push m5 failed" }
docker push "$ECR/setuhaul-api:latest"
if ($LASTEXITCODE -ne 0) { throw "push latest failed" }

# BUG FIXED 2026-09-01: the first run of this script printed "COMPLETE" while steps 3-5 had
# all FAILED on an expired OAuth token -- $ErrorActionPreference = "Stop" does not stop on
# native-command failures, and only the docker steps had $LASTEXITCODE guards. Every aws step
# below now checks $LASTEXITCODE, so this script can no longer report success it did not earn.
Write-Host "[3/5] verify the pushed manifest exists (the deleted-ECR incident's lesson)"
aws ecr describe-images --repository-name setuhaul-api --image-ids imageTag=latest --query 'imageDetails[0].imagePushedAt' --output text
if ($LASTEXITCODE -ne 0) { throw "manifest check failed -- image may not be in ECR; do NOT roll the service" }

Write-Host "[4/5] roll the service"
aws ecs update-service --cluster default --service setuhaul-api --force-new-deployment --query 'service.deployments[0].status' --output text
if ($LASTEXITCODE -ne 0) { throw "update-service failed -- service was NOT rolled" }

Write-Host "[5/5] wait for stability (catches CannotPullContainerError instead of trusting the rollout)"
aws ecs wait services-stable --cluster default --services setuhaul-api
if ($LASTEXITCODE -ne 0) { throw "stability wait FAILED -- the rollout is not confirmed; check ecs describe-services" }
Write-Host "ECS DEPLOY COMPLETE -- service stable on the new image."
