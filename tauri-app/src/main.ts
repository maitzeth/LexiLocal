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

interface LogEntry {
  timestamp: string;
  client_ip: string;
  method: string;
  path: string;
  status: number;
}

function buildCurlExample(endpoint: string, method: string, body: string): string {
  const url = `${baseUrl}${endpoint}`;
  if (method === "GET") {
    return `curl ${url}`;
  }
  return `curl -X ${method} ${url} \\\n  -H "Content-Type: application/json" \\\n  -d '${body}'`;
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
      <section class="panel">
        <h2>REST API</h2>
        <p class="muted">Current server URL: <code id="api-base">${baseUrl}</code></p>
        <p class="muted">For other machines on your LAN, replace <code>localhost</code> with this machine's local IP (e.g. <code>192.168.x.x</code>).</p>
        <div class="examples">
          <div class="example">
            <div class="example-header">
              <strong>Health check</strong>
              <button class="copy-btn secondary" data-copy="health">Copy</button>
            </div>
            <pre id="ex-health"></pre>
          </div>
          <div class="example">
            <div class="example-header">
              <strong>Ask a question</strong>
              <button class="copy-btn secondary" data-copy="chat">Copy</button>
            </div>
            <pre id="ex-chat"></pre>
          </div>
          <div class="example">
            <div class="example-header">
              <strong>Translate text</strong>
              <button class="copy-btn secondary" data-copy="translate">Copy</button>
            </div>
            <pre id="ex-translate"></pre>
          </div>
        </div>
      </section>
      <section class="panel">
        <h2>Activity Log</h2>
        <div class="log-controls">
          <button id="btn-clear-log" class="secondary">Clear</button>
          <label class="muted">
            <input type="checkbox" id="auto-scroll" checked /> Auto-scroll
          </label>
          <span id="log-count" class="muted"></span>
        </div>
        <div id="log-output" class="log-output"></div>
      </section>
    </main>
  `;

  bindEvents();
  refreshExamples();
  checkHealth();
  setInterval(checkHealth, 5000);
  fetchLogs();
  setInterval(fetchLogs, 2000);
}

function refreshExamples() {
  document.querySelector("#api-base")!.textContent = baseUrl;
  document.querySelector("#ex-health")!.textContent = buildCurlExample("/health", "GET", "");
  document.querySelector("#ex-chat")!.textContent = buildCurlExample(
    "/chat",
    "POST",
    JSON.stringify({ prompt: "What is the capital of France?" })
  );
  document.querySelector("#ex-translate")!.textContent = buildCurlExample(
    "/translate",
    "POST",
    JSON.stringify({ text: "Good morning, how are you?", source: "en", target: "es" })
  );
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function bindEvents() {
  const baseUrlInput = document.querySelector<HTMLInputElement>("#base-url")!;
  baseUrlInput.addEventListener("change", () => {
    baseUrl = baseUrlInput.value.trim() || DEFAULT_BASE_URL;
    refreshExamples();
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
        signal: AbortSignal.timeout(120000),
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
        signal: AbortSignal.timeout(120000),
      });
      const data = await res.json();
      output.textContent = data.translation || JSON.stringify(data, null, 2);
    } catch (err) {
      output.textContent = `Error: ${err}`;
    }
  });

  document.querySelectorAll<HTMLButtonElement>(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.copy!;
      const pre = document.querySelector<HTMLPreElement>(`#ex-${key}`);
      if (!pre) return;
      const ok = await copyToClipboard(pre.textContent || "");
      const original = btn.textContent;
      btn.textContent = ok ? "Copied!" : "Failed";
      setTimeout(() => (btn.textContent = original), 1500);
    });
  });

  document.querySelector("#btn-clear-log")!.addEventListener("click", () => {
    document.querySelector("#log-output")!.innerHTML = "";
    document.querySelector("#log-count")!.textContent = "";
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
    const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(10000) });
    const data = await res.json();
    updateStatus({
      running: res.ok && data.status === "ok",
      health: data,
    });
  } catch (err) {
    updateStatus({ running: false, error: String(err) });
  }
}

const seenLogKeys = new Set<string>();
async function fetchLogs() {
  try {
    const res = await fetch(`${baseUrl}/logs?limit=50`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return;
    const entries = (await res.json()) as LogEntry[];

    const output = document.querySelector<HTMLDivElement>("#log-output")!;
    const autoScroll = document.querySelector<HTMLInputElement>("#auto-scroll")!;

    // Entries are newest first; render top-down and prepend new ones at the top.
    for (const entry of entries) {
      const key = `${entry.timestamp}-${entry.client_ip}-${entry.method}-${entry.path}-${entry.status}`;
      if (seenLogKeys.has(key)) continue;
      seenLogKeys.add(key);

      const line = document.createElement("div");
      line.className = "log-line";
      const time = entry.timestamp.split("T")[1] || entry.timestamp;
      const statusClass = entry.status >= 500 ? "err" : entry.status >= 400 ? "warn" : "ok";
      line.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-ip">${entry.client_ip}</span>
        <span class="log-method ${entry.method}">${entry.method}</span>
        <span class="log-path">${entry.path}</span>
        <span class="log-status ${statusClass}">${entry.status}</span>
      `;
      output.appendChild(line);
    }

    // Trim DOM to last 200 lines for memory.
    while (output.children.length > 200) {
      output.removeChild(output.firstChild!);
    }

    document.querySelector("#log-count")!.textContent = `${entries.length} recent request(s)`;

    if (autoScroll.checked) {
      output.scrollTop = output.scrollHeight;
    }
  } catch {
    // Server unreachable; ignore silently.
  }
}

render();
