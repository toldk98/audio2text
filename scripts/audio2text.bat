@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set DIR=%~dp0
set ENV_DIR=%DIR%audio2text-env

if not exist "%DIR%main.py" (
    echo [POMYLKA] main.py ne znaydeno.
    pause
    exit /b 1
)

if not exist "%ENV_DIR%\python.exe" (
    if exist "%ENV_DIR%" (
        attrib -R "%ENV_DIR%" /s /d 2>nul
        rmdir /s /q "%ENV_DIR%" 2>nul
    )
    if not exist "%ENV_DIR%" md "%ENV_DIR%"
    if not exist "%DIR%audio2text-env.tar.gz" (
        echo [POMYLKA] audio2text-env.tar.gz ne znaydeno.
        pause
        exit /b 1
    )
    echo Rozpakuvannia seredovyshcha...
    cd /d "%ENV_DIR%"
    tar -xzf "%DIR%audio2text-env.tar.gz"
    if errorlevel 1 (
        echo [POMYLKA] Ne vdalosia rozpakuvaty.
        pause
        exit /b 1
    )
    cd /d "%DIR%"
)

if not exist "%ENV_DIR%\python.exe" (
    echo [POMYLKA] Seredovyshche ne povne.
    pause
    exit /b 1
)

call "%ENV_DIR%\Scripts\activate.bat"
start "" pythonw "%DIR%main.py"
exit 0
