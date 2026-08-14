param(
    [switch]$UseCurrentConfig
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = 'python'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$appName = 'ClassReportGenerator'
$stagingRoot = Join-Path $projectRoot "build\teacher_$timestamp"
$distRoot = Join-Path $stagingRoot 'dist'
$releaseRoot = Join-Path $projectRoot "release\ClassReport_Teacher_$timestamp"

& $python -m pip install -r (Join-Path $projectRoot 'requirements-build.txt')
& $python -m PyInstaller --noconfirm --clean --onedir --name $appName --distpath $distRoot --workpath (Join-Path $stagingRoot 'work') --specpath $stagingRoot --collect-data matplotlib --collect-data reportlab (Join-Path $projectRoot 'teacher_launcher.py')

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Copy-Item -Recurse (Join-Path $distRoot $appName) $releaseRoot
Copy-Item (Join-Path $projectRoot 'teacher_release_launcher.bat') (Join-Path $releaseRoot 'Start_Generate_Reports.bat')
Copy-Item (Join-Path $projectRoot '教师版使用说明.md') $releaseRoot
Copy-Item (Join-Path $projectRoot 'teacher_config.env.example') (Join-Path $releaseRoot '.env')

if ($UseCurrentConfig) {
    Copy-Item (Join-Path $projectRoot '.env') (Join-Path $releaseRoot '.env') -Force
    Write-Warning '已复制当前 .env。请仅向获授权的教师分发该文件夹。'
}

Write-Host "教师版已生成：$releaseRoot"
Write-Host '未使用 -UseCurrentConfig 时，请让管理员在发布包 .env 中填写令牌后再分发。'
