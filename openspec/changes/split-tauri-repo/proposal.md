# Proposal: Split the Tauri desktop app into its own repository (`Codex-Astartes`)

## Context

`LexiLocal` started as a small FastAPI server with a bash control script. A Tauri v2 desktop UI was then added inside the same repository under `tauri-app/`. Today both live together:

```
ollama-qwen-server/
├── server.py
├── run.sh
├── requirements.txt
├── server.env
├── README.md
├── toggle-server.ps1
├── launch-ui.bat
├── …
└── tauri-app/          ← full Tauri v2 app (Rust + Vite + TS)
```

This worked while the UI was a thin client of the backend. It no longer fits because:

1. **The desktop app is becoming its own product.** It will grow personal-use features unrelated to the server (clipboard history, keyboard shortcuts, tray icon, etc.). Mixing those with backend code confuses contribution, releases, and versioning.
2. **Release cadences diverge.** The backend ships when the API changes; the desktop app ships when the UI/UX changes. A monorepo forces synchronized commits.
3. **The desktop app is portable.** Other people might use `Codex-Astartes` against a different backend (Groq, OpenRouter, OpenAI). Coupling it to the Python repo makes that awkward.
4. **The user wants to extend the desktop app for personal use** (e.g., a Windows clipboard history tool inside a new `Tools` tab). That work should not pollute the backend repo's history.

## Goal

Extract the Tauri desktop app into a separate repository (`Codex-Astartes`) so it can be developed, versioned, and distributed independently from the backend. The two repos communicate over the OpenAI-compatible REST API the backend already exposes.

After this change:

- **`LexiLocal`** repo = backend only (FastAPI server, run.sh, OpenAPI-compatible endpoints, server.env, README). Cleanly installable via `./run.sh start`.
- **`Codex-Astartes`** repo = the Tauri v2 desktop app, located at `Documents/Projects/Codex-Astartes`. Buildable to a Windows `.exe`/NSIS installer. Can start/stop the backend locally and connect to it via REST.

## Non-goals (this change)

- No change to the backend's API surface, behavior, or model handling. `LexiLocal`'s REST API stays exactly as it is.
- No bundling the backend into the desktop `.exe` (no PyInstaller embed, no embedded Python). The two pieces are installed separately and the desktop app finds the backend through configuration.
- No new backend features (no new endpoints, no auth, no rate limiting). Backend stays a thin proxy + log + CORS layer.
- No migration of the clipboard feature into the backend. Clipboard is purely a desktop-app concern.
- No auto-update mechanism in this change. The desktop app installs via the existing NSIS installer.

## Users and situations

**Primary user:** the repo owner (you), running Windows 11 with Ollama installed.

**Typical flow:**

1. User installs the backend once (`git clone LexiLocal && ./run.sh pull && ./run.sh start`).
2. User installs the desktop app once (`git clone Codex-Astartes && npm run tauri:build`, then runs the produced `.exe`/installer).
3. User configures the desktop app with the **path to the backend installation directory** (e.g., `C:\Users\andre\Documents\Projects\ollama-qwen-server`). Stored persistently.
4. On launch, the desktop app shows server status (Online/Offline). Buttons let the user Start/Stop the server.
5. The desktop app's base URL is editable (default `http://localhost:8000`), so it can also target a backend on another machine on the LAN — but that requires the backend firewall to be open on that other machine (out of scope here).

## Current state (what's coupled and how)

In `tauri-app/src-tauri/src/main.rs`, the Rust backend currently has this logic to find the backend project:

```rust
fn possible_server_dirs() -> Vec<PathBuf> {
    // 1. env var OLLAMA_QWEN_SERVER_DIR
    // 2. hardcoded C:/Users/andre/Documents/Projects/ollama-qwen-server
    // 3. relative paths from exe (../../../../ollama-qwen-server, etc.)
    // 4. cwd-relative
}
```

This logic assumes the desktop `.exe` lives inside or near the backend's source tree. Once the repos are split, those relative paths no longer resolve. The desktop app needs a **persistent configuration** for the backend install path.

## Proposed solution

### Repo layout

```
Documents/Projects/
├── ollama-qwen-server/        ← LexiLocal repo (backend)
│   ├── server.py
│   ├── run.sh
│   ├── requirements.txt
│   ├── server.env
│   ├── README.md
│   └── … (no tauri-app/)
└── Codex-Astartes/          ← Codex-Astartes repo (new)
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    ├── src/
    │   ├── main.ts
    │   ├── styles.css
    │   └── tools/             ← new module for Tools tab (clipboard, etc.)
    ├── src-tauri/
    │   ├── Cargo.toml
    │   ├── tauri.conf.json
    │   ├── capabilities/
    │   └── src/
    │       ├── main.rs
    │       ├── config.rs      ← new: persistent config (path to backend)
    │       └── clipboard.rs   ← new: Windows clipboard polling + history
    └── README.md
```

