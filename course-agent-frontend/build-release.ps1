$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)] [string] $Command,
        [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Find-ElectronZip {
    $version = (& node -p "require('electron/package.json').version").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        return $null
    }
    $cacheRoot = Join-Path $env:LOCALAPPDATA "electron\Cache"
    if (-not (Test-Path -LiteralPath $cacheRoot)) {
        return $null
    }
    return Get-ChildItem -LiteralPath $cacheRoot -Recurse -File `
        -Filter "electron-v$version-win32-x64.zip" -ErrorAction SilentlyContinue `
        | Select-Object -First 1
}

Push-Location $PSScriptRoot
try {
    Invoke-Step npm.cmd run backend:build
    Invoke-Step npm.cmd run build

    $electronZip = Find-ElectronZip
    if ($electronZip) {
        Invoke-Step npx.cmd electron-builder --win "--config.electronDist=$($electronZip.FullName)"
        exit 0
    }

    & npx.cmd electron-builder --win
    if ($LASTEXITCODE -eq 0) {
        exit 0
    }

    # GitHub 下载偶发超时时，下载器可能已经留下完整缓存；自动复用后重试一次。
    $electronZip = Find-ElectronZip
    if (-not $electronZip) {
        throw "Electron Builder failed and no reusable Electron cache was found"
    }
    Invoke-Step npx.cmd electron-builder --win "--config.electronDist=$($electronZip.FullName)"
}
finally {
    Pop-Location
}
