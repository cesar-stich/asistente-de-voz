@echo off
rem Reinstala el entorno de Python (solo si moviste la carpeta o algo se rompio).
cd /d "%~dp0"
if exist .venv rmdir /s /q .venv
py -3.13 -m venv .venv || python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Listo. Ahora abre iniciar.bat
pause
