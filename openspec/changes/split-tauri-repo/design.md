# Design: Split the Tauri desktop app into its own repository (`Codex-Astartes`)

This document turns the [spec](./spec.md) into architectural decisions: how the shell mounts, how state flows, how the Rust and TypeScript sides communicate, and how files are organized. It is the blueprint the `apply` phase will follow.

## 1. Frontend architecture: vanilla TS shell with section controllers

No framework (no React, Vue, Svelte). Vanilla TS keeps the bundle small, the build fast, and the mental model flat. The cost is that we have to roll our own mini-router and controller lifecycle, which is fine for ~6 sections.

### 1.1 Shell (`src/main.ts`)

The shell owns:

- The sidebar DOM (static, mounted once).
- The `#content` mount point.
- The current `sectionId`.
- The `Config` object (loaded once via `get_config`).
- Theme application.

`renderShell()`:

```ts
// Pseudocode
async function renderShell() {
  const config = await tauri.getConfig();
  applyTheme(config.ui.theme);
  if (config.server.dir.trim() === "") {
    mountSetupScreen();
    return;
  }
  mountSidebar();
  activate("chat");  // default section
}
```

### 1.2 Section interface

Every section is an object:

```ts
// src/sections/types.ts
export interface SectionContext {
  config: Config;
  setConfig: (cfg: Config) => Promise<void>;
  switchTo: (id: SectionId) => void;
}

export interface SectionController {
  destroy(): void;          // remove event listeners, abort in-flight requests
}

export interface Section {
  id: SectionId;
  label: string;
  icon: string;              // raw SVG path "d" attribute (Lucide-style, 24x24)
  render(ctx: SectionContext): HTMLElement;  // initial render; returns the root element
}
```

When `activate(id)` is called:

1. If there's an active controller, call `controller.destroy()`.
2. Get the section by id.
3. Call `section.render(ctx)` and append the result to `#content`.
4. Store the returned controller.

This means streaming Chat output survives section switches (the controller is torn down, the in-flight fetch is aborted). History of past outputs is lost on switch — acceptable for v1; a future "section state caching" feature can store rendered HTML.

### 1.3 State management

Module-level `appState`:

```ts
let appConfig: Config = defaultConfig();
let activeSection: SectionId = "chat";
let activeController: SectionController | null = null;

function setConfig(next: Config) {
  appConfig = next;
  applyTheme(next.ui.theme);
  // Sections re-read ctx.config on their next render. If they're already
  // mounted and need to react (e.g. URL changed), they subscribe via
  // subscribeConfigChange.
}
const configSubscribers = new Set<(cfg: Config) => void>();
function subscribeConfigChange(fn: (cfg: Config) => void): () => void { ... }
```

Why a subscriber set instead of re-rendering? Because re-rendering Chat mid-stream would kill the streaming output. Sections register a subscriber to update only what changed (e.g. status dot, base URL display).

## 2. Tauri ↔ TypeScript boundary (`src/lib/tauri.ts`)

All `invoke()` calls go through typed wrappers. No raw `invoke()` in section code.

```ts
// src/lib/tauri.ts
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export const tauri = {
  // Config
  getConfig: () => invoke<Config>("get_config"),
  setServerDir: (path: string) => invoke<Config>("set_server_dir", { path }),
  setServerUrl: (url: string) => invoke<Config>("set_server_url", { url }),
  setTheme: (theme: "dark" | "light") => invoke<Config>("set_theme", { theme }),

  // Server lifecycle
  startServer: () => invoke<ServerStatus>("start_server"),
  stopServer: () => invoke<ServerStatus>("stop_server"),
  serverStatus: () => invoke<ServerStatus>("server_status"),

  // Clipboard
  getClipboardHistory: () => invoke<ClipboardItem[]>("get_clipboard_history"),
  clearClipboardHistory: () => invoke<void>("clear_clipboard_history"),
  copyToClipboard: (text: string) => invoke<void>("copy_to_clipboard", { text }),
  setClipboardPollMs: (ms: number) => invoke<Config>("set_clipboard_poll_ms", { ms }),

  // Events
  onClipboardChanged: (fn: (items: ClipboardItem[]) => void): Promise<UnlistenFn> =>
    listen<ClipboardItem[]>("clipboard://changed", (e) => fn(e.payload)),
};
```

Sections depend on `tauri.*`, never on raw `@tauri-apps/api/core`. This makes mocking trivial for tests later.

## 3. Rust architecture (`src-tauri/src/`)

