# LexiLocal

A lightweight, self-hosted REST API server backed by [Ollama](https://ollama.com) and the `qwen2.5` model family. Exposes an **OpenAI-compatible API** so any standard client (Spanify, OpenAI SDK, LangChain, Vercel AI SDK, etc.) can use it as a drop-in backend. Includes a native Windows desktop UI built with [Tauri v2](https://v2.tauri.app/).

Use it for:

- General chat / Q&A through a REST API
- English ↔ Spanish translation
- Streaming responses (SSE) like the OpenAI API
- Local, offline AI inference (no cloud required)

---

## Table of Contents

- [Why OpenAI-compatible?](#why-openai-compatible)
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Server Usage](#server-usage)
- [REST API](#rest-api)
- [Native Windows UI](#native-windows-ui)
- [Configuration](#configuration)
- [Network Access (LAN)](#network-access-lan)
- [Model Options](#model-options)
- [Troubleshooting](#troubleshooting)

---

## Why OpenAI-compatible?

The server speaks the **OpenAI Chat Completions format** at `/v1/chat/completions` and `/v1/models`. This was a deliberate choice over a custom REST shape. Reasons:

| Gain | What it means |
|---|---|
| **Ecosystem compatibility** | Any tool that speaks OpenAI works against LexiLocal — the official `openai` SDK (Python/JS/Go/etc.), LangChain, LlamaIndex, Vercel AI SDK, Continue.dev, Aider, Postman, Bruno, and your own Spanify app. |
| **Drop-in replacement** | Swap Ollama for Groq, OpenRouter, Together, or OpenAI later by changing the `base_url` in your client. Zero code changes. |
| **Future-proofing** | The OpenAI chat-completions format is the de facto industry standard. New tools adopt it by default. |
| **Custom logic on top** | LexiLocal keeps all the advantages of a custom server — CORS, activity logging, model filtering, future auth, request inspection — while speaking a standard wire format on the outside. |
| **Streaming for free** | SSE streaming is part of the spec, so any OpenAI-compatible client gets token-by-token responses with no extra work. |

Concretely: with LexiLocal running on `http://192.168.1.6:8000`, this Python code works as-is:

```python
from openai import OpenAI

client = OpenAI(base_url="http://192.168.1.6:8000/v1", api_key="not-needed")
resp = client.chat.completions.create(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

---

## Features

- ⚡ Fast, local inference via Ollama
- 🔌 **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`)
- 📡 **SSE streaming** for token-by-token responses
- 🌐 REST API with chat, translate, health, logs, and model listing
- 🖥️ Native Windows `.exe` UI (Tauri v2) with streaming output
- 🔧 Simple bash control script (`start`, `stop`, `status`, `port`, etc.)
- 📊 Real-time activity log (timestamps, client IPs, request/response bodies)
- 🔀 Works as a backend for [Spanify](https://github.com/maitzeth/Spanify) and any OpenAI-compatible client

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
├── toggle-server.ps1         # Toggle server start/stop from desktop
├── toggle-server.bat         # Batch wrapper for the toggle script
├── create-desktop-shortcut.ps1 # Create desktop shortcuts
├── README.md                 # This file
└── tauri-app/                # Native Windows UI (Tauri v2)
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    ├── src/
    │   ├── main.ts           # UI logic (uses /v1/chat/completions)
    │   └── styles.css
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

### 4. Test the API (OpenAI-compatible)

```bash
curl http://localhost:8000/v1/models
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

### OpenAI-compatible endpoints

These are the primary, recommended endpoints. They follow the [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat) spec.

#### `GET /v1/models`

List available models (proxied from Ollama).

```bash
curl http://localhost:8000/v1/models
```

**Response:**

```json
{
  "object": "list",
  "data": [
    { "id": "qwen2.5:3b", "object": "model", "created": 1790645725, "owned_by": "ollama" },
    { "id": "qwen2.5:7b", "object": "model", "created": 1790645725, "owned_by": "ollama" }
  ]
}
```

#### `POST /v1/chat/completions`

Chat completion. Accepts an OpenAI-format request with `messages` (array of `{role, content}`), `model`, optional `temperature`, `max_tokens`, and `stream`.

**Non-streaming:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is the capital of France?"}
    ],
    "stream": false
  }'
```

**Response:**

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1790645725,
  "model": "qwen2.5:3b",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "Paris." },
      "finish_reason": "stop"
    }
  ]
}
```

**Streaming (SSE):**

```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [{"role": "user", "content": "Count to 5"}],
    "stream": true
  }'
```

Tokens arrive as `data: {...}` SSE events:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant"}}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":"One"}}]}

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{"content":", two"}}]}

...

data: [DONE]
```

### Python client (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",  # server ignores it
)

resp = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

**Streaming with the SDK:**

```python
stream = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True,
)
for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
```

### JavaScript client (OpenAI SDK)

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "not-needed",
});

