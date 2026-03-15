'' launch_bot.vbs — Starts Discord bot silently at logon (15s delay for network)
'' Logs to: AppData\Local\pse_quant\logs\bot.log
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "cmd /c ""timeout /t 15 /nobreak > nul && cd /d C:\Users\Josh\Documents\pse-quant-saas && py discord\bot.py >> C:\Users\Josh\AppData\Local\pse_quant\logs\bot.log 2>&1""", 0, False
Set shell = Nothing