### 3.1 Module layout

```
src-tauri/src/
├── main.rs        # tauri::Builder, setup, command registration
├── config.rs      # Config struct, load, save, defaults, atomic writes
├── commands.rs    # all #[tauri::command] entry points
├── clipboard.rs   # background polling task + history helpers
└── server.rs      # backend process spawning + lifecycle
```

`main.rs` stays thin — it just wires modules together.

### 3.2 State management in Rust

Two long-lived pieces of state:

```rust
struct AppState {
    config: Mutex<Config>,          // always in sync with disk
    child: Mutex<Option<Child>>,     // spawned bash run.sh process
}
```

Stored in `app.manage(AppState { ... })` so commands can grab it via `tauri::State<AppState>`.

### 3.3 Config module (`config.rs`)

```rust
use serde::{Deserialize, Serialize};
use std::{fs, path::{Path, PathBuf}};
use toml;

#[derive(Serialize, Deserialize, Clone)]
pub struct Config {
    pub server: ServerConfig,
    pub ui: UiConfig,
    pub clipboard: ClipboardConfig,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct ServerConfig { pub dir: String, pub url: String }
#[derive(Serialize, Deserialize, Clone)]
pub struct UiConfig { pub theme: String }
#[derive(Serialize, Deserialize, Clone)]
pub struct ClipboardConfig {
    pub poll_ms: u64,
    pub max_items: usize,
    pub items: Vec<ClipboardItem>,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct ClipboardItem { pub timestamp: String, pub text: String }

pub fn config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
        .join("config.toml")
}

pub fn default_config() -> Config { /* see spec §2.3 */ }

pub fn load() -> Config {
    let path = config_path();
    match fs::read_to_string(&path) {
        Ok(s) => toml::from_str(&s).unwrap_or_else(|_| {
            let d = default_config();
            save(&d).ok();
            d
        }),
        Err(_) => default_config(),
    }
}

pub fn save(cfg: &Config) -> Result<(), String> {
    let path = config_path();
    let tmp = path.with_extension("toml.tmp");
    let body = toml::to_string_pretty(cfg).map_err(|e| e.to_string())?;
    fs::write(&tmp, body).map_err(|e| e.to_string())?;
    fs::rename(&tmp, &path).map_err(|e| e.to_string())?;  // atomic on same volume
    Ok(())
}
```

If the TOML is corrupted (parse error), we fall back to defaults and overwrite the file. The user loses their config but the app survives. A future improvement: keep the broken file as `config.toml.broken-<timestamp>`.

### 3.4 Backend lifecycle (`server.rs`)

Mirror of the current `main.rs::start_server`/`stop_server`, but with two changes:

1. `possible_server_dirs()` is gone. The path comes from `config.server.dir`. If empty, `start_server` returns an error.
2. `bash` is invoked with the absolute path to `run.sh`: `bash <config.server.dir>/run.sh start`.

```rust
pub async fn start(state: &AppState) -> Result<ServerStatus, String> {
    let cfg = state.config.lock().await.clone();
    if cfg.server.dir.trim().is_empty() {
        return Err("Backend directory not configured. Open Settings.".into());
    }
    let dir = PathBuf::from(&cfg.server.dir);
    if !dir.join("run.sh").exists() {
        return Err(format!("run.sh not found in {}", dir.display()));
    }
    // spawn bash run.sh start, capture child, save in state, health-check after 2.5s
}

pub async fn stop(state: &AppState) -> Result<ServerStatus, String> { /* kill child */ }
pub async fn status(state: &AppState) -> Result<ServerStatus, String> { /* report */ }
```

### 3.5 Clipboard module (`clipboard.rs`)

```rust
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_clipboard_manager::ClipboardExt;
use std::time::Duration;
use tokio::time::interval;

pub fn spawn_poller(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let mut tick = interval(Duration::from_millis(750));
        let mut last_text: Option<String> = None;
        loop {
            tick.tick().await;
            let state = app.state::<AppState>();
            let mut cfg = state.config.lock().await;
            // If user changed poll_ms, the interval will catch up at next tick.
            // For instant effect on change, we'd need to rebuild tick — out of scope.

            let text = match app.clipboard().read_text() {
                Ok(s) => s,
                Err(_) => continue,
            };
            if text.len() > 32 * 1024 { continue; }  // drop huge pastes
            if Some(&text) == last_text.as_ref() { continue; }
            last_text = Some(text.clone());

            cfg.clipboard.items.insert(0, ClipboardItem {
                timestamp: chrono::Local::now().to_rfc3339(),
                text,
            });
            cfg.clipboard.items.truncate(cfg.clipboard.max_items);
            let snapshot = cfg.clipboard.items.clone();
            // save (best-effort)
            let _ = save(&cfg);
            drop(cfg);
            let _ = app.emit("clipboard://changed", &snapshot);
        }
    });
}
```

