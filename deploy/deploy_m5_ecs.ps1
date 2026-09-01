# M5 backend deploy -- ECS half (ap-south-1). PowerShell variant of deploy_m5_ecs.sh.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File deploy\deploy_m5_ecs.ps1
$ErrorActionPreference = "Stop"
$env:AWS_DEFAULT_REGION = "ap-south-1"
$ECR = "118490268011.dkr.ecr.ap-south-1.amazonaws.com"

# BUILD STEP ADDED 2026-09-01: this script originally only tagged and pushed whatever
# setuhaul-api:m5 image already existed locally -- the Docker variant of the codezip trap
# (AGENTS.md's deploy lesson): editing backend/** does nothing for ECS until the image is
# rebuilt, and the push "succeeds" either way. Nearly shipped a stale image (built 09:54)
# over the #93/#96/#97 batch (landed 12:00+). The build is now part of the deploy.
Write-Host "[0/5] build image from the current tree"
# --platform pinned: the live task definition is runtimePlatform ARM64 (verified via
# describe-task-definition 2026-09-01); an unpinned build on this amd64 host would push
# an image the service cannot run, caught only at the [5/5] stability wait.
docker build --platform linux/arm64 -t setuhaul-api:m5 backend
if ($LASTEXITCODE -ne 0) { throw "docker build failed -- nothing was pushed or rolled" }

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
