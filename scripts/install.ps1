[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

$batPath = Join-Path $DIR "audio2text.bat"
if (-not (Test-Path $batPath)) {
    Write-Host "Помилка: не знайдено audio2text.bat у $DIR"
    Write-Host "Запустіть цей скрипт з розпакованої папки Audio2Text."
    pause
    exit 1
}

try {
    $WShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Audio2Text.lnk")
    $Shortcut.TargetPath = $batPath
    $Shortcut.WorkingDirectory = $DIR
    $Shortcut.Description = "Транскрипція аудіо в текст (WhisperX)"
    $Shortcut.Save()
    Write-Host "✅ Встановлено! Ярлик Audio2Text у меню Пуск."
    Write-Host "   Папка: $DIR"
    Write-Host ""
    Write-Host "Якщо програма не запускається — запустіть вручну:"
    Write-Host "  $batPath"
    Write-Host "і скопіюйте текст помилки."
} catch {
    Write-Host "Помилка створення ярлика: $_"
    pause
    exit 1
}
