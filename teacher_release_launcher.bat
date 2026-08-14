@echo off
setlocal
set "ROOT=%~dp0"

"%ROOT%课情报告生成器\课情报告生成器.exe"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo 生成未完成。请查看上方提示，或检查“首次配置飞书.bat”中的配置。
  pause
  exit /b %EXIT_CODE%
)

echo.
echo 已完成，正在打开班级压缩包目录……
start "" "%ROOT%output\packages"
endlocal
