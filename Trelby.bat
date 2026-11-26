@echo off
rem Abre Scripting (editor de guiones) en su propia ventana translucida.
cd /d "%~dp0"
if exist "ventana\scripting\Scripting.exe" (
  start "" "ventana\scripting\Scripting.exe"
) else if exist "ventana\out\Trelby.exe" (
  start "" "ventana\out\Trelby.exe"
) else (
  start "" pythonw server.py
)
