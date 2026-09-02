# Issue #111 / the #20 EventBridge leg -- PowerShell variant of apply_eventbridge_jobs.sh.
# See that file's header for the full why and the AWS doc citations. Short version, verified
# against current docs on 2026-09-02: EventBridge *Scheduler* has no HTTPS/API-destination
# target, so the documented shape for "call an HTTPS endpoint every minute with a custom auth
# header" is connection (API_KEY) -> API destination -> scheduled rule on the default bus.
#
# Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File deploy\eventbridge-scheduler\apply_eventbridge_jobs.ps1
#   ... -SkipLiveCheck   apply even if the endpoint is still answering 503 (not recommended)
param(
  [switch]$SkipLiveCheck
)
$ErrorActionPreference = "Stop"

$Region         = if ($env:AWS_REGION) { $env:AWS_REGION } else { "ap-south-1" }
$Here           = Split-Path -Parent $MyInvocation.MyCommand.Path
$Origin         = if ($env:SETUHAUL_PUBLIC_ORIGIN) { $env:SETUHAUL_PUBLIC_ORIGIN } else { "https://d382h70qmz3ife.cloudfront.net" }
$RoleName       = "setuhaul-eventbridge-jobs-role"
$PolicyName     = "SetuHaulInvokeInternalJobApiDestinations"
$ConnectionName = "setuhaul-internal-jobs"

