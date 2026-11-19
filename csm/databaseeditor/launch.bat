@echo off
setlocal
cd /d "%~dp0"

set "PY="

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if %errorlevel%==0 set "PY=py -3"
)

if not defined PY (
    where python >nul 2>&1
    if %errorlevel%==0 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
        if %errorlevel%==0 set "PY=python"
    )
)

if not defined PY (
    for %%D in (
        "%LocalAppData%\Programs\Python\Python313"
        "%LocalAppData%\Programs\Python\Python312"
        "%LocalAppData%\Programs\Python\Python311"
        "%LocalAppData%\Programs\Python\Python310"
        "%ProgramFiles%\Python313"
        "%ProgramFiles%\Python312"
        "%ProgramFiles%\Python311"
        "%ProgramFiles%\Python310"
        "C:\Python313"
        "C:\Python312"
        "C:\Python311"
        "C:\Python310"
    ) do (
        if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
    )
)

if not defined PY (
    echo [ERROR] Python 3.10+ not found. Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo Using Python: %PY%
%PY% server.py %*
if %errorlevel% neq 0 (
    echo.
    echo Server exited with error %errorlevel%.
    pause
)
