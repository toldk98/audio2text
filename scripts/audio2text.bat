@echo off
chcp 65001 >nul

set DIR=%~dp0
set ENV_DIR=%DIR%audio2text-env

if not exist "%DIR%main.py" (
    echo [POMYLKA] main.py ne znaydeno v "%DIR%"
    echo.
    echo Zapustit skrypt z rozpakovanoi papky Audio2Text.
    pause
    exit /b 1
)

if not exist "%ENV_DIR%" (
    echo Rozpakuvannia seredovyshcha...
    mkdir "%ENV_DIR%" 2>nul
    if not exist "%DIR%audio2text-env.tar.gz" (
        echo [POMYLKA] audio2text-env.tar.gz ne znaydeno v "%DIR%"
        pause
        exit /b 1
    )
    tar -xzf "%DIR%audio2text-env.tar.gz" -C "%ENV_DIR%"
    if errorlevel 1 (
        echo [POMYLKA] Ne vdalosia rozpakuvaty seredovyshche.
        pause
        exit /b 1
    )
)

if not exist "%ENV_DIR%\Scripts\activate.bat" (
    echo [POMYLKA] Seredovyshche ne znaydeno v "%ENV_DIR%"
    rmdir /s /q "%ENV_DIR%" 2>nul
    pause
    exit /b 1
)

call "%ENV_DIR%\Scripts\activate.bat"

pythonw "%DIR%main.py" %*
if errorlevel 1 (
    python "%DIR%main.py" %*
    if errorlevel 1 (
        echo.
        echo Programu zaversheno z pomylkou (kod: %ERRORLEVEL%).
        pause
    )
)