Notes:

- Uses `chrono` for timestamps. Add `chrono = { version = "0.4", features = ["clock"] }` to `Cargo.toml`.
- The poll interval is read from config each tick, so changing it via `set_clipboard_poll_ms` takes effect within ~1 s.
- Emit uses `Emitter` trait from `tauri::Emitter`.

### 3.6 Commands (`commands.rs`)

Each command is a thin wrapper that mutates `AppState` and calls `save`:

```rust
#[tauri::command]
pub async fn set_theme(theme: String, state: tauri::State<'_, AppState>) -> Result<Config, String> {
    if !["dark", "light"].contains(&theme.as_str()) { return Err("invalid theme".into()); }
    let mut cfg = state.config.lock().await;
    cfg.ui.theme = theme;
    save(&cfg)?;
    Ok(cfg.clone())
}
```

Similar shape for the other commands. All return the updated `Config` so the frontend can re-render in one round-trip.

## 4. File layout (concrete, ready to create)

```
Documents/Projects/Codex-Astartes/
├── .gitignore
├── README.md
├── package.json
├── package-lock.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── index.html
├── icon.svg
├── launch-ui.bat                 # moved
├── launch-ui.ps1                 # moved
├── toggle-server.ps1             # moved
├── toggle-server.bat             # moved
├── create-desktop-shortcut.ps1   # moved
├── src/
│   ├── main.ts                   # shell + routing
│   ├── styles.css                # themes, layout, panels
│   ├── icons.ts                  # inline SVG paths
│   ├── lib/
│   │   ├── tauri.ts              # typed wrappers around invoke()
│   │   └── theme.ts              # applyTheme(theme) → sets data-theme
│   ├── sections/
│   │   ├── types.ts              # Section, SectionController, SectionContext
│   │   ├── chat.ts               # Chat section
│   │   ├── translate.ts          # Translate section
│   │   ├── tools.ts              # Tools section (currently clipboard)
│   │   ├── rest.ts               # REST API examples section
│   │   ├── activity.ts           # Activity Log section
│   │   └── settings.ts           # Settings section
│   └── tools/
│       └── clipboard.ts          # view-model + render for clipboard list
├── src-tauri/
│   ├── Cargo.toml                # add toml, chrono, plugins
│   ├── build.rs
│   ├── tauri.conf.json           # productName, identifier updated
│   ├── capabilities/
│   │   └── default.json          # clipboard + dialog permissions
│   ├── icons/                    # generated from icon.svg
│   └── src/
│       ├── main.rs               # wires modules + spawns clipboard poller
│       ├── config.rs             # Config struct, load, save
│       ├── commands.rs           # all #[tauri::command]
│       ├── server.rs             # backend lifecycle
│       └── clipboard.rs          # background polling
```

Total new TS files: ~14. Total new Rust files: 4 (replacing the existing 1 monolith in `main.rs`).

## 5. Icons (`src/icons.ts`)

Lucide-style 24×24 SVGs, inlined as functions returning a `<svg>` element. Each icon takes optional `class` and `size` props.

```ts
// Example — chat icon (Lucide "message-circle")
export const chatIcon = ({ size = 16, class: cls = "" } = {}) => `
  <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}"
       viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="${cls}">
    <path d="M7.9 20A9 9 0 1 1 4 16.1L2 22Z"/>
  </svg>
`;
```

Icons needed:

- `chatIcon` (message-circle)
- `translateIcon` (languages)
- `toolsIcon` (wrench)
- `restIcon` (radio)
- `activityIcon` (list)
- `settingsIcon` (settings/gear)
- `themeIcon` (sun or moon, dynamic)
- `checkIcon`, `xIcon`, `copyIcon` (used in copy buttons, clear, etc.)

Total: ~10 icons. All MIT-licensed Lucide paths. Defined in one file as tagged-template-string functions.

## 6. CSS architecture (`src/styles.css`)

CSS variables on `:root[data-theme="..."]`. Two complete variable sets. Components reference variables only, never literal colors.

