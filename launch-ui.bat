@echo off
setlocal
set OLLAMA_QWEN_SERVER_DIR=%~dp0
start "" "%~dp0tauri-app\src-tauri\target\release\ollama-qwen-ui.exe"
