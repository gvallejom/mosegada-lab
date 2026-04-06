@echo off
REM Script de instalación rápida para Betis Arbitrage Scanner
REM Windows only

echo.
echo ========================================
echo  BETIS ARBITRAGE SCANNER - SETUP
echo ========================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no está instalado
    echo Descárgalo desde: https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Creando entorno virtual...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Instalando dependencias...
pip install -q -r requirements.txt

echo [3/4] Creando archivo .env...
if not exist .env (
    copy .env.example .env >nul
    echo ✓ Archivo .env creado
    echo IMPORTANTE: Edita .env con tus credenciales Betfair
) else (
    echo ✓ Archivo .env ya existe
)

echo [4/4] Configuración completada!
echo.
echo ========================================
echo  PRÓXIMOS PASOS
echo ========================================
echo.
echo 1. Edita el archivo .env:
echo    - Tu email Betfair en BETFAIR_USERNAME
echo    - Tu contraseña en BETFAIR_PASSWORD
echo    - Tu API Key en BETFAIR_API_KEY
echo.
echo 2. Ejecuta el scanner:
echo    python scanner_hibrido.py
echo.
echo ========================================
echo.
pause