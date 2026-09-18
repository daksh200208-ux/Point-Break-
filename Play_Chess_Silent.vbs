Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\hp\.gemini\antigravity\scratch\tars_commercial_2"
WshShell.Run "pythonw.exe pointbreak_chess.py --auto", 0, False
