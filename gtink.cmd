@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    py gtink.py --help
    pause
) else (
    py gtink.py %*
)
