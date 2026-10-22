# Starts the built prompt-expert.exe (with its tray icon) in the logged-on desktop
# session for the demo recording, with demo WAVs standing in for the microphone.
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "dist\prompt-expert\prompt-expert.exe"
$fixtures = Join-Path $root "tests\fixtures"
$config = Join-Path $root "demo-config.json"
'{"model": "small", "language": "auto", "sounds": true}' | Out-File $config -Encoding ascii

Get-Process prompt-expert, notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
$log = "$env:APPDATA\prompt-expert\prompt-expert.log"
$offset = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }

$arguments = "--config `"$config`" --test-audio `"$fixtures\demo_ko.wav`" --test-audio `"$fixtures\demo_en.wav`""
$action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $root
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName PromptExpertDemo -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName PromptExpertDemo

for ($i = 0; $i -lt 300; $i++) {
    Start-Sleep -Seconds 1
    $stream = [IO.File]::Open($log, "Open", "Read", "ReadWrite")
    $stream.Seek($offset, "Begin") | Out-Null
    $text = (New-Object IO.StreamReader($stream)).ReadToEnd()
    $stream.Close()
    if ($text -match "model ready") { break }
}

# Windows 11 hides new tray icons in the overflow; pin ours to the taskbar.
Get-ChildItem "HKCU:\Control Panel\NotifyIconSettings" | ForEach-Object {
    if ((Get-ItemProperty $_.PSPath).ExecutablePath -like "*prompt-expert.exe") {
        Set-ItemProperty $_.PSPath IsPromoted 1
    }
}
Write-Output "ready"
