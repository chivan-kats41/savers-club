@echo off
REM Windows backup of the savings_hub database. Schedule with Task Scheduler (daily).
REM Create C:\savings_hub_backup.cnf containing:   [client]  user=savings_hub_user  password=YOUR_PASSWORD
REM and restrict its permissions to your account. Adjust MYSQLDUMP to your install (XAMPP: C:\xampp\mysql\bin\mysqldump.exe).
setlocal
set MYSQLDUMP="C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"
set DB_NAME=savings_hub
set BACKUP_DIR=C:\savings_hub_backups
set CNF=C:\savings_hub_backup.cnf
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do set STAMP=%%c%%b%%a
set OUT=%BACKUP_DIR%\%DB_NAME%_%STAMP%_%time:~0,2%%time:~3,2%.sql
%MYSQLDUMP% --defaults-extra-file=%CNF% --single-transaction --routines --triggers --no-tablespaces --default-character-set=utf8mb4 %DB_NAME% > "%OUT%"
if errorlevel 1 ( echo BACKUP FAILED & del "%OUT%" & exit /b 1 )
REM delete backups older than 14 days
forfiles /p "%BACKUP_DIR%" /m %DB_NAME%_*.sql /d -14 /c "cmd /c del @path" 2>nul
echo Backup ok: %OUT%
echo REMINDER: also back up the media and private_media folders.
endlocal
