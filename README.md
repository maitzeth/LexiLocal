# Ollama Qwen2.5 REST Server + Native Windows UI

A lightweight, self-hosted REST API server backed by [Ollama](https://ollama.com) and the `qwen2.5` model family. Includes a native Windows desktop UI built with [Tauri v2](https://v2.tauri.app/).

Use it for:

- General chat / Q&A through a REST API
- English ↔ Spanish translation
- Local, offline AI inference (no cloud required)

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Server Usage](#server-usage)
- [REST API](#rest-api)
- [Native Windows UI](#native-windows-ui)
- [Configuration](#configuration)
- [Model Options](#model-options)
- [Troubleshooting](#troubleshooting)

---

## Features

- ⚡ Fast, local inference via Ollama
- 🌐 REST API for chat and translation
- 🖥️ Native Windows `.exe` UI (Tauri v2)
- 🔧 Simple bash control script (`start`, `stop`, `status`, `port`, etc.)
- 📝 Easy model switching (`qwen2.5:1.8b`, `qwen2.5:3b`, `qwen2.5:7b`, ...)

---

## Project Structure

```
ollama-qwen-server/
├── server.py                 # FastAPI application
├── run.sh                    # Bash control script
├── requirements.txt          # Python dependencies
├── server.env                # Server configuration
├── server.env.example        # Configuration template
├── launch-ui.bat             # Windows shortcut to open the UI
├── launch-ui.ps1             # PowerShell shortcut to open the UI
├── README.md                 # This file
└── tauri-app/                # Native Windows UI
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    ├── src/
    │   ├── main.ts           # UI logic
    │   └── styles.css        # UI styles
    └── src-tauri/
        ├── Cargo.toml
        ├── tauri.conf.json
        ├── capabilities/
        └── src/main.rs       # Rust backend (start/stop server)
```

---

## Requirements

### Server

- [Ollama](https://ollama.com) installed and running
- Python 3.10 or newer
- Git Bash (on Windows) or any Unix-like shell

### UI (build from source)

- Node.js + npm
- Rust + Cargo
- Visual Studio Build Tools with C++ workload (Windows)

---

## Quick Start

### 1. Install Ollama

Download and install Ollama from [https://ollama.com](https://ollama.com). Make sure it is running:

```bash
ollama --version
```

### 2. Download the model

```bash
ollama pull qwen2.5:3b
```

### 3. Start the server

```bash
./run.sh start
```

The first run installs Python dependencies automatically.

### 4. Test the API

```bash
curl http://localhost:8000/health
```

### 5. Open the native UI (optional)

Double-click:

```
launch-ui.bat
```

Or from PowerShell:

```powershell
.\launch-ui.ps1
```

---

## Server Usage

The `run.sh` script is the easiest way to control the server.

```bash
./run.sh [command]
```

| Command | Description |
|---------|-------------|
| `./run.sh start` | Install dependencies and start the server |
| `./run.sh stop` | Stop the server |
| `./run.sh status` | Show server status and health URL |
| `./run.sh restart` | Restart the server |
| `./run.sh port 8080` | Change the server port |
| `./run.sh pull` | Download/update the model via Ollama |
| `./run.sh logs` | Tail the server log file |

### Change the port

```bash
./run.sh port 8080
./run.sh restart
```

---

## REST API

The server exposes a REST API on `http://localhost:8000` by default.

### `GET /health`

Check if the server and Ollama are reachable.

```bash
curl http://localhost:8000/health
```

**Response:**

```json
{
  "status": "ok",
  "ollama_host": "http://localhost:11434",
  "model": "qwen2.5:3b"
}
```

### `POST /chat`

Send a prompt and get a response.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of Spain?"}'
```

**Response:**

```json
{
  "answer": "The capital of Spain is Madrid."
}
```

Optional `system` message:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello",
    "system": "You are a helpful assistant. Answer in Spanish."
  }'
```

### `POST /translate`

Translate text between English and Spanish.

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, how are you today?",
    "source": "en",
    "target": "es"
  }'
```

**Response:**

```json
{
  "translation": "Hola, ¿cómo estás hoy?",
  "source": "en",
  "target": "es"
}
```

Supported language pairs: `en → es` and `es → en`.

### Python client example

```python
import requests

response = requests.post(
    "http://localhost:8000/chat",
    json={"prompt": "Explain recursion in one sentence."}
)
print(response.json()["answer"])
```

### JavaScript client example

```javascript
const res = await fetch("http://localhost:8000/translate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    text: "The weather is nice today.",
    source: "en",
    target: "es",
  }),
});
const data = await res.json();
console.log(data.translation);
```

---

## Native Windows UI

The Tauri app provides a native Windows interface for the server.

### Run in development mode

```bash
cd tauri-app
npm install
npm run tauri:dev
```

### Build the production `.exe`

```bash
cd tauri-app
npm run tauri:build
```

After building, you will find:

- **Portable executable:**
  `tauri-app/src-tauri/target/release/ollama-qwen-ui.exe`

- **Windows installer:**
  `tauri-app/src-tauri/target/release/bundle/nsis/LexiLocal UI_1.0.0_x64-setup.exe`

The installer creates:
- A Start Menu shortcut: **LexiLocal UI**
- A desktop shortcut: **LexiLocal UI**

### Launch the built UI

Use the shortcuts in the project root:

```batch
launch-ui.bat
```

Or from PowerShell:

```powershell
.\launch-ui.ps1
```

These set the `OLLAMA_QWEN_SERVER_DIR` environment variable automatically so the UI knows where the server project is located.

---

## Configuration

Edit `server.env` to change settings:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

| Variable | Description |
|----------|-------------|
| `OLLAMA_HOST` | URL of the running Ollama instance |
| `OLLAMA_MODEL` | Model name to use (must be available in Ollama) |
| `SERVER_HOST` | Interface to bind the REST server to |
| `SERVER_PORT` | Port for the REST server |

---

## Model Options

The `qwen2.5` family works well for translation and general Q&A.

| Model | Size | Use case |
|-------|------|----------|
| `qwen2.5:1.8b` | ~1.1 GB | Very fast, lower quality, weak hardware |
| `qwen2.5:3b` | ~1.9 GB | **Default**: good balance of speed and quality |
| `qwen2.5:7b` | ~4.7 GB | Higher quality, requires more RAM/VRAM |
| `qwen2.5-coder:3b` | ~2 GB | Optimized for code-related tasks |

Change the model in `server.env` and restart the server. Download a new model with:

```bash
ollama pull qwen2.5:7b
```

---

## Troubleshooting

### `python` command opens the Microsoft Store

The `run.sh` script looks for the real Python installation first. If it still fails, disable the Windows "App execution aliases" for `python.exe` and `python3.exe` in:

`Settings → Apps → Advanced app settings → App execution aliases`

### Server says model not found

Pull the model manually:

```bash
ollama pull qwen2.5:3b
```

### UI cannot find the server directory

Set the environment variable before launching the UI:

```batch
set OLLAMA_QWEN_SERVER_DIR=C:\path\to\ollama-qwen-server
```

Or use the provided `launch-ui.bat` / `launch-ui.ps1` scripts.

### UI start/stop buttons do not work

The UI uses Git Bash (`bash`) to run `run.sh`. Make sure Git Bash is installed and available in the system `PATH`.

### Port already in use

Change the port:

```bash
./run.sh port 8080
./run.sh restart
```

---

## License

MIT — free to use and modify.
