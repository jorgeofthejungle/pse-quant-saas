@echo off
:: PSE Quant SaaS — Auto-Start Installer
:: Right-click this file and choose "Run as administrator"
:: Registers all 3 services to start silently at logon

echo PSE Quant SaaS — Registering auto-start tasks...
echo.

:: Get the current logged-on user's SID for the logon trigger
for /f "tokens=*" %%i in ('whoami') do set CURRENT_USER=%%i

:: --- Dashboard ---
schtasks /create /tn "PSE Dashboard" ^
  /tr "wscript.exe \"C:\Users\Josh\Documents\pse-quant-saas\launch_dashboard.vbs\"" ^
  /sc ONLOGON /delay 0000:05 /f
if %errorlevel% equ 0 (
    echo [OK] PSE Dashboard registered
) else (
    echo [FAIL] PSE Dashboard — error %errorlevel%
)

:: --- Discord Bot (15s delay built into VBS) ---
schtasks /create /tn "PSE Discord Bot" ^
  /tr "wscript.exe \"C:\Users\Josh\Documents\pse-quant-saas\launch_bot.vbs\"" ^
  /sc ONLOGON /delay 0000:05 /f
if %errorlevel% equ 0 (
    echo [OK] PSE Discord Bot registered
) else (
    echo [FAIL] PSE Discord Bot — error %errorlevel%
)

:: --- APScheduler (30s delay built into VBS) ---
schtasks /create /tn "PSE Scheduler" ^
  /tr "wscript.exe \"C:\Users\Josh\Documents\pse-quant-saas\launch_scheduler.vbs\"" ^
  /sc ONLOGON /delay 0000:10 /f
if %errorlevel% equ 0 (
    echo [OK] PSE Scheduler registered
) else (
    echo [FAIL] PSE Scheduler — error %errorlevel%
)

echo.
echo Done. All 3 services will start silently at next logon.
echo Logs: C:\Users\Josh\AppData\Local\pse_quant\logs\
echo.
pause
