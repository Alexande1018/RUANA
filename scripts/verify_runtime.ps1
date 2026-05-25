param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"

$health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get
if ($health.status -ne "healthy") {
    throw "Health check failed for $BaseUrl"
}

$contactMetrics = Invoke-RestMethod -Uri "$BaseUrl/api/contactos/metricas" -Method Get
if ($contactMetrics.status -ne "success") {
    throw "Contact metrics check failed for $BaseUrl"
}

Write-Host "Runtime checks passed for $BaseUrl."
