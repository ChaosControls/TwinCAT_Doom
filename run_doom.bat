@echo off
rem ============================================================
rem run_doom.bat — launched by the PLC via NT_StartProcess when
rem MAIN enters Doom mode (state 40).
rem
rem Runs headless (TwinCAT service session — no visible window).
rem All output goes to doom_log.txt for debugging.
rem
rem --plc local resolves the machine's own AMS Net ID through the
rem TwinCAT router (loopback 127.0.0.1.1.1 is NOT routed and fails
rem with ADS error 6). --auto-exit makes Python shut down when
rem DOOMgvl.bActive goes FALSE (Y-button reset on the PLC).
rem ============================================================
cd /d %~dp0
python main.py --plc local --auto-exit > doom_log.txt 2>&1