const resp = await client.chat.completions.create({
  model: "qwen2.5:3b",
  messages: [{ role: "user", content: "Hello" }],
});
console.log(resp.choices[0].message.content);
```

### Using with Spanify

Point Spanify's Ollama adapter at LexiLocal by editing one line:

```ts
// In Spanify: src/lib/providers/ollama.ts
const BASE_URL = "http://192.168.1.6:8000/v1";  // your host IP
```

No other Spanify changes needed — its adapter already speaks this dialect.

### Legacy endpoints (deprecated, still working)

These pre-OpenAI endpoints are kept for backward compatibility. Prefer `/v1/chat/completions` for new code.

#### `POST /chat`

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

Response: `{ "answer": "..." }`. Optional `system` field.

#### `POST /translate`

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source": "en", "target": "es"}'
```

Response: `{ "translation": "...", "source": "en", "target": "es" }`.

### Operational endpoints

#### `GET /health`

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "ok",
  "ollama_host": "http://localhost:11434",
  "model": "qwen2.5:3b"
}
```

#### `GET /logs`

Recent activity log (timestamps, client IPs, request/response bodies). `/health` and `/logs` themselves are filtered out to keep the output clean.

```bash
curl http://localhost:8000/logs?limit=20
```

---

## Native Windows UI

The Tauri v2 app provides a native Windows interface. It uses `/v1/chat/completions` with **SSE streaming**, so responses appear token by token in the UI.

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

### UI features

- **Status indicator** (online/offline) with model name and Ollama URL
- **Server controls** (Start / Stop) — spawns the Python server via Git Bash
- **Chat panel** with model selector dropdown (populated from `/v1/models`) and SSE streaming output
- **Translate panel** (EN ↔ ES) with SSE streaming
- **REST API panel** with copyable curl examples for `/v1/models`, `/v1/chat/completions`, and SSE streaming
- **Activity Log** showing recent requests with timestamps, client IPs, method, path, status, and truncated request/response bodies

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
| `OLLAMA_MODEL` | Default model name when client omits `model` |
| `SERVER_HOST` | Interface to bind the REST server to |
| `SERVER_PORT` | Port for the REST server |

---

## Network Access (LAN)

The server binds to `0.0.0.0` by default, so any device on your local network can reach it. Replace `localhost` with the host machine's local IP.

### Find the host machine's local IP

**Windows:**
```powershell
ipconfig
```
Look for `IPv4 Address` under your active adapter (e.g. `192.168.1.X`).

**macOS / Linux:**
```bash
ifconfig | grep "inet "
# or
ip addr show
```

### Open the firewall (Windows, one-time, as Administrator)

```powershell
New-NetFirewallRule -DisplayName "LexiLocal Server 8000" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 `
  -Action Allow -Profile Private
```

### Call the API from another machine on the LAN

Replace `<host-ip>` with the actual IP of the machine running the server.

**OpenAI SDK (Python):**

```python
from openai import OpenAI

client = OpenAI(base_url="http://<host-ip>:8000/v1", api_key="not-needed")
resp = client.chat.completions.create(
    model="qwen2.5:3b",
    messages=[{"role": "user", "content": "Hello from another machine"}],
)
print(resp.choices[0].message.content)
```

**curl:**

```bash
curl http://<host-ip>:8000/v1/models

curl -X POST http://<host-ip>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:3b",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**PowerShell:**

```powershell
Invoke-RestMethod -Method Post -Uri "http://<host-ip>:8000/v1/chat/completions" `
  -ContentType "application/json" `
  -Body '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"Hi"}]}'
```

### Point the desktop UI at a remote server

In the UI, change the URL field (top right) from `http://localhost:8000` to `http://<host-ip>:8000`. All features (chat, translate, model list, logs) will use that URL.

### Troubleshooting

| Problem | Fix |
|---------|-----|
| Connection refused | Make sure the server is running: `./run.sh status` |
| Timeout / unreachable | Open the firewall rule (see above) and confirm both machines are on the same network/subnet |
| Works from same machine, not from others | Confirm `SERVER_HOST=0.0.0.0` in `server.env` |
| Works, but response is blocked | The server sends CORS headers (`*`), so web clients should be fine |

> **Security note:** The server has no authentication. Anyone on your LAN can call it. For production use, put it behind a reverse proxy with auth (nginx, Caddy, etc.).

---

## Model Options

The `qwen2.5` family works well for translation and general Q&A.

| Model | Size | Use case |
|-------|------|----------|
| `qwen2.5:1.8b` | ~1.1 GB | Very fast, lower quality, weak hardware |
| `qwen2.5:3b` | ~1.9 GB | **Default**: good balance of speed and quality |
| `qwen2.5:7b` | ~4.7 GB | Higher quality, requires more RAM/VRAM |
| `qwen2.5-coder:3b` | ~2 GB | Optimized for code-related tasks |
| `qwen2.5:14b` | ~9 GB | Best quality, needs ~12 GB RAM |

Change the model in `server.env` (default) or per-request via the `model` field in `/v1/chat/completions`. Download a new model with:

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

### UI shows "Offline" or "Failed to fetch"

1. Check the server is running: `./run.sh status` and `curl http://localhost:8000/health`
2. If running from another machine, check the URL field in the UI matches the host IP
3. Open the firewall rule for port 8000 on private networks

---

## License

MIT — free to use and modify.
