@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   lite browser test - 打包 exe
echo ============================================
echo.
echo [1/4] 检查依赖 PySide6 / pythonnet / cryptography ...
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo      未检测到依赖，正在安装 ...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto :fail
) else (
    echo      PySide6 已安装
)
python -c "import pythonnet" 2>nul
if errorlevel 1 (
    echo      安装 pythonnet ...
    python -m pip install pythonnet
)
python -c "import cryptography" 2>nul
if errorlevel 1 (
    echo      安装 cryptography ...
    python -m pip install cryptography
)
echo.
echo [2/4] 生成程序图标 ...
python tools\make_icon.py
if errorlevel 1 goto :fail
echo.
echo [3/4] 使用 PyInstaller 打包 ...
python -m PyInstaller --noconfirm --clean --windowed ^
    --name "lite browser test" ^
    --icon "assets\lite_browser.ico" ^
    --version-file "tools\version_info.txt" ^
    --add-data "assets\lite_browser.ico;assets" ^
    --add-data "lib\webview2;lib\webview2" ^
    --collect-all pythonnet ^
    --collect-all clr_loader ^
    --collect-all cryptography ^
    --hidden-import clr ^
    --hidden-import cffi ^
    lite_browser.py
if errorlevel 1 goto :fail
echo.
echo [4/4] 精简体积（删除用不到的 Qt 组件）...
python tools\slim_dist.py
if errorlevel 1 goto :fail
echo.
echo ============================================
echo  打包完成！
echo  可执行文件：dist\lite browser test\lite browser test.exe
echo ============================================
pause
exit /b 0

:fail
echo.
echo *** 打包失败，请检查上面的错误信息 ***
pause
exit /b 1