### Backend repo (`LexiLocal`) changes

1. **Delete `tauri-app/`** from the repo.
2. **Move the toggle scripts and launcher scripts** that are desktop-app-oriented:
   - `launch-ui.bat`, `launch-ui.ps1` → move to `Codex-Astartes`.
   - `toggle-server.ps1`, `toggle-server.bat` → move to `Codex-Astartes` (still useful for users who want a CLI toggle without opening the GUI).
   - `create-desktop-shortcut.ps1` → move to `Codex-Astartes`.
3. **Update `README.md`**:
   - Remove the "Native Windows UI" section (it lives in the other repo now).
   - Add a short "Desktop UI" section that links to `Codex-Astartes` with a one-liner install.
   - Update the project structure listing.

### Desktop repo (`Codex-Astartes`) initial contents

The Tauri app source moves verbatim from `LexiLocal/tauri-app/` into the new repo's root. Then these changes:

#### Configuration (replaces the path-finding heuristic in `main.rs`)

- Add `src-tauri/src/config.rs` with a `Config` struct:
  ```rust
  struct Config {
      backend_dir: PathBuf,        // absolute path to LexiLocal install dir
      backend_url: String,         // default "http://localhost:8000"
      theme: String,               // future-proof; default "dark"
  }
  ```
- Persist config in `%APPDATA%\Codex-Astartes\config.json` (Windows) using `tauri-plugin-store` or plain JSON I/O.
- Add Rust commands `get_config`, `set_config` exposed to the frontend.
- First-run flow: if no config exists, show a setup screen asking for the backend install directory. Save it.

#### Backend discovery & lifecycle

- `start_server` and `stop_server` Rust commands keep their behavior, but instead of `possible_server_dirs()`, they read `config.backend_dir` and run `bash <backend_dir>/run.sh start|stop` from that directory.
- If `bash` is missing on PATH, return a clear error: "Git Bash is required. Install from https://git-scm.com/."
- The backend URL defaults to `config.backend_url`. The frontend can change it via a Settings panel and save back through `set_config`.

#### New "Tools" tab — clipboard history (first feature)

- Add a fifth tab/section in the UI: **Tools**.
- First tool: **Clipboard history** showing the last 10 text items copied to the Windows clipboard while the desktop app is running.
- Implementation:
  - Add `tauri-plugin-clipboard-manager` to `Cargo.toml` and `package.json`.
  - Rust polls the system clipboard every ~750 ms via `tauri-plugin-clipboard-manager`, deduplicates by content hash, stores up to 10 items (timestamp + text).
  - Expose `get_clipboard_history`, `clear_clipboard_history`, and `copy_to_clipboard` Rust commands.
  - Frontend renders a list with timestamp, preview (first 80 chars), and "Copy back" + "Send to Chat" + "Send to Translate" actions.
  - "Send to Chat/Translate" pushes the item into the corresponding tab's input and switches tabs.

#### UI layout (4 → 5 panels becomes 2x3 or tabbed)

The current UI is a 2×2 grid (Chat | Translate | REST API | Activity Log). Adding Tools makes it 5 panels. Options:

- **(a)** 2×3 grid with one cell empty. Quick but ugly.
- **(b)** Tabbed top bar (Chat / Translate / Tools) + bottom row (REST API / Activity Log). Clean.
- **(c)** Sidebar navigation. Most extensible for future Tools additions.

**Recommend (b)** — tabs for the user-facing tools, bottom row for diagnostics. Easy to extend with more Tools later.

### Distribution

- **Backend:** unchanged. `./run.sh start` to run; `./run.sh install` is not in scope.
- **Desktop:** `npm run tauri:build` produces `Codex-Astartes.exe` and `Codex-Astartes_<version>_x64-setup.exe` (NSIS). The installer creates Start Menu + Desktop shortcuts, same as today.

## Business rules

