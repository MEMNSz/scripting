"""Lanzador de Scripting instalado.

Si la PC tiene .NET 8 (Escritorio), abre la ventana translúcida (Scripting.exe).
Si no, abre el servidor local y Scripting en una ventana de Edge.
"""
import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
EXE = APP / "ventana" / "scripting" / "Scripting.exe"


def has_desktop_net8():
    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")]
    for r in filter(None, roots):
        d = Path(r) / "dotnet" / "shared" / "Microsoft.WindowsDesktop.App"
        if d.exists() and any(p.name.split(".")[0] == "8" for p in d.iterdir()):
            return True
    return False


if EXE.exists() and has_desktop_net8():
    subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
else:
    subprocess.Popen([sys.executable, str(APP / "server.py")], cwd=str(APP))
