"""
Lightweight REST server backed by a local Ollama instance.
Default model: qwen2.5:3b (good for EN<->ES translation and general Q&A).
"""

import os
import sys
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# In-memory ring buffer of recent requests (timestamp, client IP, method, path, status).
LOG_MAX_ENTRIES = 200
_request_log: deque = deque(maxlen=LOG_MAX_ENTRIES)
_log_lock = threading.Lock()


def _record_request(client_ip: str, method: str, path: str, status_code: int) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "client_ip": client_ip,
        "method": method,
        "path": path,
        "status": status_code,
    }
    with _log_lock:
        _request_log.append(entry)


def _client_ip(request: Request) -> str:
    # Honour common proxy headers when present, else fall back to the socket peer.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def ollama_generate(prompt: str, system: str | None = None, stream: bool = False) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": 0.3},
    }
    if system:
        payload["system"] = system

    try:
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running?") from exc
    except requests.exceptions.Timeout as exc:
        raise HTTPException(status_code=504, detail="Ollama request timed out.") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Checking Ollama at %s", OLLAMA_HOST)
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL not in models:
            logger.warning("Model '%s' not found in Ollama. Pull it with: ollama pull %s", OLLAMA_MODEL, OLLAMA_MODEL)
        else:
            logger.info("Model '%s' is available.", OLLAMA_MODEL)
    except requests.exceptions.RequestException as exc:
        logger.error("Ollama does not appear to be running at %s: %s", OLLAMA_HOST, exc)
    yield


app = FastAPI(title="Ollama Qwen2.5 Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    client_ip = _client_ip(request)
    response = await call_next(request)
    _record_request(client_ip, request.method, request.url.path, response.status_code)
    return response


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt")
    system: str | None = Field(None, description="Optional system message")


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to translate")
    source: str = Field(..., pattern="^(en|es)$", description="Source language: en or es")
    target: str = Field(..., pattern="^(en|es)$", description="Target language: en or es")


class HealthResponse(BaseModel):
    status: str
    ollama_host: str
    model: str


class LogEntry(BaseModel):
    timestamp: str
    client_ip: str
    method: str
    path: str
    status: int


@app.get("/health", response_model=HealthResponse)
def health():
    ollama_ok = False
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        ollama_ok = resp.status_code == 200
    except requests.exceptions.RequestException:
        pass

    return HealthResponse(
        status="ok" if ollama_ok else "ollama-unreachable",
        ollama_host=OLLAMA_HOST,
        model=OLLAMA_MODEL,
    )


@app.get("/logs", response_model=List[LogEntry])
def get_logs(limit: int = 50):
    """Return the most recent request log entries (newest first)."""
    with _log_lock:
        entries = list(_request_log)[-limit:][::-1]
    return entries


@app.post("/chat")
def chat(req: ChatRequest):
    answer = ollama_generate(req.prompt, system=req.system)
    return {"answer": answer}


@app.post("/translate")
def translate(req: TranslateRequest):
    if req.source == req.target:
        raise HTTPException(status_code=400, detail="Source and target languages must differ.")

    system = (
        "You are a professional translator. "
        "Return ONLY the translated text, with no explanations, notes, or extra formatting."
    )
    direction = f"{req.source.upper()} -> {req.target.upper()}"
    prompt = f"Translate the following text from {direction}:\n\n{req.text}"

    translated = ollama_generate(prompt, system=system)
    return {
        "translation": translated,
        "source": req.source,
        "target": req.target,
    }


if __name__ == "__main__":
    logger.info("Starting server on %s:%s using model %s", SERVER_HOST, SERVER_PORT, OLLAMA_MODEL)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
