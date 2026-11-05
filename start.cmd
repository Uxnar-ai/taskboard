@echo off
rem taskboard · <HOST> 任务卡发布站 · 无窗口启动（与 wb 用量看板同一套路）
cd /d "%~dp0"
set PY=<LOCAL_PATH>\.workbuddy\binaries\python\envs\default\Scripts\pythonw.exe
start "" "%PY%" "%~dp0server.py" --host 0.0.0.0 --port 8802
