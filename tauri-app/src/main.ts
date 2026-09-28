import "./styles.css";
import { invoke } from "@tauri-apps/api/core";

const DEFAULT_BASE_URL = "http://localhost:8000";

let baseUrl = DEFAULT_BASE_URL;

interface ServerStatus {
  running: boolean;
  pid?: number;
  health?: { status: string; ollama_host: string; model: string };
  error?: string;
}

function render() {
  document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
    <header>
      <h1>Ollama Qwen2.5 Server</h1>
      <div class="status">
        <span id="status-dot" class="status-dot"></span>
        <span id="status-text">Checking...</span>
        <span id="model-info" class="muted"></span>
      </div>
      <div class="server-controls">
        <button id="btn-start" class="secondary">Start Server</button>
        <button id="btn-stop" class="secondary">Stop Server</button>
        <input id="base-url" type="text" value="${baseUrl}" placeholder="http://localhost:8000" />
        <button id="btn-check" class="secondary">Check</button>
      </div>
    </header>
    <main>
      <section class="panel">
        <h2>Chat</h2>
        <textarea id="chat-prompt" placeholder="Ask anything..."></textarea>
        <button id="btn-chat">Send</button>
        <div id="chat-output" class="output"></div>
      </section>
      <section class="panel">
        <h2>Translate</h2>
        <textarea id="translate-text" placeholder="Text to translate..."></textarea>
        <div class="row">
          <select id="translate-source">
            <option value="en">English</option>
            <option value="es">Español</option>
          </select>
          <span>→</span>
          <select id="translate-target">
            <option value="es">Español</option>
            <option value="en">English</option>
          </select>
        </div>
        <button id="btn-translate">Translate</button>
        <div id="translate-output" class="output"></div>
      </section>
    </main>
  `;

  bindEvents();
  checkHealth();
  setInterval(checkHealth, 5000);
}

function bindEvents() {
  const baseUrlInput = document.querySelector<HTMLInputElement>("#base-url")!;
  baseUrlInput.addEventListener("change", () => {
    baseUrl = baseUrlInput.value.trim() || DEFAULT_BASE_URL;
    checkHealth();
  });

  document.querySelector("#btn-check")!.addEventListener("click", checkHealth);

  document.querySelector("#btn-start")!.addEventListener("click", async () => {
    const text = document.querySelector<HTMLSpanElement>("#status-text")!;
    text.textContent = "Starting server...";
    try {
      const status = await invoke<ServerStatus>("start_server");
      updateStatus(status);
    } catch (err) {
      text.textContent = `Error: ${err}`;
    }
  });

  document.querySelector("#btn-stop")!.addEventListener("click", async () => {
    const text = document.querySelector<HTMLSpanElement>("#status-text")!;
    text.textContent = "Stopping server...";
    try {
      const status = await invoke<ServerStatus>("stop_server");
      updateStatus(status);
    } catch (err) {
      text.textContent = `Error: ${err}`;
    }
  });

  document.querySelector("#btn-chat")!.addEventListener("click", async () => {
    const prompt = document.querySelector<HTMLTextAreaElement>("#chat-prompt")!.value.trim();
    if (!prompt) return;
    const output = document.querySelector<HTMLDivElement>("#chat-output")!;
    output.innerHTML = `<div class="loading"><div class="spinner"></div>Thinking...</div>`;
    try {
      const res = await fetch(`${baseUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      output.textContent = data.answer || JSON.stringify(data, null, 2);
    } catch (err) {
      output.textContent = `Error: ${err}`;
    }
  });

  document.querySelector("#btn-translate")!.addEventListener("click", async () => {
    const text = document.querySelector<HTMLTextAreaElement>("#translate-text")!.value.trim();
    if (!text) return;
    const source = document.querySelector<HTMLSelectElement>("#translate-source")!.value;
    const target = document.querySelector<HTMLSelectElement>("#translate-target")!.value;
    const output = document.querySelector<HTMLDivElement>("#translate-output")!;
    output.innerHTML = `<div class="loading"><div class="spinner"></div>Translating...</div>`;
    try {
      const res = await fetch(`${baseUrl}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source, target }),
      });
      const data = await res.json();
      output.textContent = data.translation || JSON.stringify(data, null, 2);
    } catch (err) {
      output.textContent = `Error: ${err}`;
    }
  });
}

function updateStatus(status: ServerStatus) {
  const dot = document.querySelector<HTMLSpanElement>("#status-dot")!;
  const text = document.querySelector<HTMLSpanElement>("#status-text")!;
  const modelInfo = document.querySelector<HTMLSpanElement>("#model-info")!;

  dot.classList.toggle("online", status.running);
  text.textContent = status.running
    ? `Online${status.health?.model ? ` • ${status.health.model}` : ""}`
    : "Offline";
  modelInfo.textContent = status.error
    ? status.error
    : status.health
      ? `${status.health.model} @ ${status.health.ollama_host}`
      : "";
}

async function checkHealth() {
  try {
    const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();
    updateStatus({
      running: res.ok && data.status === "ok",
      health: data,
    });
  } catch (err) {
    updateStatus({ running: false, error: String(err) });
  }
}

render();
