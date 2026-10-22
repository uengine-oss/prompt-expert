# Builds dist\prompt-expert-Setup-<version>.exe with Inno Setup 6 (installs it per-user if missing).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $ProgressPreference = "SilentlyContinue"
    $setup = "$env:TEMP\innosetup.exe"
    Invoke-WebRequest "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe" -OutFile $setup -UseBasicParsing
    Start-Process $setup -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER" -Wait
    $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
}

if (-not (Test-Path "dist\prompt-expert\prompt-expert.exe")) { & .\build.ps1 }
$version = (Select-String -Path winwhisper\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
& $iscc /Q "/DAppVersion=$version" installer\prompt-expert.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
Write-Output "built: $root\dist\prompt-expert-Setup-$version.exe"
