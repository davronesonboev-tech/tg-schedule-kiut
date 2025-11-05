@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   Telegram Bot - Schedule
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not installed!
    echo Download Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check virtual environment
if not exist "venv\" (
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
if not exist "venv\Lib\site-packages\telegram\" (
    echo [*] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Check .env file
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found!
    echo.
    echo Create .env file from config.env:
    echo 1. Copy config.env to .env
    echo 2. Open .env in text editor
    echo 3. Fill TELEGRAM_BOT_TOKEN and TARGET_CHAT_ID
    echo.
    pause
    exit /b 1
)

REM Start bot
echo.
echo [*] Starting bot...
echo.
python bot_multi.py

REM Keep window open on error
if errorlevel 1 (
    echo.
    echo [ERROR] Bot stopped with error
    pause
    exit /b 1
)

echo.
echo Bot stopped.
pause

