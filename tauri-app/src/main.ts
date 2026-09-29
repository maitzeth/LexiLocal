import "./styles.css";
import { invoke } from "@tauri-apps/api/core";

const DEFAULT_BASE_URL = "http://localhost:8000";

let baseUrl = DEFAULT_BASE_URL;
let availableModels: string[] = [];
let selectedModel = "";

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
  request_body?: string | null;
  response_body?: string | null;
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
        <div class="row">
          <label class="muted">Model:</label>
          <select id="chat-model"></select>
          <button id="btn-chat">Send</button>
        </div>
        <textarea id="chat-prompt" placeholder="Ask anything..."></textarea>
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
        <div class="row">
          <button id="btn-translate">Translate</button>
        </div>
        <div id="translate-output" class="output"></div>
      </section>
      <section class="panel">
        <h2>REST API (OpenAI-compatible)</h2>
        <p class="muted">Server: <code id="api-base">${baseUrl}</code></p>
        <p class="muted">Compatible with the OpenAI Chat Completions API. Spanify can point to <code>${baseUrl}/v1</code>.</p>
        <div class="examples">
          <div class="example">
            <div class="example-header">
              <strong>List models</strong>
              <button class="copy-btn secondary" data-copy="models">Copy</button>
            </div>
            <pre id="ex-models"></pre>
          </div>
          <div class="example">
            <div class="example-header">
              <strong>Chat completion</strong>
              <button class="copy-btn secondary" data-copy="chat">Copy</button>
            </div>
            <pre id="ex-chat"></pre>
          </div>
          <div class="example">
            <div class="example-header">
              <strong>Streaming (SSE)</strong>
              <button class="copy-btn secondary" data-copy="stream">Copy</button>
            </div>
            <pre id="ex-stream"></pre>
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
  fetchModels();
  fetchLogs();
  setInterval(fetchLogs, 2000);
}

function refreshExamples() {
  document.querySelector("#api-base")!.textContent = baseUrl;
  document.querySelector("#ex-models")!.textContent = buildCurlExample("/v1/models", "GET", "");
  document.querySelector("#ex-chat")!.textContent = buildCurlExample(
    "/v1/chat/completions",
    "POST",
    JSON.stringify({
      model: "qwen2.5:3b",
      messages: [{ role: "user", content: "Hello" }],
      stream: false,
    })
  );
  document.querySelector("#ex-stream")!.textContent = `curl -N ${baseUrl}/v1/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -d '{"model":"qwen2.5:3b","messages":[{"role":"user","content":"Hi"}],"stream":true}'`;
}

