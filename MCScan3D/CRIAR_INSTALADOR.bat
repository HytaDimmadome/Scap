@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================================
echo   Criando o instalador Scap-Setup.exe (alguns minutos)
echo ======================================================
python -m pip install -r requirements.txt
if errorlevel 1 goto erro
python -m PyInstaller --noconfirm --onefile --windowed --name Scap --icon gui_assets\emblema.ico --add-data "gui_assets;gui_assets" --add-data "visualizador.html;." --add-data "mcscan_leitor.js;." --add-data "mcscan_visualizador.js;." --hidden-import mapscan_gui --hidden-import mapscan_ui --hidden-import mapscan_viewer --collect-all webview mcscan.py
if errorlevel 1 goto erro

set ISCC=
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set ISCC=%%~P
if defined ISCC goto compilar
echo Instalando o Inno Setup (programa que monta instaladores)...
winget install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set ISCC=%%~P
if not defined ISCC goto semiscc
:compilar
"%ISCC%" instalador\Scap.iss
if errorlevel 1 goto erro
echo.
echo PRONTO! O instalador esta em:  %~dp0saida\Scap-Setup.exe
explorer "%~dp0saida"
pause
exit /b 0
:semiscc
echo.
echo Nao consegui instalar o Inno Setup sozinho. Baixe e instale em https://jrsoftware.org/isdl.php e rode este arquivo de novo.
pause
exit /b 1
:erro
echo.
echo DEU ERRO. Tire um print desta janela e me mande.
pause
exit /b 1
