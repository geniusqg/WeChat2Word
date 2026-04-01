@echo off
chcp 65001 >nul
title WeChat2Word Build

echo.
echo  ╔════════════════════════════════════════╗
echo  ║     WeChat2Word 构建脚本              ║
echo  ╚════════════════════════════════════════╝
echo.

:: ── 检测 Python ──────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [✗] 未检测到 Python，请先安装 Python 3.8+
    echo    下载地址：https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo [+] %%i

:: ── 安装依赖 ─────────────────────────────────
echo.
echo [*] 安装 Python 依赖（pysqlcipher3、pyinstaller）...
pip install pysqlcipher3 pyinstaller -q
if errorlevel 1 (
    echo.
    echo [!] pysqlcipher3 安装失败！
    echo.
    echo    请确保已安装 Visual Studio Build Tools（含 C++ 生成工具）
    echo    下载地址：https://visualstudio.microsoft.com/downloads/
    echo    安装时勾选 "C++ 生成工具" → 重启后重试
    echo.
    echo    如果仍失败，可跳过 pysqlcipher3：
    echo    pip install pyinstaller
    echo    然后使用 --msg-db 模式（见 README）
    echo.
)

:: ── 创建虚拟环境（可选，防止污染全局）─────────
echo.
set /p USE_VENV="是否创建独立虚拟环境？(y/N): "
if /i "%USE_VENV%"=="y" (
    echo [*] 创建虚拟环境...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install pysqlcipher3 pyinstaller -q
)

:: ── 构建 EXE ─────────────────────────────────
echo.
echo [*] 开始构建 EXE（可能需要 3-5 分钟）...
echo.

echo [1/2] 构建主程序（交互式CLI）...
pyinstaller wechat2word.spec --clean --noconfirm
if errorlevel 1 (
    echo [!] 主程序构建失败，尝试无 spec 模式...
    pyinstaller wechat2word.py --onefile --console --name WeChat2Word --clean
)

echo.
echo [2/2] 构建快速导出工具...
pyinstaller quick_export.spec --clean --noconfirm
if errorlevel 1 (
    echo [!] 快速导出构建失败，忽略...
)

:: ── 整理输出 ─────────────────────────────────
echo.
echo [*] 整理输出目录...
if not exist "dist\WeChat2Word_Portable" mkdir "dist\WeChat2Word_Portable"
if exist "dist\WeChat2Word" (
    xcopy /E /Q /Y "dist\WeChat2Word\*" "dist\WeChat2Word_Portable\" >nul 2>&1
)
if exist "dist\WeChat2Word_Quick" (
    copy "dist\WeChat2Word_Quick\WeChat2Word_Quick.exe" "dist\WeChat2Word_Portable\" >nul 2>&1
)
copy README.md "dist\WeChat2Word_Portable\" >nul 2>&1
copy start.bat "dist\WeChat2Word_Portable\" >nul 2>&1
copy requirements.txt "dist\WeChat2Word_Portable\" >nul 2>&1

:: ── 完成 ─────────────────────────────────────
echo.
echo ════════════════════════════════════════
echo.
echo  [✓] 构建完成！
echo.
echo  输出目录：
echo    dist\WeChat2Word_Portable\
echo.
echo  主要文件：
echo    - WeChat2Word.exe           交互式主程序
echo    - WeChat2Word_Quick.exe     快速导出工具
echo.
echo  使用方法：
echo    双击 WeChat2Word.exe 运行
echo    （首次运行请确保微信 PC 版已登录）
echo.
echo  如遇杀毒软件误报，请将 exe 添加到白名单。
echo.
pause
