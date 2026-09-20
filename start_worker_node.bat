@echo off
title Ollama Agents Distributed Compute Worker Node (Port 9000 ^& 11434)
echo ===================================================
echo   Ollama Agents General Distributed Worker Node
echo ===================================================
echo.

:: 1. Check if Ollama service is reachable
echo [1/3] Checking Ollama service status...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Ollama is not running. Starting Ollama service...
    set OLLAMA_HOST=0.0.0.0
    start "" ollama serve
    echo [*] Waiting for Ollama to initialize...
    timeout /t 5 /nobreak >nul
) else (
    echo [+] Ollama service is active.
)

:: 2. Check Virtual Environment
echo [2/3] Checking Python virtual environment...
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)

:: 3. Launch General Distributed Compute Worker Node Server on Port 9000
echo [3/3] Launching General Compute Worker Node Server on http://0.0.0.0:9000 ...
echo ---------------------------------------------------
%PYTHON_CMD% -m ollama_agents.worker_node --host 0.0.0.0 --port 9000

echo.
echo Worker node shut down.
pause
