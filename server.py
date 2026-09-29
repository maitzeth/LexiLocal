"""
Lightweight REST server backed by a local Ollama instance.
Default model: qwen2.5:3b (good for EN<->ES translation and general Q&A).

Endpoints:
  POST /v1/chat/completions       - OpenAI-compatible (supports SSE streaming)
  GET  /v1/models                 - OpenAI-compatible model list
  GET  /health                    - liveness + Ollama reachability
  GET  /logs                      - recent activity log
"""

import os
import json
import uuid
import time
import logging
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Tuple

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Paths whose bodies we want to capture in the activity log.
LOGGED_PATHS = {"/v1/chat/completions"}
# Paths we never record in the activity log (high-frequency, low-signal).
IGNORED_PATHS = {"/health", "/logs", "/v1/models"}
BODY_PREVIEW_CHARS = 240
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


def _decode_body(body: bytes) -> str:
    if not body:
        return None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except (ValueError, TypeError):
        return text


def _ollama_chat_non_stream(
    model: str,
    messages: List[dict],
    temperature: float = 0.3,
    num_predict: Optional[int] = None,
) -> str:
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if num_predict is not None:
        payload["options"]["num_predict"] = num_predict
    response = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return (data.get("message") or {}).get("content", "").strip()


def _ollama_chat_stream(
    model: str,
    messages: List[dict],
    temperature: float = 0.3,
    num_predict: Optional[int] = None,
):
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    if num_predict is not None:
        payload["options"]["num_predict"] = num_predict
    response = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=120,
        stream=True,
    )
    response.raise_for_status()
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        msg = data.get("message") or {}
        content = msg.get("content", "")
        done = data.get("done", False)
        yield content, done


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Checking Ollama at %s", OLLAMA_HOST)
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL not in models:
            logger.warning(
                "Model '%s' not found in Ollama. Pull it with: ollama pull %s",
                OLLAMA_MODEL,
                OLLAMA_MODEL,
            )
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

    # Eagerly read the body once so downstream handlers (including our routes)
    # can still call request.body() - Starlette caches it after the first read.
    request_body_text: Optional[str] = None
    if (
        request.method in ("POST", "PUT", "PATCH")
        and path in LOGGED_PATHS
        and path not in IGNORED_PATHS
    ):
        try:
            raw = (await request.body())[:MAX_BODY_BYTES]
            request_body_text = _truncate(_decode_body(raw))
        except Exception:
            request_body_text = None

    response = await call_next(request)

    if path in IGNORED_PATHS:
        return response

    response_body_text: Optional[str] = None

    # Do NOT drain streaming responses - that would buffer the whole stream
    # and defeat SSE. Record a marker instead.
    if isinstance(response, StreamingResponse):
        response_body_text = "(streaming)"
    elif path in LOGGED_PATHS:
        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)
        response_body_text = _truncate(_decode_body(body_bytes[:MAX_BODY_BYTES]))

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


# ---------------------------------------------------------------------------
# OpenAI-compatible endpoints.
# ---------------------------------------------------------------------------


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
    with _log_lock:
        entries = [e for e in _request_log if e["path"] not in IGNORED_PATHS][-limit:][::-1]
    return entries


@app.get("/v1/models")
def list_models():
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {exc}") from exc

    models = [
        {
            "id": m["name"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": "ollama",
        }
        for m in data.get("models", [])
    ]
    return {"object": "list", "data": models}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = json.loads((await request.body()).decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    model = body.get("model") or OLLAMA_MODEL
    messages = body.get("messages") or []
    stream = bool(body.get("stream", False))
    temperature = float(body.get("temperature", 0.3))
    max_tokens = body.get("max_tokens") or body.get("num_predict")

    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created_ts = int(time.time())

    if not stream:
        try:
            content = _ollama_chat_non_stream(
                model, messages, temperature=temperature, num_predict=max_tokens
            )
        except requests.exceptions.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Ollama error: {exc}") from exc

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def event_generator():
        # Send an initial chunk with role, so OpenAI-compatible clients see it.
        yield _sse_chunk(completion_id, created_ts, model, {"role": "assistant"})
        try:
            for content, done in _ollama_chat_stream(
                model, messages, temperature=temperature, num_predict=max_tokens
            ):
                if content:
                    yield _sse_chunk(completion_id, created_ts, model, {"content": content})
                if done:
                    yield _sse_chunk(completion_id, created_ts, model, {}, finish_reason="stop")
                    break
        except requests.exceptions.RequestException as exc:
            # Surface the error as an SSE error event then terminate.
            err_payload = {"error": {"message": str(exc), "type": "ollama_error"}}
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse_chunk(
    completion_id: str,
    created_ts: int,
    model: str,
    delta: dict,
    finish_reason: Optional[str] = None,
) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    logger.info("Starting server on %s:%s using model %s", SERVER_HOST, SERVER_PORT, OLLAMA_MODEL)
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
