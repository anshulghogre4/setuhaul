# Issue #111 -- PowerShell variant of deploy/apply_ecs_task_definition.sh. See that file's
# header for the full why: the live task definition carried no JOB_AUTH_TOKEN, so both
# internal job routes answered 503 JOB_AUTH_UNCONFIGURED on production (verified live
# 2026-09-02). This registers deploy/ecs-task-definition.json as a new revision (adding
# JOB_AUTH_TOKEN and SENTRY_DSN as SSM SecureString secrets) and rolls the service onto it.
#
# Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File deploy\apply_ecs_task_definition.ps1
#   ... -SkipSentry   register without SENTRY_DSN (while /setuhaul/sentry-dsn is absent)
#   ... -NoRoll       register the revision but leave the service alone
param(
  [switch]$SkipSentry,
  [switch]$NoRoll
)
$ErrorActionPreference = "Stop"

$Region      = if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }
$Cluster     = if ($env:ECS_CLUSTER) { $env:ECS_CLUSTER } else { "default" }
$Service     = if ($env:ECS_SERVICE) { $env:ECS_SERVICE } else { "setuhaul-api" }
$TaskDefFile = if ($env:TASKDEF_FILE) { $env:TASKDEF_FILE } else { "deploy/ecs-task-definition.json" }
$CfOrigin    = if ($env:SETUHAUL_PUBLIC_ORIGIN) { $env:SETUHAUL_PUBLIC_ORIGIN } else { "https://d382h70qmz3ife.cloudfront.net" }

if (-not (Test-Path $TaskDefFile)) {
  throw "Task definition not found at $TaskDefFile -- run this from the repo root."
}

$Staged = Join-Path ([System.IO.Path]::GetTempPath()) ("setuhaul-taskdef-" + [guid]::NewGuid().ToString() + ".json")

try {
  if ($SkipSentry) {
    Write-Host "[0/6] -SkipSentry: stripping the SENTRY_DSN secret from the staged payload"
    $doc = Get-Content -Raw $TaskDefFile | ConvertFrom-Json
    foreach ($c in $doc.containerDefinitions) {
      $c.secrets = @($c.secrets | Where-Object { $_.name -ne "SENTRY_DSN" })
    }
    # -Depth 20: the default of 2 silently truncates nested arrays into type names, which
    # would register a task definition with garbage in it and no error at all.
    $doc | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 $Staged
  } else {
    Copy-Item $TaskDefFile $Staged
  }

  Write-Host "[1/6] preflight: every SSM parameter the payload references must already exist"
  # ECS resolves `secrets` when a task STARTS. A missing parameter is a
  # ResourceInitializationError on every replacement task, so the rollout never stabilises
  # and step 4 just blocks. One cheap existence check per secret avoids that entirely.
  # --with-decryption is deliberately not passed: existence is all we need, and the
  # plaintext would end up in this terminal's scrollback.
  $payload = Get-Content -Raw $Staged | ConvertFrom-Json
  $missing = @()
  foreach ($c in $payload.containerDefinitions) {
    foreach ($s in $c.secrets) {
      $param = $s.valueFrom
      if ($param -match ':parameter/') { $param = '/' + ($param -split ':parameter/', 2)[1] }
      $type = aws ssm get-parameter --region $Region --name $param --query 'Parameter.Type' --output text 2>$null
      if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($type) -or $type -eq "None") {
        Write-Host "  MISSING  $($s.name)  <- $param (region $Region)"
        $missing += $s.name
      } else {
        Write-Host "  ok       $($s.name)  <- $param ($type)"
      }
    }
  }

  if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "Refusing to register: these SSM parameters do not exist in $Region -- $($missing -join ', ')"
    Write-Host "Create them first (see the '#111 runbook' section of deploy/README.md), e.g.:"
    Write-Host '  python -c "import secrets;print(secrets.token_urlsafe(32))"'
    Write-Host "  aws ssm put-parameter --region ap-south-1 --name /setuhaul/job-auth-token ``"
    Write-Host "      --type SecureString --value '<the token>' --overwrite"
    Write-Host ""
    Write-Host "Put the SAME value in .env.local's JOB_AUTH_TOKEN so the local runner and the"
    Write-Host "EventBridge connection agree. If only /setuhaul/sentry-dsn is missing, re-run"
    Write-Host "this script with -SkipSentry."
    throw "SSM preflight failed -- nothing was registered."
  }

  Write-Host "[2/6] register the new revision (first write this script performs)"
  $newArn = aws ecs register-task-definition --region $Region --cli-input-json "file://$Staged" --query 'taskDefinition.taskDefinitionArn' --output text
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($newArn)) {
    throw "register-task-definition FAILED -- the service was NOT touched"
  }
  Write-Host "  registered: $newArn"

  if ($NoRoll) {
    Write-Host "[3/6] -NoRoll: stopping here. Point the service at $newArn when ready."
    return
  }

  Write-Host "[3/6] point the service at the new revision"
  aws ecs update-service --region $Region --cluster $Cluster --service $Service --task-definition $newArn --query 'service.deployments[0].status' --output text
  if ($LASTEXITCODE -ne 0) { throw "update-service FAILED -- the service was NOT rolled" }

  Write-Host "[4/6] wait for stability (this is the step that catches a bad secret reference)"
  aws ecs wait services-stable --region $Region --cluster $Cluster --services $Service
  if ($LASTEXITCODE -ne 0) { throw "stability wait FAILED -- check `aws ecs describe-services` for ResourceInitializationError" }

  Write-Host "[5/6] read back what the service is actually running -- never trust an exit code"
  $live = aws ecs describe-services --region $Region --cluster $Cluster --services $Service --query 'services[0].taskDefinition' --output text
  if ($LASTEXITCODE -ne 0) { throw "describe-services FAILED -- cannot confirm the rollout" }
  Write-Host "  service task definition: $live"
  aws ecs describe-task-definition --region $Region --task-definition $live --query 'taskDefinition.containerDefinitions[0].secrets[].name' --output json
  if ($LASTEXITCODE -ne 0) { throw "describe-task-definition FAILED -- cannot confirm the secrets landed" }

  Write-Host "[6/6] prove the regression this issue exists for is closed"
  # 503 here means the token never reached the container. Anything else (401 unauthenticated,
  # 200 authenticated) means the guard is configured -- that is the exact regression class.
  # try/catch rather than -SkipHttpErrorCheck: that switch is PowerShell 7+ only, and this
  # repo's scripts are invoked with `powershell` (Windows PowerShell 5.1) throughout.
  $code = 0
  try {
    $code = [int](Invoke-WebRequest -Uri "$CfOrigin/internal/jobs/expiry-sweep" -Method POST -UseBasicParsing).StatusCode
  } catch {
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    else { throw "could not reach $CfOrigin -- $($_.Exception.Message)" }
  }
  if ($code -eq 503) {
    throw "STILL 503 from $CfOrigin/internal/jobs/expiry-sweep -- JOB_AUTH_TOKEN did not land. Secrets resolve at task start; confirm the tasks were actually replaced."
  }
  Write-Host "  unauthenticated POST now answers $code (401 expected) -- the token is configured."
  Write-Host ""
  Write-Host "TASK DEFINITION APPLIED -- $newArn is live."
  Write-Host "Next: python docs/scripts/run_internal_job.py expiry-sweep --base $CfOrigin"
}
finally {
  if (Test-Path $Staged) { Remove-Item $Staged -Force }
}
