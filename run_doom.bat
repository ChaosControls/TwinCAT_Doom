@echo off
rem ============================================================
rem run_doom.bat — launched by the PLC via NT_StartProcess when
rem MAIN enters Doom mode (state 40).
rem
rem Runs headless (TwinCAT service session — no visible window).
rem All output goes to doom_log.txt for debugging.
rem
rem NT_StartProcess runs this as SYSTEM, whose PATH does not
rem include per-user Python installs — so we fall back to the
rem full path if "python" is not found. Adjust PYTHON_FALLBACK
rem if Python lives somewhere else on this machine.
rem
rem TARGET/PORT: --plc local resolves this machine's own AMS Net
rem ID through the TwinCAT router. If the PLC runtime uses its
rem own Net ID or a non-default port (see probe_ads.py), set
rem them here.
rem ============================================================
set "PYTHON_FALLBACK=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
set "TARGET=local"
set "PORT=851"

cd /d %~dp0

set "PYTHON=python"
where python >nul 2>&1 || set "PYTHON=%PYTHON_FALLBACK%"

"%PYTHON%" main.py --plc %TARGET% --port %PORT% --auto-exit > doom_log.txt 2>&1
