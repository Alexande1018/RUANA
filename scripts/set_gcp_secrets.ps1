param(
    [string]$EnvFile = ".env.local"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\ruana_env.ps1"

Import-RuanaEnv -Path $EnvFile
Require-RuanaEnv -Names @(
    "FIREBASE_PROJECT_ID",
    "DATABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "FLASK_SECRET_KEY"
)

$projectId = $env:FIREBASE_PROJECT_ID
$gcloud = Resolve-RuanaCommand -Name "gcloud" -CandidatePaths @(
    "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:USERPROFILE\scoop\apps\gcloud\current\bin\gcloud.cmd"
)

Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("config", "set", "project", $projectId)
Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("services", "enable", "secretmanager.googleapis.com", "iam.googleapis.com", "--project", $projectId)

function Set-SecretValue {
    param(
        [string]$Name,
        [string]$Value
    )

    $secretNames = @(Invoke-RuanaNativeCommandOutput -FilePath $gcloud -Arguments @("secrets", "list", "--project", $projectId, "--format", "value(name)"))
    $escapedName = [regex]::Escape($Name)
    $exists = @($secretNames | Where-Object { $_ -eq $Name -or $_ -match "/$escapedName$" }).Count -gt 0

    if (-not $exists) {
        Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("secrets", "create", $Name, "--replication-policy", "automatic", "--project", $projectId)
    }

    $tmp = New-TemporaryFile
    try {
        [System.IO.File]::WriteAllText($tmp.FullName, $Value, [System.Text.UTF8Encoding]::new($false))
        Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("secrets", "versions", "add", $Name, "--data-file", $tmp.FullName, "--project", $projectId)
    }
    finally {
        Remove-Item -LiteralPath $tmp.FullName -Force -ErrorAction SilentlyContinue
    }
}

Set-SecretValue -Name "ruana-database-url" -Value $env:DATABASE_URL
Set-SecretValue -Name "ruana-supabase-service-role-key" -Value $env:SUPABASE_SERVICE_ROLE_KEY
Set-SecretValue -Name "ruana-supabase-anon-key" -Value $env:SUPABASE_ANON_KEY
Set-SecretValue -Name "ruana-flask-secret-key" -Value $env:FLASK_SECRET_KEY

$adminCredentialsPath = if ($env:RUANA_ADMIN_CREDENTIALS_PATH) { $env:RUANA_ADMIN_CREDENTIALS_PATH } else { ".local-secrets/admin_credentials.json" }
if (Test-Path -LiteralPath $adminCredentialsPath) {
    $adminCredentialsJson = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $adminCredentialsPath))
    Set-SecretValue -Name "ruana-admin-credentials" -Value $adminCredentialsJson
    Write-Host "Secret ruana-admin-credentials updated from $adminCredentialsPath"
}
else {
    Write-Warning "Admin credentials file not found at $adminCredentialsPath. Run bootstrap_admin_credentials.py first."
}

$runtimeServiceAccountName = "ruana-runner"
$runtimeServiceAccount = "$runtimeServiceAccountName@$projectId.iam.gserviceaccount.com"
$serviceAccounts = @(Invoke-RuanaNativeCommandOutput -FilePath $gcloud -Arguments @("iam", "service-accounts", "list", "--project", $projectId, "--format", "value(email)"))
if ($serviceAccounts -notcontains $runtimeServiceAccount) {
    Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("iam", "service-accounts", "create", $runtimeServiceAccountName, "--display-name", "RUANA Cloud Run runtime", "--project", $projectId)
    Start-Sleep -Seconds 5
}

foreach ($secretName in @("ruana-database-url", "ruana-supabase-service-role-key", "ruana-supabase-anon-key", "ruana-flask-secret-key", "ruana-admin-credentials")) {
    Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @(
        "secrets", "add-iam-policy-binding", $secretName,
        "--member", "serviceAccount:$runtimeServiceAccount",
        "--role", "roles/secretmanager.secretAccessor",
        "--project", $projectId,
        "--quiet"
    )
}

Write-Host "GCP secrets updated for project $projectId."
