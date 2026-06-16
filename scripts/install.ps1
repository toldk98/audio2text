$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

$WShell = New-Object -ComObject WScript.Shell
$Shortcut = $WShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Audio2Text.lnk")
$Shortcut.TargetPath = "$DIR\audio2text.bat"
$Shortcut.WorkingDirectory = "$DIR"
$Shortcut.Save()

Write-Host "✅ Встановлено! Audio2Text доступний у меню Пуск."
