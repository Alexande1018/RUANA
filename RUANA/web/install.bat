@echo off
REM RUANA Dashboard - Script de instalación rápida
REM Windows

echo ==========================================
echo ^>^>^> RUANA Dashboard - Instalacion
echo ==========================================
echo.

REM Cambiar a directorio script
cd /d "%~dp0"

echo Ubicacion: %cd%
echo.

REM Verificar Python
echo ^>^>^> Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python no esta instalado
    exit /b 1
)
echo OK: Python encontrado
echo.

REM Crear venv
if not exist "venv" (
    echo ^>^>^> Creando entorno virtual...
    python -m venv venv
    echo OK: Entorno virtual creado
) else (
    echo OK: Entorno virtual ya existe
)
echo.

REM Activar venv
echo ^>^>^> Activando entorno virtual...
call venv\Scripts\activate.bat
echo OK: Entorno virtual activado
echo.

REM Instalar dependencias
echo ^>^>^> Instalando dependencias...
pip install -q -r requirements.txt
echo OK: Dependencias instaladas
echo.

REM Crear datos de ejemplo
echo ^>^>^> Creando datos de ejemplo...
python run.py
echo.

echo ==========================================
echo OK: Instalacion completada!
echo ==========================================
echo.
echo Para iniciar el dashboard:
echo   venv\Scripts\activate.bat
echo   python run.py
echo.
echo Luego abre: http://localhost:5000
echo.
pause
