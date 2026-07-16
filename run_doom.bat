@echo off
rem ============================================================
rem run_doom.bat — launched by the PLC via NT_StartProcess when
rem MAIN enters Doom mode (state 40).
rem
rem Runs headless (TwinCAT service session — no visible window).
rem All output goes to doom_log.txt for debugging.
rem
rem 127.0.0.1.1.1 = local AMS Net ID (Python runs on the same
rem IPC as the PLC runtime). --auto-exit makes Python shut down
rem when DOOM.bActive goes FALSE (Y-button reset on the PLC).
rem ============================================================
cd /d %~dp0
python main.py --plc 127.0.0.1.1.1 --auto-exit > doom_log.txt 2>&1
