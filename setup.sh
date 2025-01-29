#!/bin/bash

# 检测是否是Termux环境
if [ -f "$PREFIX/etc/apt/sources.list" ]; then
    echo "Detected Termux environment."
    # Termux换源
    sed -i 's@^\(deb.*stable main\)$@#\1\ndeb https://mirrors.tuna.tsinghua.edu.cn/termux/termux-packages-24 stable main@' $PREFIX/etc/apt/sources.list
    apt update && apt upgrade -y
    apt install -y python-numpy python-lxml python-pillow android-tools
else
    echo "Detected Debian-based environment."
    # Debian-based系统换源
    sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list
    apt update && apt-get upgrade -y
    apt install -y python3-numpy python3-lxml python3-pillow -y
    # 包名有时候不一样
    apt install android-tools-adb -y &
    apt install android-tools -y &
    apt install adb -y &
fi

# pip换源并安装Python包
pip install --upgrade pip setuptools -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install BDXConverter uiautomator2 websockets tqdm rich prompt_toolkit requests

# 安装Rust
if [ -f "/data/data/com.termux/files/usr/bin/pkg" ]; then
    pkg install rust -y
else
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
fi

# 安装uvicorn和fastapi
pip install uvicorn fastapi

echo "Setup completed."