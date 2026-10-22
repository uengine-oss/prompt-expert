# Builds dist\prompt-expert\prompt-expert.exe (a folder build; zip it to distribute).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller msvc-runtime
# ctranslate2.dll needs the x64 C++ runtime, which clean Windows installs lack;
# msvc-runtime drops the x64 DLLs into the venv root so we can ship them.
$runtime = "msvcp140.dll", "msvcp140_1.dll", "vcomp140.dll" |
    Where-Object { Test-Path ".venv\$_" } | ForEach-Object { "--add-binary", ".venv\$_;." }
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name prompt-expert `
    --icon installer\winwhisper.ico `
    --collect-data faster_whisper --collect-binaries ctranslate2 `
    --hidden-import pystray._win32 @runtime `
    run_winwhisper.py
Write-Output "built: $PSScriptRoot\dist\prompt-expert\prompt-expert.exe"
