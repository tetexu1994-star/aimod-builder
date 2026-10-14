# AI Mod Builder PowerShell Launcher
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  AI Mod Builder - 游戏 Mod 制作与安全工作台" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path "$ScriptDir\agmod\__init__.py")) {
    Write-Host "[错误] 请先解压缩整个 ZIP 压缩包后再运行！不要在压缩包内直接双击。" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

$PyCmd = $null
if (Test-Path "$ScriptDir\runtime\python.exe") {
    $PyCmd = "$ScriptDir\runtime\python.exe"
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    try {
        & python -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $PyCmd = "python" }
    } catch {}
} elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    try {
        & py -3 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $PyCmd = "py -3" }
    } catch {}
}

if (-not $PyCmd) {
    Write-Host "[提示] 本机未检测到有效的 Python 环境。" -ForegroundColor Yellow
    $choice = Read-Host "是否自动下载官方 Python 便携版 (约 15MB)？输入 Y 自动下载，按其他键退出 (Y/N)"
    if ($choice -match "^[yY]") {
        Write-Host "正在下载便携版 Python..." -ForegroundColor Cyan
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $zipPath = "$ScriptDir\python_embed.zip"
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip" -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath "$ScriptDir\runtime" -Force
        Remove-Item $zipPath -Force
        if (Test-Path "$ScriptDir\runtime\python.exe") {
            $PyCmd = "$ScriptDir\runtime\python.exe"
            Write-Host "便携版 Python 配置成功！" -ForegroundColor Green
        }
    }
}

if (-not $PyCmd) {
    Write-Host "[错误] 请先安装 Python 3.10+ (https://www.python.org/downloads/)" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host "启动本地 Web 工作台 (http://127.0.0.1:8765)..." -ForegroundColor Green
if ($PyCmd -eq "py -3") {
    & py -3 -m agmod.ui
} else {
    & $PyCmd -m agmod.ui
}

Read-Host "按回车键退出"
