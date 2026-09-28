"""
Lightweight REST server backed by a local Ollama instance.
Default model: qwen2.5:3b (good for EN<->ES translation and general Q&A).
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


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
