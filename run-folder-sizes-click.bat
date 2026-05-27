@echo off
setlocal

call "%~dp0run-folder-sizes.bat" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
pause

exit /b %EXIT_CODE%