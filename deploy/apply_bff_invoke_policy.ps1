# Issue #92 -- restore the ECS BFF task role's AgentCore invoke grant from the checked-in artifact.
# PowerShell variant of deploy/apply_bff_invoke_policy.sh; see that file's header for the full why.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File deploy\apply_bff_invoke_policy.ps1
$ErrorActionPreference = "Stop"

$RoleName   = if ($env:ROLE_NAME)   { $env:ROLE_NAME }   else { "setuhaul-bff-task-role" }
$PolicyName = if ($env:POLICY_NAME) { $env:POLICY_NAME } else { "SetuHaulInvokeAgentCore" }
$PolicyFile = if ($env:POLICY_FILE) { $env:POLICY_FILE } else { "deploy/bff-task-role-invoke-policy.json" }

if (-not (Test-Path $PolicyFile)) {
  throw "Policy document not found at $PolicyFile -- run this from the repo root."
}

# $LASTEXITCODE guards on every aws call: $ErrorActionPreference = "Stop" does NOT stop on native
# command failure. deploy_m5_ecs.ps1 printed "COMPLETE" over three failed steps for exactly this
# reason on 2026-09-01; the same mistake is not repeated here.
Write-Host "[1/3] show what is on the role RIGHT NOW (read-only; absence is the expected post-recreation state)"
aws iam get-role-policy --role-name $RoleName --policy-name $PolicyName --query 'PolicyDocument' --output json
if ($LASTEXITCODE -ne 0) { Write-Host "(no existing $PolicyName on $RoleName -- that is what we are fixing)" }

Write-Host "[2/3] put the checked-in policy (the only write this script performs)"
aws iam put-role-policy --role-name $RoleName --policy-name $PolicyName --policy-document "file://$PolicyFile"
if ($LASTEXITCODE -ne 0) { throw "put-role-policy FAILED -- the grant was NOT applied" }

Write-Host "[3/3] read it back and prove it took -- never trust an unexamined exit code (AGENTS.md)"
aws iam get-role-policy --role-name $RoleName --policy-name $PolicyName --query 'PolicyDocument' --output json
if ($LASTEXITCODE -ne 0) { throw "read-back FAILED -- cannot confirm the grant landed" }

Write-Host ""
Write-Host "Applied. Live immediately for new requests, but a warm AgentCore container keeps its"
Write-Host "half-hydrated environment -- see deploy/README.md for the warm-container caveat."
