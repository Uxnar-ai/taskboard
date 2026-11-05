@echo off
rem 关掉 8802 上的 taskboard
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8802" ^| findstr LISTENING') do (
  taskkill /f /pid %%p >nul 2>&1
)
echo stopped
