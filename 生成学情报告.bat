@echo off
setlocal
set "PROJECT_DIR=%~dp0"

rem Double-click this file to generate all reports from the data directory.
if exist "D:\ProgramFiles\miniforge\python.exe" (
  "D:\ProgramFiles\miniforge\python.exe" -B "%PROJECT_DIR%run.py" %*
) else (
  python -B "%PROJECT_DIR%run.py" %*
)

if errorlevel 1 pause
endlocal
