function Import-RuanaEnv {
    param(
        [string]$Path = ".env.local"
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Environment file not found: $Path"
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) {
            return
        }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Require-RuanaEnv {
    param(
        [string[]]$Names
    )

    $missing = @()
    foreach ($name in $Names) {
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            $missing += $name
        }
    }

    if ($missing.Count -gt 0) {
        throw "Missing required environment variables: $($missing -join ', ')"
    }
}

function Resolve-RuanaCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string[]]$CandidatePaths = @()
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($path in $CandidatePaths) {
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }

    throw "Command not found: $Name"
}

function Invoke-RuanaNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "External command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-RuanaNativeCommandOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    $output = & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "External command failed with exit code $LASTEXITCODE."
    }
    return $output
}
