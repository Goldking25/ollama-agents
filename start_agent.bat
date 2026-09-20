@echo off
cd /d "%~dp0"
title Ollama Agent Web UI (Port 8100 + Tailscale + SD Forge UI + ComfyUI)
echo ===================================================================
echo   Starting Ollama, SD Forge UI, ComfyUI, Tailscale ^& Web UI
echo ===================================================================
echo.

:: 1. Check if Ollama service is reachable on port 11434
echo [1/6] Checking Ollama service status...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Ollama is not running. Starting Ollama service...
    start "" ollama serve
    echo [*] Waiting for Ollama to initialize...
    timeout /t 5 /nobreak >nul
) else (
    echo [+] Ollama service is running.
)

:: 2. Check and Launch SD WebUI Forge UI on port 7860
echo.
echo [2/6] Checking SD WebUI Forge status (Port 7860)...
curl -s http://127.0.0.1:7860/sdapi/v1/options >nul 2>&1
if %errorlevel% neq 0 (
    if exist "F:\ai\sd-webui-forge-neo\webui-user.bat" (
        echo [!] SD WebUI Forge is not running. Starting Forge UI from F:\ai\sd-webui-forge-neo ...
        start "SD WebUI Forge UI" /D "F:\ai\sd-webui-forge-neo" webui-user.bat
        echo [*] SD WebUI Forge UI launcher started in background window.
    ) else (
        echo [!] F:\ai\sd-webui-forge-neo\webui-user.bat not found. Skipping Forge auto-start.
    )
) else (
    echo [+] SD WebUI Forge API is active on port 7860.
)

:: 3. Check and Launch ComfyUI API on port 8000
echo.
echo [3/6] Checking ComfyUI status (Port 8000)...
curl -s http://127.0.0.1:8000/system_stats >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\Users\manig\Downloads\ComfyUI_windows_portable\run_nvidia_gpu.bat" (
        echo [!] ComfyUI is not running. Starting ComfyUI from C:\Users\manig\Downloads\ComfyUI_windows_portable ...
        start "ComfyUI Portable" /D "C:\Users\manig\Downloads\ComfyUI_windows_portable" run_nvidia_gpu.bat
        echo [*] ComfyUI Portable started in background window.
    ) else (
        echo [!] ComfyUI portable path not found. Skipping ComfyUI auto-start.
    )
) else (
    echo [+] ComfyUI API is active on port 8000.
)

:: 4. Check Virtual Environment
echo.
echo [4/6] Checking Python virtual environment...
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
    echo [+] Using virtual environment: %~dp0.venv
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    echo [+] Using local virtual environment: .venv
) else (
    set "PYTHON_CMD=python"
    echo [!] Virtual environment not found. Falling back to global python.
)

:: 5. Enable Tailscale Remote Network Access
echo.
echo [5/6] Initializing Tailscale Remote Connection...
where tailscale >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Bringing up Tailscale network...
    tailscale up >nul 2>&1
    for /f "tokens=1" %%i in ('tailscale ip -4 2^>nul') do set "TAILSCALE_IP=%%i"
    echo [+] Tailscale is ACTIVE!
) else (
    echo [!] Tailscale CLI not found in PATH. Remote Tailscale IP lookup skipped.
)

:: 6. Launch Web UI bound to 0.0.0.0 (Local + Remote Access)
echo.
echo ===================================================================
echo   Ollama Agents Web Dashboard Ready!
echo.
echo   Local Access  : http://localhost:8100
if defined TAILSCALE_IP (
    echo   Remote Access : http://%TAILSCALE_IP%:8100
)
echo   SD Forge API  : http://127.0.0.1:7860
echo   ComfyUI API   : http://127.0.0.1:8000
echo ===================================================================
echo.

start http://localhost:8100
%PYTHON_CMD% -m ollama_agents.cli serve --host 0.0.0.0 --port 8100

echo.
echo Server shut down.
pause

