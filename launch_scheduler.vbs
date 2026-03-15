'' launch_scheduler.vbs — Starts APScheduler silently at logon (30s delay)
'' Logs to: AppData\Local\pse_quant\logs\scheduler.log
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "cmd /c ""timeout /t 30 /nobreak > nul && cd /d C:\Users\Josh\Documents\pse-quant-saas && py scheduler.py >> C:\Users\Josh\AppData\Local\pse_quant\logs\scheduler.log 2>&1""", 0, False
Set shell = Nothing
