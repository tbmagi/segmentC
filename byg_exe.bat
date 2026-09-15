@echo off
rem ---------------------------------------------------------------------------
rem  Bygger Kundesegmentering.exe. Dobbeltklik paa denne fil.
rem
rem  Kraever at Python 3.10 eller nyere er installeret fra python.org.
rem  Resten henter scriptet selv.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo.
echo  Bygger Kundesegmentering.exe
echo  Det tager typisk 2-5 minutter foerste gang.
echo.

rem  "py" foelger med Windows-installationen fra python.org og vaelger den
rem  nyeste Python. Findes den ikke, proeves "python" i stedet.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 build_exe.py %*
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        python build_exe.py %*
    ) else (
        echo.
        echo  Python blev ikke fundet.
        echo.
        echo  Hent Python fra https://www.python.org/downloads/ og saet
        echo  flueben i "Add Python to PATH" under installationen.
        echo.
        pause
        exit /b 1
    )
)

echo.
if %ERRORLEVEL%==0 (
    echo  Programmet ligger nu i mappen "dist".
) else (
    echo  Byggeriet fejlede - se beskeden ovenfor.
)
echo.
pause