$Work = Join-Path ([System.IO.Path]::GetTempPath()) ("setuhaul-eb-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $Work | Out-Null

function Render([string]$src, [string]$dst, [hashtable]$map) {
  $text = Get-Content -Raw $src
  foreach ($k in $map.Keys) { $text = $text.Replace($k, $map[$k]) }
  Set-Content -Path $dst -Value $text -Encoding utf8
}

try {
  Write-Host "[1/8] refuse to schedule against a route that is still refusing"
  # 1440 invocations a day into a 503 is not a schedule, it is a metrics generator. The
  # task-definition half of #111 (deploy\apply_ecs_task_definition.ps1) must land first.
  $code = 0
  try {
    $code = [int](Invoke-WebRequest -Uri "$Origin/internal/jobs/expiry-sweep" -Method POST -UseBasicParsing).StatusCode
  } catch {
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    else { throw "could not reach $Origin -- $($_.Exception.Message)" }
  }
  Write-Host "  unauthenticated POST $Origin/internal/jobs/expiry-sweep -> $code"
  if ($code -eq 503 -and -not $SkipLiveCheck) {
    throw "503 JOB_AUTH_UNCONFIGURED: JOB_AUTH_TOKEN is not on the running task yet. Run deploy\apply_ecs_task_definition.ps1 first (-SkipLiveCheck to override)."
  }

  Write-Host "[2/8] read the job token from SSM (single source of truth; never printed)"
  $token = aws ssm get-parameter --region $Region --name /setuhaul/job-auth-token --with-decryption --query 'Parameter.Value' --output text
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token) -or $token -eq "None") {
    throw "/setuhaul/job-auth-token is missing in $Region -- see deploy/README.md #111 runbook."
  }
  Write-Host "  got $($token.Length) characters from /setuhaul/job-auth-token"

  Write-Host "[3/8] the invoke role EventBridge assumes to call the API destinations"
  aws iam get-role --role-name $RoleName 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  role exists -- refreshing its trust policy from the artifact"
    aws iam update-assume-role-policy --role-name $RoleName --policy-document "file://$Here/invoke-role-trust.json"
    if ($LASTEXITCODE -ne 0) { throw "update-assume-role-policy FAILED" }
  } else {
    aws iam create-role --role-name $RoleName --description "Issue #111: lets EventBridge scheduled rules invoke the SetuHaul internal-job API destinations." --assume-role-policy-document "file://$Here/invoke-role-trust.json" --query 'Role.Arn' --output text
    if ($LASTEXITCODE -ne 0) { throw "create-role FAILED" }
  }
  aws iam put-role-policy --role-name $RoleName --policy-name $PolicyName --policy-document "file://$Here/invoke-role-policy.json"
  if ($LASTEXITCODE -ne 0) { throw "put-role-policy FAILED -- the rules would be unable to invoke anything" }

  Write-Host "[4/8] the connection (API_KEY -> X-SetuHaul-Job-Token header)"
  # EventBridge stores ApiKeyValue in Secrets Manager on its own side, through its
  # service-linked role. The token is never written into this repo, the rule, or the destination.
  $connFile = Join-Path $Work "connection.json"
  Render "$Here/connection.json" $connFile @{ "__JOB_AUTH_TOKEN__" = $token }
  aws events describe-connection --region $Region --name $ConnectionName 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "  connection exists -- updating its API key to the current SSM value"
    aws events update-connection --region $Region --cli-input-json "file://$connFile" --query 'ConnectionArn' --output text
  } else {
    aws events create-connection --region $Region --cli-input-json "file://$connFile" --query 'ConnectionArn' --output text
  }
  if ($LASTEXITCODE -ne 0) { throw "connection create/update FAILED" }
  Remove-Item $connFile -Force

  Write-Host "  waiting for the connection to reach AUTHORIZED"
  for ($i = 0; $i -lt 30; $i++) {
    $state = aws events describe-connection --region $Region --name $ConnectionName --query 'ConnectionState' --output text
    Write-Host "    state=$state"
    if ($state -eq "AUTHORIZED") { break }
    Start-Sleep -Seconds 2
  }
  $connArn = aws events describe-connection --region $Region --name $ConnectionName --query 'ConnectionArn' --output text
  if ($LASTEXITCODE -ne 0) { throw "cannot read the connection ARN" }

  Write-Host "[5/8] the two API destinations"
  $destArns = @{}
  foreach ($job in @("expiry-sweep", "notification-drain")) {
    $destFile = Join-Path $Here "api-destination-$job.json"
    $destName = (Get-Content -Raw $destFile | ConvertFrom-Json).Name
    $staged = Join-Path $Work "dest.json"
    Render $destFile $staged @{ "__CONNECTION_ARN__" = $connArn }
    aws events describe-api-destination --region $Region --name $destName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      aws events update-api-destination --region $Region --cli-input-json "file://$staged" | Out-Null
    } else {
      aws events create-api-destination --region $Region --cli-input-json "file://$staged" | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw "api destination create/update FAILED for $destName" }
    $arn = aws events describe-api-destination --region $Region --name $destName --query 'ApiDestinationArn' --output text
    if ($LASTEXITCODE -ne 0) { throw "cannot read the ARN of $destName" }
    Write-Host "  $destName -> $arn"
    $destArns[$job] = $arn
  }

  Write-Host "[6/8] the two scheduled rules (rate(1 minute), default bus)"
  aws events put-rule --region $Region --cli-input-json "file://$Here/rule-expiry-sweep.json" --query 'RuleArn' --output text
  if ($LASTEXITCODE -ne 0) { throw "put-rule FAILED for the expiry sweep" }
  aws events put-rule --region $Region --cli-input-json "file://$Here/rule-notification-drain.json" --query 'RuleArn' --output text
  if ($LASTEXITCODE -ne 0) { throw "put-rule FAILED for the notification drain" }

  Write-Host "[7/8] attach each destination to its rule"
  # A freshly created role is not always visible to EventBridge's PassRole check yet; this
  # short wait turns an intermittent ValidationException into a non-event.
  Start-Sleep -Seconds 10
  foreach ($job in @("expiry-sweep", "notification-drain")) {
    $staged = Join-Path $Work "targets.json"
    Render (Join-Path $Here "targets-$job.json") $staged @{ "__API_DESTINATION_ARN__" = $destArns[$job] }
    $failed = aws events put-targets --region $Region --cli-input-json "file://$staged" --query 'FailedEntryCount' --output text
    if ($LASTEXITCODE -ne 0) { throw "put-targets FAILED for $job" }
    Write-Host "  $job put-targets FailedEntryCount=$failed"
    if ($failed -ne "0") {
      aws events put-targets --region $Region --cli-input-json "file://$staged" --query 'FailedEntries' --output json
      throw "put-targets reported failures for $job -- the rule will not fire"
    }
  }

  Write-Host "[8/8] read it all back -- never trust an unexamined exit code (AGENTS.md)"
  foreach ($rule in @("setuhaul-expiry-sweep-every-minute", "setuhaul-notification-drain-every-minute")) {
    aws events describe-rule --region $Region --name $rule --query '{Name:Name,Schedule:ScheduleExpression,State:State}' --output json
    if ($LASTEXITCODE -ne 0) { throw "describe-rule FAILED for $rule" }
    aws events list-targets-by-rule --region $Region --rule $rule --query 'Targets[].{Id:Id,Arn:Arn,Role:RoleArn}' --output json
    if ($LASTEXITCODE -ne 0) { throw "list-targets-by-rule FAILED for $rule" }
  }

  Write-Host ""
  Write-Host "SCHEDULER APPLIED. Both jobs now fire once a minute."
  Write-Host "Confirm delivery in ~3 minutes with the AWS/Events InvocationsSentToApiDestination"
  Write-Host "metric, or by tailing /aws/ecs/default/setuhaul-api-ap-south-1 for internal/jobs."
  Write-Host "Pause without deleting:  aws events disable-rule --region $Region --name <rule>"
}
finally {
  if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
}
