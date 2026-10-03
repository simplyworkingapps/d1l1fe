@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py setup.py
) else (
  python --version >nul 2>nul
  if errorlevel 1 (
    echo.
    echo   Python isn't installed yet. Open PowerShell and run:
    echo     winget install --id Python.Python.3.12 --id Git.Git --id GitHub.cli
    echo   Then close this window and double-click this file again.
  ) else (
    python setup.py
  )
)
echo.
pause
