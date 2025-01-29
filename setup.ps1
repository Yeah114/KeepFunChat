# 检测是否是Windows环境
if ($IsWindows) {
    Write-Host "Detected Windows environment."

    # 检查 winget 命令是否存在
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Installing winget..."
        # 使用 PowerShell 安装 winget
        Install-Script winget-install -Force
    }

    # 使用 winget 安装 Python
    winget install --id Python.Python.3 --accept-package-agreements --accept-source-agreements

    # 换源 pip
    python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    # 更新 pip 并安装 Python 包
    python -m pip install --upgrade pip setuptools
    python -m pip install BDXConverter uiautomator2 websockets tqdm rich prompt_toolkit requests

    # 安装 Rust
    if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
        Write-Host "Installing Rust..."
        # 使用 PowerShell 安装 Rust
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
        winget install --id Rustlang.Rustup -e
    }

    # 安装 uvicorn 和 fastapi
    python -m pip install uvicorn fastapi

    Write-Host "Setup completed."
} else {
    Write-Host "This script is designed to run on Windows."
}