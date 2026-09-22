@echo off
REM Launches the backend (FastAPI/uvicorn) and frontend (Vite) dev servers
REM each in their own window, then opens the web app once Vite is ready.
REM Double-click this file, or run it from cmd.exe / PowerShell.
REM
REM Uses npm.cmd explicitly (not the bare "npm" wrapper) so this also works
REM from a PowerShell session with the default script execution policy.

setlocal

set "REPO_DIR=%~dp0"
set "FRONTEND_DIR=%REPO_DIR%frontend"

echo Starting backend on http://localhost:8000 ...
start "cv-ai backend" cmd /k "cd /d %REPO_DIR% && uv run uvicorn api.main:app --reload"

echo Starting frontend on http://localhost:5173 ...
start "cv-ai frontend" cmd /k "cd /d %FRONTEND_DIR% && npm.cmd run dev"

echo Waiting for the frontend dev server to come up...
timeout /t 5 /nobreak >nul

start "" "http://localhost:5173"

endlocal
