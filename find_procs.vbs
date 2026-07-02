Set objWMI = GetObject("winmgmts:\.\root\cimv2")
Set colProcs = objWMI.ExecQuery("SELECT ProcessId,CommandLine FROM Win32_Process WHERE Name='python.exe'")
For Each proc In colProcs
    WScript.Echo "PID=" & proc.ProcessId & " CMD=" & proc.CommandLine
Next