```css
:root[data-theme="dark"] {
  --bg: #0f172a;
  --panel: #1e293b;
  --text: #f8fafc;
  --muted: #94a3b8;
  --accent: #38bdf8;
  --accent-dim: #0ea5e9;
  --danger: #f87171;
  --success: #4ade80;
  --border: #334155;
  --log-method-GET: #4ade80;
  --log-method-POST: #38bdf8;
  --log-method-OPTIONS: #94a3b8;
}

:root[data-theme="light"] {
  --bg: #f8fafc;
  --panel: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --accent: #0284c7;
  --accent-dim: #0369a1;
  --danger: #dc2626;
  --success: #16a34a;
  --border: #cbd5e1;
  /* log colors stay similar but darker hues for contrast on light bg */
  --log-method-GET: #15803d;
  --log-method-POST: #0369a1;
  --log-method-OPTIONS: #64748b;
}
```

Sections style themselves with these variables. Switching themes is instant (no JS re-render needed beyond `document.documentElement.dataset.theme = 'light'`).

## 7. Event flow: clipboard update

```
[Windows clipboard changes]
   ↓ (every poll_ms)
[clipboard.rs poller reads text]
   ↓ dedupe + push + trim
[AppState.config updated, save() to disk]
   ↓
[app.emit("clipboard://changed", items)]
   ↓
[tauri.onClipboardChanged listener in Tools section]
   ↓
[render the new list — append-only DOM diff, no full re-render]
```

The Tools section, when active, listens and updates. When inactive, events are dropped (the next time the user activates Tools, `render()` calls `getClipboardHistory()` to fetch the current state).

## 8. Build & distribution

- Dev: `npm run tauri:dev` — Vite serves on `localhost:1420`, Tauri opens a window pointing at it. Hot reload works for TS changes; Rust changes trigger rebuild + restart.
- Build: `npm run tauri:build` — produces `Codex-Astartes.exe` (portable) and `Codex-Astartes_<ver>_x64-setup.exe` (NSIS).
- Installer behavior: same as today — Start Menu + Desktop shortcuts named **Codex-Astartes**.

## 9. Risks and how we mitigate them

| Risk | Mitigation |
|---|---|
| TOML parse error wipes user config | Fall back to defaults and overwrite; ideally preserve broken file as `config.toml.broken-<ts>` (deferred to v2). |
| `bash` missing on user's PATH | Start/Stop buttons disabled with tooltip "Install Git Bash"; Chat/Translate still work if backend is reachable. |
| Backend path contains spaces or non-ASCII | PathBuf handles it; `run.sh` is invoked via absolute path so shell parsing is safe. |
| Clipboard poll race with user copying huge text | 32 KB cap drops the item; UI shows a "skipped oversized paste" toast. |
| Long-running clipboard history corrupts `config.toml` | Atomic writes (`tmp` + rename). |
| Sidebar re-renders during streaming Chat | It doesn't — only `#content` is replaced; sidebar is mounted once. |
| `tauri-plugin-clipboard-manager` requires extra capability | Added in §3 of spec; capabilities updated in §8. |

## 10. Implementation order (what `apply` will do)

Following the spec's acceptance criteria in dependency order:

1. Create `Codex-Astartes` repo, move Tauri source. Verify `npm run tauri:build` produces a working `.exe` (AC #2).
2. Strip `tauri-app/` and launcher scripts from `LexiLocal`. Update `LexiLocal/README.md` (AC #1, #8).
3. Add `config.rs`, refactor `main.rs` to use it. Add `set_server_dir`, `set_server_url`, `set_theme`, `get_config` commands (AC #3, #5).
4. Refactor `server.rs` to use `config.server.dir` instead of heuristic (AC #4).
5. Build sidebar shell, port existing panels to section modules (Chat, Translate, REST API, Activity Log, Settings).
6. Add `clipboard.rs` poller, `tools/` view, Tools section (AC #6, #7).
7. Add light theme + toggle (AC #4 from open questions).
8. End-to-end test against the 10 acceptance criteria.

The review budget is 400 lines per PR. The split itself will likely be one PR per repo (creation + clean). The feature implementation (steps 3–7) is estimated ~1500–2000 lines of new code, which exceeds the budget — so we will need to split into chained PRs (the SDD apply phase will forecast this).

## 11. Out of scope (restated)

- Tray icon, auto-update, code signing.
- Image/file clipboard.
- Encrypted clipboard history.
- Mobile / Linux / macOS.
- Server-side changes (none).
- Bundled Python in the `.exe`.
