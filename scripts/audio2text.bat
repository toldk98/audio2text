@echo off
set DIR=%~dp0
set ENV_DIR=%DIR%audio2text-env
if not exist "%ENV_DIR%" (
    echo Розпакування середовища...
    mkdir "%ENV_DIR%"
    tar -xzf "%DIR%audio2text-env.tar.gz" -C "%ENV_DIR%"
)
call "%ENV_DIR%\Scripts\activate.bat"
python "%DIR%main.py" %*
