# PowerShell Launcher for Valkyrie RE CLI
$Host.UI.RawUI.WindowTitle = "Valkyrie RE - Offline Security & Reverse Engineering CLI"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$ScriptDir\valkyrie.py" @args
