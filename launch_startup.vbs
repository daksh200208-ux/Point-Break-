Set FSO = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir

' Wait 8 seconds on system boot for audio, network, and display drivers to stabilize
WScript.Sleep 8000

' Launch compiled executable if present, else fallback to pythonw
If FSO.FileExists(ScriptDir & "\PointBreak_Commercial.exe") Then
    WshShell.Run """" & ScriptDir & "\PointBreak_Commercial.exe"" --startup", 0, False
ElseIf FSO.FileExists(ScriptDir & "\PointBreak.exe") Then
    WshShell.Run """" & ScriptDir & "\PointBreak.exe"" --startup", 0, False
Else
    WshShell.Run "pythonw.exe """ & ScriptDir & "\jarvis.py"" --startup", 0, False
End If
