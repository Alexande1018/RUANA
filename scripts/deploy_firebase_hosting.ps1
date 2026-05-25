param(
    [string]$EnvFile = ".env.local"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\ruana_env.ps1"

Import-RuanaEnv -Path $EnvFile
Require-RuanaEnv -Names @("FIREBASE_PROJECT_ID")

$projectId = $env:FIREBASE_PROJECT_ID
$localCredentials = Join-Path (Resolve-Path ".") ".local-secrets\firebase-deployer.json"
if (-not $env:GOOGLE_APPLICATION_CREDENTIALS -and (Test-Path -LiteralPath $localCredentials)) {
    [Environment]::SetEnvironmentVariable("GOOGLE_APPLICATION_CREDENTIALS", $localCredentials, "Process")
    [Environment]::SetEnvironmentVariable("FIREBASE_TOKEN", $null, "Process")
}

$localFirebase = Join-Path (Resolve-Path ".") "node_modules\.bin\firebase.cmd"
$firebase = if (Test-Path -LiteralPath $localFirebase) {
    $localFirebase
}
else {
    $command = Get-Command firebase -ErrorAction SilentlyContinue
    if ($command) { $command.Source } else { $null }
}

if ($firebase) {
    Invoke-RuanaNativeCommand -FilePath $firebase -Arguments @("deploy", "--project", $projectId, "--only", "hosting")
}
else {
    $npx = Resolve-RuanaCommand -Name "npx.cmd" -CandidatePaths @("C:\Program Files\nodejs\npx.cmd")
    Invoke-RuanaNativeCommand -FilePath $npx -Arguments @("--yes", "firebase-tools@15.18.0", "deploy", "--project", $projectId, "--only", "hosting")
}

Write-Host "Firebase Hosting deploy finished for project $projectId."
