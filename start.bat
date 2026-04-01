@echo off
chcp 65001 >nul
title WeChat2Word

:: 激活虚拟环境（如存在）
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

:: 启动程序（传递所有参数）
python wechat2word.py %*

:: 保留窗口以便查看结果
echo.
pause
