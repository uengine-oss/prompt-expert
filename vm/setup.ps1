# Runs once at first logon of the test VM (from the unattend CD).
$ErrorActionPreference = "Continue"
Start-Transcript -Path C:\winwhisper-setup.log -Append
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# virtio network driver (and the rest of the ARM64 virtio drivers)
$virtio = Get-PSDrive -PSProvider FileSystem | Where-Object { Test-Path "$($_.Root)NetKVM\w11\ARM64" } | Select-Object -First 1
if ($virtio) {
    foreach ($d in "NetKVM", "viostor", "vioserial", "Balloon", "viorng", "vioinput") {
        pnputil.exe /add-driver "$($virtio.Root)$d\w11\ARM64\*.inf" /install
    }
}
Start-Sleep -Seconds 15

# Keep the desktop session alive and unlocked: tests drive the real keyboard/clipboard.
powercfg.exe /change monitor-timeout-ac 0
powercfg.exe /change standby-timeout-ac 0
powercfg.exe /change hibernate-timeout-ac 0
reg.exe add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization" /v NoLockScreen /t REG_DWORD /d 1 /f
reg.exe add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f
$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty $winlogon AutoAdminLogon "1"
Set-ItemProperty $winlogon DefaultUserName "ww"
Set-ItemProperty $winlogon DefaultPassword "WinWhisper1!"

# OpenSSH server: Windows capability first, GitHub release as fallback.
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = "$env:TEMP\OpenSSH-ARM64.zip"
    Invoke-WebRequest "https://github.com/PowerShell/Win32-OpenSSH/releases/latest/download/OpenSSH-ARM64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath "C:\Program Files" -Force
    & "C:\Program Files\OpenSSH-ARM64\install-sshd.ps1"
}
New-Item -ItemType Directory -Force C:\ProgramData\ssh | Out-Null
Copy-Item "$here\authorized_keys" C:\ProgramData\ssh\administrators_authorized_keys -Force
icacls.exe C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
Set-Service sshd -StartupType Automatic
Start-Service sshd
New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue

"done" | Out-File C:\winwhisper-setup.done
Stop-Transcript
