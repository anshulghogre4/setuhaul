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

# ---------------------------------------------------------------------------------------
# POST-DEPLOY SMOKE (issue #111, added 2026-09-02): the internal-jobs guard.
#
# On 2026-09-02 both internal job routes answered 503 JOB_AUTH_UNCONFIGURED on production for
# an unknown length of time, because the task definition simply had no JOB_AUTH_TOKEN. Nothing
# errored -- the service was healthy, /health/live returned 200, the deploy "succeeded". The
# only symptom was that the outbox never drained and no expiry escalations were produced.
# This step turns that silent class of defect into a failed deploy.
#
# Guarded, not mandatory: the token is deliberately not in the repo, so a machine without it
# locally cannot run the check. The skip is LOUD on purpose -- a quiet skip would recreate the
# same false confidence this step exists to remove.
$CfOrigin = if ($env:SETUHAUL_PUBLIC_ORIGIN) { $env:SETUHAUL_PUBLIC_ORIGIN } else { "https://d382h70qmz3ife.cloudfront.net" }
$SmokeToken = $env:JOB_AUTH_TOKEN
if ([string]::IsNullOrWhiteSpace($SmokeToken) -and (Test-Path ".env.local")) {
  $line = Select-String -Path ".env.local" -Pattern '^JOB_AUTH_TOKEN=' | Select-Object -First 1
  if ($line) { $SmokeToken = ($line.Line -replace '^JOB_AUTH_TOKEN=', '').Trim().Trim('"').Trim("'") }
}

if ([string]::IsNullOrWhiteSpace($SmokeToken)) {
  Write-Host ""
  Write-Host "########################################################################"
  Write-Host "# SMOKE SKIPPED: no JOB_AUTH_TOKEN in this environment or .env.local.  #"
  Write-Host "# The deploy is NOT verified against issue #111's regression -- the    #"
  Write-Host "# internal job routes could be answering 503 and you would not know.   #"
  Write-Host "# Verify by hand:                                                      #"
  Write-Host "#   python docs/scripts/run_internal_job.py expiry-sweep               #"
  Write-Host "########################################################################"
} else {
  Write-Host ""
  Write-Host "[smoke] POST $CfOrigin/internal/jobs/expiry-sweep (issue #111 regression guard)"
  # try/catch rather than -SkipHttpErrorCheck: that switch is PowerShell 7+ only and these
  # scripts are invoked with Windows PowerShell 5.1.
  $smokeCode = 0
  $smokeBody = ""
  try {
    $resp = Invoke-WebRequest -Uri "$CfOrigin/internal/jobs/expiry-sweep" -Method POST -UseBasicParsing -Headers @{ "X-SetuHaul-Job-Token" = $SmokeToken }
    $smokeCode = [int]$resp.StatusCode
    $smokeBody = $resp.Content
  } catch {
    if ($_.Exception.Response) {
      $smokeCode = [int]$_.Exception.Response.StatusCode
      # Windows PowerShell 5.1 has ALREADY drained the response stream by the time the
      # exception surfaces -- GetResponseStream() reads back empty and the body ends up in
      # $_.ErrorDetails.Message instead. Verified live 2026-09-02: reading only the stream
      # made this step report the generic "expected 200" instead of naming
      # JOB_AUTH_UNCONFIGURED, which is the entire diagnostic value of the check.
      # ErrorDetails first, stream as the fallback (PowerShell 7 behaves the other way).
      if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $smokeBody = $_.ErrorDetails.Message
      } else {
        $stream = $_.Exception.Response.GetResponseStream()
        if ($stream) { $smokeBody = (New-Object System.IO.StreamReader($stream)).ReadToEnd() }
      }
    } else {
      throw "SMOKE FAILED: could not reach $CfOrigin -- $($_.Exception.Message)"
    }
  }
  Write-Host "  status $smokeCode"
  if ($smokeBody -match "JOB_AUTH_UNCONFIGURED") {
    Write-Host $smokeBody
    throw "DEPLOY FAILED THE #111 SMOKE: the running task has no JOB_AUTH_TOKEN. Fix with deploy\apply_ecs_task_definition.ps1 -- the token is an SSM-sourced task-definition secret, and a new image alone will never add it."
  }
  if ($smokeCode -ne 200) {
    Write-Host $smokeBody
    throw "DEPLOY FAILED THE #111 SMOKE: expected 200, got $smokeCode."
  }
  Write-Host "  $smokeBody"
  Write-Host "  internal jobs are callable on production."
}
