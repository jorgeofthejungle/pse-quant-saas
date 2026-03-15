'' launch_dashboard.vbs — Starts Flask dashboard silently at logon
'' Logs to: AppData\Local\pse_quant\logs\dashboard.log
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "cmd /c ""cd /d C:\Users\Josh\Documents\pse-quant-saas && py dashboard\app.py >> C:\Users\Josh\AppData\Local\pse_quant\logs\dashboard.log 2>&1""", 0, False
Set shell = Nothing
