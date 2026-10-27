@echo off
rem Inicia el asistente en segundo plano (aparece un icono naranja en la bandeja, junto al reloj).
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0asistente.py"