async function fetchModels() {
  try {
    const res = await fetch(`${baseUrl}/v1/models`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return;
    const data = await res.json();
    availableModels = (data.data || []).map((m: { id: string }) => m.id);
    if (availableModels.length && !availableModels.includes(selectedModel)) {
      selectedModel = availableModels[0];
    }
    const select = document.querySelector<HTMLSelectElement>("#chat-model");
    if (select) {
      select.innerHTML = availableModels
        .map((m) => `<option value="${m}" ${m === selectedModel ? "selected" : ""}>${m}</option>`)
        .join("");
    }
  } catch {
    // Server unreachable; ignore.
  }
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
    fetchModels();
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

  document.querySelector<HTMLSelectElement>("#chat-model")!.addEventListener("change", (e) => {
    selectedModel = (e.target as HTMLSelectElement).value;
  });

  document.querySelector("#btn-chat")!.addEventListener("click", () => {
    const prompt = document.querySelector<HTMLTextAreaElement>("#chat-prompt")!.value.trim();
    if (!prompt) return;
    const output = document.querySelector<HTMLDivElement>("#chat-output")!;
    output.textContent = "";
    output.innerHTML = `<div class="loading"><div class="spinner"></div>Thinking...</div>`;
    streamChatCompletion([{ role: "user", content: prompt }], output);
  });

  document.querySelector("#btn-translate")!.addEventListener("click", () => {
    const text = document.querySelector<HTMLTextAreaElement>("#translate-text")!.value.trim();
    if (!text) return;
    const source = document.querySelector<HTMLSelectElement>("#translate-source")!.value;
    const target = document.querySelector<HTMLSelectElement>("#translate-target")!.value;
    if (source === target) {
      alert("Source and target must differ.");
      return;
    }
    const output = document.querySelector<HTMLDivElement>("#translate-output")!;
    output.textContent = "";
    output.innerHTML = `<div class="loading"><div class="spinner"></div>Translating...</div>`;
    const direction = `${source.toUpperCase()} -> ${target.toUpperCase()}`;
    const system =
      "You are a professional translator. Return ONLY the translated text, with no explanations, notes, or extra formatting.";
    const user = `Translate the following text from ${direction}:\n\n${text}`;
    streamChatCompletion(
      [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
      output
    );
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

async function streamChatCompletion(messages: { role: string; content: string }[], output: HTMLDivElement) {
  const model = selectedModel || availableModels[0] || "qwen2.5:3b";
  try {
    const res = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages, stream: true }),
      signal: AbortSignal.timeout(300000),
    });
    if (!res.ok || !res.body) {
      output.textContent = `Error: HTTP ${res.status}`;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    output.textContent = "";
    let gotAnyContent = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        const lines = event.split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const payload = trimmed.slice(5).trim();
          if (payload === "[DONE]") {
            return;
          }
          try {
            const json = JSON.parse(payload);
            const delta = json.choices?.[0]?.delta;
            const content = delta?.content;
            if (content) {
              if (!gotAnyContent) {
                output.textContent = "";
                gotAnyContent = true;
              }
              output.textContent += content;
            }
          } catch {
            // ignore malformed chunks
          }
        }
      }
    }

    if (!gotAnyContent) {
      output.textContent = "(empty response)";
    }
  } catch (err) {
    output.textContent = `Error: ${err}`;
  }
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
function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string)
  );
}

async function fetchLogs() {
  try {
    const res = await fetch(`${baseUrl}/logs?limit=50`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return;
    const entries = (await res.json()) as LogEntry[];

    const output = document.querySelector<HTMLDivElement>("#log-output")!;
    const autoScroll = document.querySelector<HTMLInputElement>("#auto-scroll")!;

    for (const entry of entries) {
      const key = `${entry.timestamp}-${entry.client_ip}-${entry.method}-${entry.path}-${entry.status}-${entry.request_body ?? ""}-${entry.response_body ?? ""}`;
      if (seenLogKeys.has(key)) continue;
      seenLogKeys.add(key);

      const time = entry.timestamp.split("T")[1] || entry.timestamp;
      const statusClass = entry.status >= 500 ? "err" : entry.status >= 400 ? "warn" : "ok";

      const entry_el = document.createElement("div");
      entry_el.className = "log-entry";

      const header = document.createElement("div");
      header.className = "log-line";
      header.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-ip">${entry.client_ip}</span>
        <span class="log-method ${entry.method}">${entry.method}</span>
        <span class="log-path">${entry.path}</span>
        <span class="log-status ${statusClass}">${entry.status}</span>
      `;
      entry_el.appendChild(header);

      if (entry.request_body) {
        const req = document.createElement("div");
        req.className = "log-body log-body-req";
        req.title = entry.request_body;
        req.innerHTML = `<span class="log-body-label">REQ</span> ${escapeHtml(entry.request_body)}`;
        entry_el.appendChild(req);
      }
      if (entry.response_body) {
        const res = document.createElement("div");
        res.className = "log-body log-body-res";
        res.title = entry.response_body;
        res.innerHTML = `<span class="log-body-label">RES</span> ${escapeHtml(entry.response_body)}`;
        entry_el.appendChild(res);
      }

      output.appendChild(entry_el);
    }

    while (output.children.length > 100) {
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
