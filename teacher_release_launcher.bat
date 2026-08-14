@echo off
setlocal
set "ROOT=%~dp0"

"%ROOT%ClassReportGenerator.exe"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Report generation did not finish. Check the message above and the .env configuration.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo Finished. Opening the class package folder...
start "" "%ROOT%output\packages"
endlocal
