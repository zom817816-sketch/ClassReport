$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = 'python'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$appName = 'ClassReportTeacherGUI'
$stagingRoot = Join-Path $projectRoot "build\gui_$timestamp"
$distRoot = Join-Path $stagingRoot 'dist'
$releaseRoot = Join-Path $projectRoot "release\ClassReport_GUI_$timestamp"
$embeddedConfig = "$(Join-Path $projectRoot '.env');embedded"

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    throw '未找到 .env，无法构建含内置凭据的教师版。'
}

& $python -m pip install -r (Join-Path $projectRoot 'requirements-build.txt')
& $python -m PyInstaller --noconfirm --clean --noconsole --onefile --name $appName --distpath $distRoot --workpath (Join-Path $stagingRoot 'work') --specpath $stagingRoot --add-data $embeddedConfig --collect-data matplotlib --collect-data reportlab (Join-Path $projectRoot 'teacher_gui_launcher.py')

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Copy-Item (Join-Path $distRoot "$appName.exe") $releaseRoot
Write-Host "GUI 教师版已生成：$releaseRoot"
Write-Warning '该 EXE 内含飞书凭据，仅限受控设备使用；请勿公开传播。'
