# Runs a tests\e2e_*.py script inside the logged-on user's desktop session.
# SSH sessions have no desktop, so keyboard hooks, SendInput and the user's
# clipboard would not reach any window; an interactive scheduled task does.
param(
    [string]$Case = "ko",
    [string]$Model = "small",
    [string]$Python = "",
    [string]$AppExe = "",
    [switch]$SkipNotepad,
    [ValidateSet("dictation", "copypath")][string]$Suite = "dictation"
)
$root = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $root ".venv\Scripts\python.exe" }
$output = Join-Path $root "e2e-output.txt"
$result = Join-Path $root "e2e-result.json"
Remove-Item $output, $result -ErrorAction SilentlyContinue

if ($Suite -eq "copypath") {
    $script = "tests\e2e_copypath.py"
    $extra = ""
} else {
    $script = "tests\e2e_windows.py"
    $extra = "--case $Case --model $Model"
    if ($SkipNotepad) { $extra += " --skip-notepad" }
}
if ($AppExe) { $extra += " --app-exe `"$AppExe`"" }

$taskName = "PromptExpertE2E"
$arguments = "/c chcp 65001 >nul & cd /d `"$root`" & `"$Python`" -X utf8 $script $extra --result `"$result`" > `"$output`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arguments
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Start-Sleep -Seconds 3
while ((Get-ScheduledTask -TaskName $taskName).State -eq "Running") { Start-Sleep -Seconds 2 }
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false

if (Test-Path $output) { Get-Content $output -Encoding UTF8 }
if (-not (Test-Path $result)) { Write-Output "no result file"; exit 2 }
$parsed = Get-Content $result -Raw -Encoding UTF8 | ConvertFrom-Json
if ($parsed.passed) { Write-Output "E2E PASSED"; exit 0 } else { Write-Output "E2E FAILED"; exit 1 }
