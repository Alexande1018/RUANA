param(
    [string]$EnvFile = ".env.local"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\ruana_env.ps1"

Import-RuanaEnv -Path $EnvFile
Require-RuanaEnv -Names @(
    "FIREBASE_PROJECT_ID",
    "GOOGLE_CLOUD_REGION",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY"
)

$projectId = $env:FIREBASE_PROJECT_ID
$region = $env:GOOGLE_CLOUD_REGION
$service = "ruana"
$repository = if ($env:ARTIFACT_REGISTRY_REPOSITORY) { $env:ARTIFACT_REGISTRY_REPOSITORY } else { "ruana" }
$image = "$region-docker.pkg.dev/$projectId/$repository/$service"
$gcloud = Resolve-RuanaCommand -Name "gcloud" -CandidatePaths @(
    "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    "$env:USERPROFILE\scoop\apps\gcloud\current\bin\gcloud.cmd"
)

Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("config", "set", "project", $projectId)
Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @(
    "services", "enable",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "--project", $projectId
)

$repositoryNames = @(Invoke-RuanaNativeCommandOutput -FilePath $gcloud -Arguments @("artifacts", "repositories", "list", "--location", $region, "--project", $projectId, "--format", "value(name)"))
$escapedRepository = [regex]::Escape($repository)
$repositoryExists = @($repositoryNames | Where-Object { $_ -eq $repository -or $_ -match "/repositories/$escapedRepository$" }).Count -gt 0
if (-not $repositoryExists) {
    Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @(
        "artifacts", "repositories", "create", $repository,
        "--repository-format", "docker",
        "--location", $region,
        "--description", "RUANA container images",
        "--project", $projectId
    )
}

$runtimeServiceAccountName = "ruana-runner"
$runtimeServiceAccount = "$runtimeServiceAccountName@$projectId.iam.gserviceaccount.com"
$serviceAccounts = @(Invoke-RuanaNativeCommandOutput -FilePath $gcloud -Arguments @("iam", "service-accounts", "list", "--project", $projectId, "--format", "value(email)"))
if ($serviceAccounts -notcontains $runtimeServiceAccount) {
    Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("iam", "service-accounts", "create", $runtimeServiceAccountName, "--display-name", "RUANA Cloud Run runtime", "--project", $projectId)
    Start-Sleep -Seconds 5
}

Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @("builds", "submit", "--tag", $image, "--project", $projectId)

Invoke-RuanaNativeCommand -FilePath $gcloud -Arguments @(
    "run", "deploy", $service,
    "--image", $image,
    "--region", $region,
    "--project", $projectId,
    "--allow-unauthenticated",
    "--max-instances", "3",
    "--service-account", $runtimeServiceAccount,
    "--set-env-vars", "FIREBASE_PROJECT_ID=$projectId,GOOGLE_CLOUD_REGION=$region,SUPABASE_URL=$($env:SUPABASE_URL)",
    "--set-secrets", "DATABASE_URL=ruana-database-url:latest,SUPABASE_SERVICE_ROLE_KEY=ruana-supabase-service-role-key:latest,SUPABASE_ANON_KEY=ruana-supabase-anon-key:latest,FLASK_SECRET_KEY=ruana-flask-secret-key:latest,RUANA_ADMIN_CREDENTIALS_JSON=ruana-admin-credentials:latest"
)

Write-Host "Cloud Run deploy finished for service $service in $region."
