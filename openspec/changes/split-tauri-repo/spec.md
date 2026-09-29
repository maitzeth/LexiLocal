# Spec: Split the Tauri desktop app into its own repository (`Codex-Astartes`)

This spec turns the [proposal](./proposal.md) into a concrete, testable contract. It defines the file moves, the new persistent configuration, the Tauri commands, the frontend sections, and the exact acceptance checks.

## 1. Repository split

### 1.1 What moves out of `LexiLocal`

The following paths are removed from the `LexiLocal` repo:

- `tauri-app/` (entire directory, ~200 files including `node_modules` and `target` — those are gitignored anyway)
- `launch-ui.bat`
- `launch-ui.ps1`
- `toggle-server.ps1`
- `toggle-server.bat`
- `create-desktop-shortcut.ps1`

### 1.2 What stays in `LexiLocal`

- `server.py`
- `run.sh`
- `requirements.txt`
- `server.env`, `server.env.example`
- `server.log` (gitignored)
- `README.md` (rewritten — see §6)
- `openspec/` (SDD artifacts for this change and future ones)

### 1.3 What gets created in `Codex-Astartes`

The new repo at `C:\Users\andre\Documents\Projects\Codex-Astartes\` is initialized as a fresh git repo and receives the contents of `tauri-app/` at its root (the `tauri-app/` prefix is dropped). Concretely:

```
Documents/Projects/Codex-Astartes/
├── .gitignore            (Tauri/Vite/Rust-flavored)
├── README.md
├── package.json
├── package-lock.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── index.html
├── icon.svg
├── src/
│   ├── main.ts
│   ├── styles.css
│   └── tools/
│       └── clipboard.ts          (new — clipboard history view model)
├── src-tauri/
│   ├── Cargo.toml
│   ├── build.rs
│   ├── tauri.conf.json
│   ├── capabilities/
│   │   └── default.json
│   ├── icons/                    (generated from icon.svg)
│   └── src/
│       ├── main.rs               (rewritten — uses config + sidebar shell)
│       ├── config.rs             (new — Config struct + TOML load/save)
│       ├── clipboard.rs          (new — Windows clipboard polling + history)
│       └── commands.rs           (new — all #[tauri::command] entry points)
├── launch-ui.bat                 (moved from LexiLocal)
├── launch-ui.ps1                 (moved)
├── toggle-server.ps1             (moved)
├── toggle-server.bat             (moved)
└── create-desktop-shortcut.ps1   (moved)
```

### 1.4 Git remotes

- `LexiLocal`: existing remote `git@github.com:maitzeth/LexiLocal.git`. After the split, push the cleaned backend as a new commit on `master`.
- `Codex-Astartes`: new repo `git@github.com:maitzeth/Codex-Astartes.git` (to be created on GitHub by the user; the local repo is pushed after creation).

## 2. Persistent configuration (`config.toml`)

### 2.1 Location

`config.toml` lives in the **same directory as the executable**. For the NSIS-installed app, that is:

```
%LocalAppData%\Codex-Astartes\config.toml
```

(The exact directory is whatever `std::env::current_exe().parent()` returns at runtime — i.e., next to `codex-astartes.exe`, the binary produced by `tauri-build`.)

If the file does not exist on startup, the app shows the setup screen (§4) and writes the file on save.

### 2.2 Schema (TOML)

```toml
# Codex-Astartes — persistent configuration
# Edit through the UI; manual edits are also fine.

[server]
# Absolute path to the LexiLocal backend installation directory.
# Must contain run.sh. Created via "Start Server" button.
dir = "C:\\Users\\andre\\Documents\\Projects\\ollama-qwen-server"

# Base URL the frontend uses to reach the backend.
# Change to a LAN IP to talk to a remote backend.
url = "http://localhost:8000"

[ui]
# "dark" or "light".
theme = "dark"

[clipboard]
# Most-recent-first. Capped at `max_items` (10). Polled from Windows clipboard
# every `poll_ms` (750) milliseconds while the app is running.
poll_ms = 750
max_items = 10
items = [
  { timestamp = "2026-09-29T12:34:56", text = "Hello world" },
  # ...
]
```

### 2.3 Rust module (`src-tauri/src/config.rs`)

Exposes:

```rust
#[derive(Serialize, Deserialize)]
pub struct Config {
    pub server: ServerConfig,
    pub ui: UiConfig,
    pub clipboard: ClipboardConfig,
}

pub fn config_path() -> PathBuf { /* current_exe parent + "config.toml" */ }
pub fn load() -> Result<Config, ConfigError> { /* parse TOML or return default */ }
pub fn save(cfg: &Config) -> Result<(), ConfigError> { /* serialize + write atomically */ }
```

Defaults if file is missing or invalid:

- `server.dir = ""` (empty → triggers setup screen)
- `server.url = "http://localhost:8000"`
- `ui.theme = "dark"`
- `clipboard.poll_ms = 750`
- `clipboard.max_items = 10`
- `clipboard.items = []`

Writes are atomic: write to `config.toml.tmp` then rename.

## 3. Tauri commands (`src-tauri/src/commands.rs`)

All commands are `#[tauri::command]` and exposed to the frontend via `invoke()`.

### 3.1 Configuration

- `get_config() -> Config` — returns the current in-memory config.
- `set_server_dir(path: String) -> Result<Config, String>` — validates that `path/run.sh` exists, then updates `server.dir` and saves.
- `set_server_url(url: String) -> Result<Config, String>` — validates URL parses and starts with `http`, updates `server.url`, saves.
- `set_theme(theme: String) -> Result<Config, String>` — accepts `"dark"` or `"light"`, saves.

### 3.2 Backend lifecycle

- `start_server() -> Result<ServerStatus, String>` — if `config.server.dir` is empty, returns `"Backend directory not configured"`. Otherwise spawns `bash <config.server.dir>/run.sh start` in that directory, captures PID, returns status. Same retry/health-check semantics as the current implementation.
- `stop_server() -> Result<ServerStatus, String>` — kills the spawned process (if any), returns stopped status.
- `server_status() -> Result<ServerStatus, String>` — returns `running` based on whether the tracked child process is alive.

### 3.3 Clipboard

- `get_clipboard_history() -> Result<Vec<ClipboardItem>, String>` — returns current history (most recent first).
- `clear_clipboard_history() -> Result<(), String>` — empties history in memory and on disk.
- `copy_to_clipboard(text: String) -> Result<(), String>` — writes `text` to the system clipboard via `tauri-plugin-clipboard-manager`.
- `set_clipboard_poll_ms(ms: u64) -> Result<Config, String>` — updates poll interval, saves.

### 3.4 Internal

A background task (spawned in `setup()` of `main.rs`) calls `tauri-plugin-clipboard-manager` every `config.clipboard.poll_ms` ms. On change, it dedupes against the last item, prepends `{ timestamp, text }`, trims to `max_items`, saves config, and emits an event `clipboard://changed` with the new history to the frontend.

## 4. First-run setup screen

When `config.server.dir` is empty, the app renders a setup overlay (not the sidebar) instead of the main UI. The overlay contains:

- App title and a one-line description.
- A file/folder picker for the backend install directory (uses `tauri-plugin-dialog`'s `pick_folder`).
- A "Save" button that calls `set_server_dir`.
- On success, the overlay disappears and the sidebar UI renders.
- On error (path invalid, no `run.sh`), an inline error message is shown next to the Save button.

Once configured, subsequent launches skip the setup screen unless the user clears the path from Settings.

## 5. Frontend (`src/main.ts` + `src/tools/clipboard.ts`)

### 5.1 Layout: sidebar shell

```
┌─────────────┬────────────────────────────────────────────────────┐
│ Codex-Astartes│ [selected section content]                         │
│ ● Online    │                                                    │
│             │                                                    │
│ 💬 Chat     │                                                    │
│ 🌐 Translate│                                                    │
│ 🛠  Tools   │                                                    │
│ 📡 REST API │                                                    │
│ 📋 Activity │                                                    │
│             │                                                    │
│ ⚙ Settings  │                                                    │
│ ◐ Theme: ●  │                                                    │
└─────────────┴────────────────────────────────────────────────────┘
```

The sidebar is fixed width (~220 px), dark or light themed via CSS variables. Navigation uses inline SVG icons (Lucide-style, 16 px) defined in `src/icons.ts` — no emoji, no extra dependency. The status dot at the top mirrors `/health` (polled every 5 s).

### 5.2 Sections

Each section is a separate render function. Only one is mounted at a time; switching sections is instant (no re-fetch, no destroy of cached state for Chat/Translate inputs).

- **Chat** — model selector (from `/v1/models`), prompt textarea, Send button, streaming output to `/v1/chat/completions`.
- **Translate** — EN↔ES selector, textarea, Translate button, streaming output to `/v1/chat/completions` with translation system prompt.
- **Tools** — currently shows Clipboard history. New tools slot in below as new panels.
  - List of items with timestamp, first ~80 chars preview, full text on hover.
  - Buttons per item: **Copy back** (`copy_to_clipboard`), **→ Chat** (fill chat input, switch to Chat), **→ Translate** (fill translate input, switch to Translate).
  - Header buttons: **Clear** (`clear_clipboard_history`), **Pause/Resume polling**, **Set interval** (calls `set_clipboard_poll_ms`).
- **REST API** — same as today (3 copyable curl examples: `/v1/models`, `/v1/chat/completions`, SSE).
- **Activity Log** — same as today (polls `/logs` every 2 s, shows time / IP / method / path / status / REQ / RES).
- **Settings** — backend directory picker (writes to config), backend URL field, theme selector, "Reveal config file" button (opens the folder in Explorer), "Open logs folder" button.

### 5.3 Theming

CSS variables define the palette. Two themes:

- **Dark** (default, current look): bg `#0f172a`, panel `#1e293b`, text `#f8fafc`, accent `#38bdf8`.
- **Light**: bg `#f8fafc`, panel `#ffffff`, text `#0f172a`, accent `#0284c7`, borders `#cbd5e1`.

The toggle in the sidebar flips `<html data-theme="dark|light">`, which selects the variable set. Persisted in config on change.

## 6. README updates

### 6.1 `LexiLocal/README.md`

- Remove the "Native Windows UI" section (it lives in the other repo now).
- Remove the `tauri-app/` mention from Project Structure.
- Add a "Desktop UI" section near the top:

  > A native Windows desktop UI for this backend lives in a separate repository:
  > **[Codex-Astartes](https://github.com/maitzeth/Codex-Astartes)**. Build it with `npm run tauri:build` or download the installer from its releases.

- Remove the now-obsolete `create-desktop-shortcut.ps1`, `toggle-server.ps1`, `launch-ui.bat` mentions.

### 6.2 `Codex-Astartes/README.md` (new)

Covers:

- What it is (the desktop UI for LexiLocal).
- Prerequisites (Rust, Node, Ollama, a working LexiLocal backend).
- Install (clone, `npm install`, `npm run tauri:build`).
- First-run setup (point at backend dir).
- Usage walkthrough of each sidebar section.
- Configuration (`config.toml` reference).
- Clipboard history notes & privacy.
- Building the NSIS installer.
- Troubleshooting (bash not found, backend unreachable, config invalid).

## 7. Tauri dependencies

`src-tauri/Cargo.toml` adds:

- `tauri-plugin-clipboard-manager = "2"`
- `tauri-plugin-dialog = "2"`
- `serde = { version = "1", features = ["derive"] }` (already present)
- `toml = "0.8"`
- `tokio = { version = "1", features = ["fs", "sync", "rt", "macros", "time"] }` (broaden existing features)

`tauri-app/package.json` adds:

- `@tauri-apps/plugin-clipboard-manager = "^2"`
- `@tauri-apps/plugin-dialog = "^2"`

`tauri.conf.json`:

- `bundle.productName` becomes `"Codex-Astartes"` (was `"LexiLocal UI"`).
- `bundle.identifier` becomes `"com.codex-astartes.app"`.
- Capabilities updated to include `clipboard-manager:default` and `dialog:default`.

## 8. Capabilities and permissions

`src-tauri/capabilities/default.json` adds:

```json
{
  "permissions": [
    "core:default",
    "clipboard-manager:allow-read-text",
    "clipboard-manager:allow-write-text",
    "dialog:allow-open"
  ]
}
```

## 9. Acceptance criteria (mapped to the proposal's 10)

| # | Criterion | How verified |
|---|---|---|
| 1 | `LexiLocal` repo contains no `tauri-app/` | `find LexiLocal -name tauri-app -type d` returns nothing after the change. |
| 2 | `Codex-Astartes` builds and produces a working `.exe` | `npm run tauri:build` completes; running the produced installer creates the Start Menu + Desktop shortcuts. |
| 3 | First-launch setup screen | Delete `config.toml`; launch the app. Setup overlay appears; pick a valid backend dir; the main UI renders. |
| 4 | Start/Stop buttons work | With config set, click **Start Server**: the Python server logs `Server running with PID …`. Click **Stop Server**: PID is gone. |
| 5 | Base URL persists | Change URL in Settings; restart app; the new URL is shown in the sidebar status and is used by all sections. |
| 6 | Tools tab + clipboard history | Copy 5 different things to the Windows clipboard; the Tools tab shows 5 entries with timestamps, most recent first. |
| 7 | Clipboard actions | **Copy back** puts the item on the system clipboard. **→ Chat** fills the Chat textarea and switches tabs. **→ Translate** does the same for Translate. |
| 8 | `LexiLocal/README.md` links to the desktop repo | `grep "Codex-Astartes" LexiLocal/README.md` finds the link. |
| 9 | No backend code changes | `diff` of `server.py`, `run.sh`, `requirements.txt` vs. `master@{1}` shows no changes. All curl examples still work. |
| 10 | Both repos pushed | `git -C LexiLocal log` shows the split commit; `git -C Codex-Astartes log` shows the initial commit. Both have a `master` branch tracking `origin/master`. |

## 10. Out of scope (explicit non-goals, restated)

- No changes to `server.py`, `run.sh`, the OpenAI-compatible API, the activity log middleware, CORS, or model handling.
- No bundled Python in the `.exe`. The backend stays a separate install.
- No tray icon (setup is a window, not a tray menu).
- No auto-update mechanism.
- No multi-machine backend discovery (the user enters the URL manually; LAN access still requires the firewall rule from the existing README).
- No image/file clipboard support (text only, 32 KB max per item).
- No clipboard encryption at rest (TOML is plain text on disk).
- No mobile / Linux / macOS targets. Windows-only in this change.
