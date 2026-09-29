"""
Lightweight REST server backed by a local Ollama instance.
Default model: qwen2.5:3b (good for EN<->ES translation and general Q&A).
"""

import os
import sys
import json
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

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

# Paths whose bodies we want to capture in the activity log.
LOGGED_PATHS = {"/chat", "/translate"}
# Paths we never record in the activity log (high-frequency, low-signal).
IGNORED_PATHS = {"/health", "/logs"}
# How many characters of each body to keep in the log entry.
BODY_PREVIEW_CHARS = 240
# How many bytes of the request body to read at most.
MAX_BODY_BYTES = 64 * 1024

LOG_MAX_ENTRIES = 200
_request_log: deque = deque(maxlen=LOG_MAX_ENTRIES)
_log_lock = threading.Lock()


def _record_request(
    client_ip: str,
    method: str,
    path: str,
    status_code: int,
    request_body: Optional[str] = None,
    response_body: Optional[str] = None,
) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "client_ip": client_ip,
        "method": method,
        "path": path,
        "status": status_code,
        "request_body": request_body,
        "response_body": response_body,
    }
    with _log_lock:
        _request_log.append(entry)


def _truncate(text: str) -> str:
    if text is None:
        return None
    if len(text) <= BODY_PREVIEW_CHARS:
        return text
    return text[:BODY_PREVIEW_CHARS] + "..."


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


async def _read_request_body(request: Request) -> bytes:
    """Read up to MAX_BODY_BYTES from the request, then restore the receive
    channel so downstream handlers can read the body again."""
    body = await request.body()
    # Starlette caches body() on the Request instance automatically.
    return body


def _decode_body(body: bytes) -> str:
    if not body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    # If it looks like JSON, pretty-print compactly so it fits the preview better.
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except (ValueError, TypeError):
        return text


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
    path = request.url.path

    # For paths we care about, capture request and response bodies.
    capture_bodies = (
        request.method in ("POST", "PUT", "PATCH")
        and path in LOGGED_PATHS
        and path not in IGNORED_PATHS
    )

    request_body_text: Optional[str] = None
    response_body_text: Optional[str] = None

    if capture_bodies:
        raw = await _read_request_body(request)
        raw = raw[:MAX_BODY_BYTES]
        request_body_text = _truncate(_decode_body(raw))

    response = await call_next(request)

    if path in IGNORED_PATHS:
        # Still don't record these at all.
        return response

    if capture_bodies and path in LOGGED_PATHS:
        # Drain the response body iterator so we can both forward it and log it.
        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)
        response_body_text = _truncate(_decode_body(body_bytes[:MAX_BODY_BYTES]))

        # Rebuild a fresh response with the captured body so the client still gets it.
        from fastapi.responses import Response
        new_response = Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
        response = new_response

    _record_request(
        client_ip=client_ip,
        method=request.method,
        path=path,
        status_code=response.status_code,
        request_body=request_body_text,
        response_body=response_body_text,
    )
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
    request_body: Optional[str] = None
    response_body: Optional[str] = None


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
        entries = [e for e in _request_log if e["path"] not in IGNORED_PATHS][-limit:][::-1]
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
