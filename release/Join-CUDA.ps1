param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$partial = $null
try {
    $manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'cuda-parts.json') -Raw | ConvertFrom-Json
    $names = @($manifest.output) + @($manifest.parts | ForEach-Object { $_.name })
    foreach ($name in $names) {
        if ([string]::IsNullOrWhiteSpace($name) -or [IO.Path]::GetFileName($name) -ne $name -or $name.Contains(':')) {
            throw 'Invalid filename in manifest.'
        }
    }
    $output = Join-Path $PSScriptRoot $manifest.output
    if (Test-Path -LiteralPath $output) {
        if ((Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash -ne $manifest.sha256) {
            throw 'An existing EXE has a different checksum. Move it elsewhere before joining.'
        }
        Write-Host "Already assembled and verified: $output"
    } else {
        foreach ($part in $manifest.parts) {
            $path = Join-Path $PSScriptRoot $part.name
            Write-Host "Checking $($part.name)..."
            if (!(Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -ne $part.size) {
                throw "Missing or incomplete download: $($part.name)"
            }
            if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $part.sha256) {
                throw "Checksum mismatch: $($part.name). Download this part again."
            }
        }
        $partial = Join-Path $PSScriptRoot ($manifest.output + '.' + [guid]::NewGuid().ToString('N') + '.partial')
        $target = [IO.File]::Open($partial, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
        try {
            foreach ($part in $manifest.parts) {
                Write-Host "Joining $($part.name)..."
                $source = [IO.File]::OpenRead((Join-Path $PSScriptRoot $part.name))
                try { $source.CopyTo($target, 4194304) } finally { $source.Dispose() }
            }
        } finally { $target.Dispose() }
        if ((Get-Item -LiteralPath $partial).Length -ne $manifest.size -or
            (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $manifest.sha256) {
            throw 'The assembled file did not pass verification.'
        }
        Move-Item -LiteralPath $partial -Destination $output
        $partial = $null
        Write-Host "Ready: $output"
        Write-Host 'You can now run the EXE. The download parts may be deleted afterward.'
    }
    if (!$NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($partial -and (Test-Path -LiteralPath $partial)) { Remove-Item -LiteralPath $partial }
    if (!$NoPause) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
