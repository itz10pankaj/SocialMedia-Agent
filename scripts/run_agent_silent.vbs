Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Bulletproof project directory path
ProjectDir = "E:\PersonalSocialAgent"
If Not FSO.FolderExists(ProjectDir) Then
    ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
    ProjectDir = FSO.GetParentFolderName(ScriptDir)
End If

Cmd = """" & ProjectDir & "\.venv\Scripts\python.exe"" -m app.auto_runner"
WshShell.CurrentDirectory = ProjectDir
WshShell.Run Cmd, 0, False
