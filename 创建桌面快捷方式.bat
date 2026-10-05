@echo off
chcp 65001 >nul
setlocal
set "EXEDIR=%~dp0dist\lite browser"
set "EXE=%EXEDIR%\lite browser.exe"
if not exist "%EXE%" (
    echo 未找到 "%EXE%"
    echo 请先运行 build_exe.bat 打包，或从源码方式使用 run.bat 启动。
    pause
    exit /b 1
)
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\lite browser.lnk'); $s.TargetPath='%EXE%'; $s.WorkingDirectory='%EXEDIR%'; $s.IconLocation='%EXE%'; $s.Description='lite browser - 作者 lvzian'; $s.Save()"
echo 已在桌面创建快捷方式：lite browser
pause
exit /b 0
