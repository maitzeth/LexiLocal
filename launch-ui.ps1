$env:OLLAMA_QWEN_SERVER_DIR = $PSScriptRoot
$exe = Join-Path $PSScriptRoot "tauri-app\src-tauri\target\release\ollama-qwen-ui.exe"
Start-Process -FilePath $exe -WorkingDirectory $PSScriptRoot
