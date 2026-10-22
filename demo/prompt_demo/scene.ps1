# Sets up the desktop for the prompt demo (run inside the logged-on session):
# prompt-expert with demo WAVs as the microphone, Explorer on the sales folder,
# and the prompt page as an Edge app window in front.
$ErrorActionPreference = "Continue"
Start-Transcript -Path C:\demo\scene.log -Force | Out-Null
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class Win {
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    public static IntPtr FindByPrefix(string prefix) {
        IntPtr found = IntPtr.Zero;
        EnumWindows((h, l) => {
            var text = new StringBuilder(512);
            GetWindowText(h, text, 512);
            if (IsWindowVisible(h) && text.ToString().StartsWith(prefix)) { found = h; return false; }
            return true;
        }, IntPtr.Zero);
        return found;
    }
    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool repaint);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[Win]::SetProcessDPIAware() | Out-Null  # window coordinates below are physical pixels

function Wait-Window([string]$title) {
    for ($i = 0; $i -lt 60; $i++) {
        $h = [Win]::FindByPrefix($title)
        if ($h -ne [IntPtr]::Zero) { return $h }
        Start-Sleep -Milliseconds 500
    }
    throw "window not found: $title"
}

(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }
Get-Process msedge, notepad, prompt-expert -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1

$exe = "$env:LOCALAPPDATA\Programs\prompt-expert\prompt-expert.exe"

# Same starting history every take: two older paths for the Recent Paths menu.
$history = @(
    @{ id = "a1"; path = "$env:USERPROFILE\Documents\보고서\주간 보고 10월 3주차.docx" },
    @{ id = "a2"; path = "C:\Projects\sales-dashboard" }
)
[IO.File]::WriteAllText("$env:APPDATA\prompt-expert\path-history.json", (ConvertTo-Json $history),
                        (New-Object Text.UTF8Encoding $false))
& $exe --install-shell-menu | Out-Null
Start-Process $exe -ArgumentList '--test-audio C:\demo\say1_16k.wav --test-audio C:\demo\say2_16k.wav'

$sales = "$env:USERPROFILE\Documents\매출 데이터"
Start-Process explorer.exe "`"$sales`""
$explorer = Wait-Window "매출 데이터"
[Win]::ShowWindow($explorer, 9) | Out-Null  # SW_RESTORE: Explorer remembers "maximized"
[Win]::MoveWindow($explorer, 400, 196, 612, 490, $true) | Out-Null

$msedge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
Start-Process $msedge '--app=file:///C:/demo/prompt.html --no-first-run --window-position=13,13 --window-size=496,480'  # DIPs at 125% = 620x600 px
$edge = Wait-Window "AI 프롬프트"
Start-Sleep 2
[Win]::SetForegroundWindow($edge) | Out-Null

# Keep our tray icon visible next to the clock instead of in the overflow.
Start-Sleep 3
Get-ChildItem "HKCU:\Control Panel\NotifyIconSettings" | ForEach-Object {
    if ((Get-ItemProperty $_.PSPath).ExecutablePath -like "*prompt-expert.exe") { Set-ItemProperty $_.PSPath IsPromoted 1 }
}
