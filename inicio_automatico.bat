@echo off
rem Hace que el asistente arranque solo al prender la PC.
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Asistente de voz.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0asistente.py\"'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Listo: el asistente arrancara solo cada vez que prendas la PC.
echo (Para quitarlo: Win+R, escribe shell:startup y borra "Asistente de voz")
pause
