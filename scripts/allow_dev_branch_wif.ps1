param(
    [string]$ProjectId = "ruana-4293f",
    [string]$Repository = "Alexande1018/RUANA"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\ruana_env.ps1"

$gcloud = Resolve-RuanaCommand -Name "gcloud" -CandidatePaths @(
    "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:USERPROFILE\scoop\apps\gcloud\current\bin\gcloud.cmd"
)

$attributeCondition = "assertion.repository=='$Repository' && (assertion.ref=='refs/heads/main' || assertion.ref=='refs/heads/dev')"

Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("config", "set", "project", $ProjectId)
Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @(
    "iam", "workload-identity-pools", "providers", "update-oidc", "github",
    "--location=global",
    "--workload-identity-pool=github-actions",
    "--project", $ProjectId,
    "--attribute-condition=$attributeCondition"
)

Write-Host "Workload Identity actualizado para main y dev en $Repository."