1. The desktop app must not assume the backend lives in any specific absolute path. All paths come from user config.
2. The desktop app must work when the backend is on a different machine (LAN) — base URL is configurable, backend lifecycle commands become disabled with a hint ("Backend is on another machine; lifecycle is managed there").
3. The clipboard history is **session-only** by default (lost when app closes). Persistence is a future option, not in this change.
4. The clipboard history stores **text only**. Images, files, and non-text formats are ignored. Maximum text size per entry: 32 KB. Items larger than that are dropped (with a notice in the dev console).
5. Passwords and other secrets are not auto-detected/redacted in this change. The user is responsible for what they copy. (A future feature.)
6. The desktop app stores its config in `%APPDATA%\Codex-Astartes\` (Windows-standard per-user app data). No data leaves the machine.

## Implications

- **Breaking change for existing users of the current `.exe`.** Anyone who installed via the NSIS installer will need to reinstall from `Codex-Astartes`. Mitigation: the old installer path keeps working until the user upgrades; README of `LexiLocal` clearly points to the new repo.
- **The old desktop shortcuts on the user's machine (`LexiLocal UI.lnk`)** will continue to work after reinstall, because the install path doesn't change. They will be re-created by the new installer.
- **The activity log middleware** stays in the backend. The desktop app will keep polling `/logs` exactly as today.
- **CORS / firewall**: unchanged. Backend still binds `0.0.0.0:8000`. Desktop app talks to `localhost:8000` by default.
- **No new dependencies in the backend repo.** Pure extraction.

## Edge cases

- **User has not configured the backend path** on first launch → show the setup screen. Cannot proceed without it.
- **Backend directory exists but `run.sh` is missing** → error: "Backend install directory looks wrong. Reconfigure."
- **User runs the desktop app on a machine without Git Bash** → start/stop buttons disabled with explanation; chat/translate still work if backend is reachable.
- **Clipboard contains the same text twice in a row** → dedupe; only the latest timestamp is shown.
- **Clipboard contains a 1 MB paste** → dropped, with a console log line. The 10-item buffer is preserved.
- **User copies while app is closed** → those copies are not captured (session-only). Acceptable for v1.
- **Two instances of the desktop app run at once** → each has its own clipboard history (in-memory). Not a problem for v1.

## Tradeoffs

| Decision | Alternative | Why we chose this |
|---|---|---|
| Persistent config file | Hardcoded path | User controls install location; no broken heuristics |
| Clipboard polled in Rust | JS-only via `navigator.clipboard` | `navigator.clipboard` only sees the in-webview clipboard, not Windows system clipboard |
| Session-only clipboard history | Persist to disk | Simpler, fewer privacy concerns, faster to ship |
| Tabbed UI | Sidebar nav | Sidebar is more extensible but adds chrome for a 5-item set; tabs are enough for now |
| Two separate repos | Monorepo with workspaces | User wants independent evolution and clear ownership |

## Acceptance criteria (this change)

1. `LexiLocal` repo contains no `tauri-app/` directory after the change.
2. `Codex-Astartes` repo at `Documents/Projects/Codex-Astartes` builds successfully with `npm run tauri:build` and produces a working `.exe`.
3. The desktop app, on first launch, shows a setup screen asking for the backend install directory. After configuring, it persists the path.
4. The desktop app's Start/Stop buttons successfully start and stop the backend located at the configured path.
5. The base URL is editable in the UI; changes persist across restarts.
6. A new **Tools** tab is present and shows a **Clipboard history** panel with the last 10 text copies captured while the app was running, with timestamps.
7. The clipboard panel offers "Copy back" (sends the item to the system clipboard), "Send to Chat" (fills the Chat input and switches tabs), and "Send to Translate" (fills the Translate input and switches tabs).
8. `LexiLocal`'s README no longer references the desktop UI in detail; it links to `Codex-Astartes`.
9. No backend code or API changes. All existing `curl` examples in `LexiLocal/README.md` still work unchanged.
10. Both repos are independently git-versioned and pushed to GitHub.

## Open questions — RESOLVED

1. **Clipboard persistence:** ✅ Persist to disk. Stored in `config.toml` next to the `.exe` (same directory where the app is installed), so the app is portable — a USB-stick install carries its clipboard history with it.
2. **Setup screen:** ✅ Visible setup window on first launch (no tray icon in this change).
3. **Config file format:** ✅ TOML (fancy, comment-friendly, native Rust/Python support).
4. **Theme/dark mode:** ✅ Add a light/dark toggle in the sidebar. Dark is the default; light is a first-class theme. Both are real themes (not just CSS variables), with coherent palettes.

UI navigation: ✅ Sidebar. Replaces the current 2×2 grid. Sections: Chat, Translate, Tools, REST API, Activity Log. Settings + theme toggle live in the sidebar footer.

Proceeding to `spec.md`.
