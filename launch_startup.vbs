Set FSO = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir
WScript.Sleep 2000
WshShell.Run "pythonw.exe """ & ScriptDir & "\jarvis.py"" --startup", 0, False
