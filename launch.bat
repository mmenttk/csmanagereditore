@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 server.py %*
    if errorlevel 1 pause
    goto :eof
)

where python >nul 2>&1
if %errorlevel%==0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if %errorlevel%==0 (
        python server.py %*
        if errorlevel 1 pause
        goto :eof
    )
)

for %%V in (313 312 311 310) do (
    if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
        "%LocalAppData%\Programs\Python\Python%%V\python.exe" server.py %*
        if errorlevel 1 pause
        goto :eof
    )
    if exist "%ProgramFiles%\Python%%V\python.exe" (
        "%ProgramFiles%\Python%%V\python.exe" server.py %*
        if errorlevel 1 pause
        goto :eof
    )
    if exist "C:\Python%%V\python.exe" (
        "C:\Python%%V\python.exe" server.py %*
        if errorlevel 1 pause
        goto :eof
    )
)

echo Could not find Python 3.10+ on this PC.
echo Please install Python 3 from https://www.python.org/downloads/ (check "Add python.exe to PATH").
pause
