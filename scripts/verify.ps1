<#
使用临时 pgvector 容器运行独立数据库验证；不连接开发/生产业务库。
默认使用已有项目虚拟环境和 node_modules，不执行依赖安装。
先在 PyCharm 确认 PythonPath 与 retrue-server 模块解释器一致。
#>
param(
    [string]$PythonPath = "",
    [int]$DatabasePort = 58432,
    [switch]$UseExistingTestDatabase
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $projectRoot 'retrue-server/.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw '缺少项目解释器，请先配置 retrue-server 虚拟环境' }
if ($DatabasePort -lt 1024 -or $DatabasePort -gt 65535) { throw '独立测试库端口必须在 1024 到 65535 之间' }

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw '验证命令失败，停止后续步骤' }
}

$temporaryContainer = $null
$previousLocation = Get-Location
$environmentNames = @('DJANGO_SETTINGS_MODULE', 'RETRUE_TEST_DB_PORT', 'RETRUE_TEST_DB_HOST', 'RETRUE_TEST_DB_USER', 'RETRUE_TEST_DB_PASSWORD', 'AI_PROVIDER', 'AI_CONFIG_FILE', 'LOG_TO_FILE')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:DJANGO_SETTINGS_MODULE = 'config.settings_test'
    $env:RETRUE_TEST_DB_PORT = [string]$DatabasePort
    $env:RETRUE_TEST_DB_HOST = '127.0.0.1'
    $env:RETRUE_TEST_DB_USER = 'retrue_test'
    $env:RETRUE_TEST_DB_PASSWORD = 'validation_only'
    $env:AI_PROVIDER = 'mock'
    $env:AI_CONFIG_FILE = ''
    $env:LOG_TO_FILE = 'false'
    if (-not $UseExistingTestDatabase) {
        $temporaryContainer = 'retrue-validation-' + ([guid]::NewGuid().ToString('N').Substring(0, 12))
        Invoke-Checked 'docker' @('run', '--detach', '--name', $temporaryContainer, '--env', 'POSTGRES_DB=retrue_validation', '--env', 'POSTGRES_USER=retrue_test', '--env', 'POSTGRES_PASSWORD=validation_only', '--publish', "127.0.0.1:${DatabasePort}:5432", 'pgvector/pgvector:pg16')
        $available = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            & docker exec $temporaryContainer pg_isready -U retrue_test -d retrue_validation *> $null
            if ($LASTEXITCODE -eq 0) { $available = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $available) { throw '临时 PostgreSQL 未就绪，停止验证' }
    }
    Set-Location (Join-Path $projectRoot 'retrue-server')
    Invoke-Checked $PythonPath @('-m', 'pip', 'check')
    Invoke-Checked $PythonPath @('manage.py', 'check')
    Invoke-Checked $PythonPath @('manage.py', 'makemigrations', '--check', '--dry-run')
    # Django 只在 test_retrue_validation 创建/销毁测试库，后端不使用 --parallel。
    Invoke-Checked $PythonPath @('manage.py', 'test', '--noinput', '--verbosity', '1')
    Set-Location (Join-Path $projectRoot 'retrue-web')
    Invoke-Checked 'npm.cmd' @('run', 'test')
    Invoke-Checked 'npm.cmd' @('run', 'build')
    Write-Output '独立后端、前端测试和生产构建全部通过'
}
finally {
    Set-Location $previousLocation
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
    # 仅清理本脚本创建的随机容器；不删卷、不操作已有数据库或其它容器。
    if ($temporaryContainer -and $temporaryContainer -match '^retrue-validation-[a-f0-9]{12}$') {
        & docker rm --force $temporaryContainer *> $null
    }
}
