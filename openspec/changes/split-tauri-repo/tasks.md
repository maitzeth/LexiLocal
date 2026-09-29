# Tasks: Split the Tauri desktop app into its own repository (`CodexAstarte`)

Concrete implementation tasks for `apply`. Each `- [ ]` line is a unit of work. Grouped by PR for chained delivery (~400 lines / PR review budget).

---

## PR 1 — Repository split

**Goal:** Move Tauri source to its own repo; clean the backend repo of desktop-app files.

**Repos touched:** `LexiLocal` (slim down), `CodexAstarte` (new).

### Backend repo (`LexiLocal`)

- [ ] Remove `tauri-app/` directory from working tree (and from `.gitignore` if anything is repo-wide about it — it isn't, just the directory itself).
- [ ] Delete `launch-ui.bat`, `launch-ui.ps1`, `toggle-server.ps1`, `toggle-server.bat`, `create-desktop-shortcut.ps1` (they move to the new repo).
- [ ] Update `README.md`:
  - [ ] Remove the "Native Windows UI" section.
  - [ ] Remove `tauri-app/` from the Project Structure listing.
  - [ ] Remove references to `launch-ui.bat`, `toggle-server.ps1`, `create-desktop-shortcut.ps1`.
  - [ ] Add a "Desktop UI" section linking to `CodexAstarte`.
- [ ] Commit: `chore: extract tauri app into CodexAstarte repo`.

### Desktop repo (`CodexAstarte`)

- [ ] Create `Documents/Projects/CodexAstarte/`.
- [ ] Create new GitHub repo `maitzeth/CodexAstarte` (user action — paused until user confirms the repo exists).
- [ ] `git init` inside the new folder.
- [ ] Move all Tauri source files from `LexiLocal/tauri-app/` to `CodexAstarte/` (drop the `tauri-app/` prefix).
- [ ] Move launcher scripts (`launch-ui.bat`, `launch-ui.ps1`, `toggle-server.ps1`, `toggle-server.bat`, `create-desktop-shortcut.ps1`) from `LexiLocal/` to `CodexAstarte/`.
- [ ] Update `package.json`:
  - [ ] Rename `name` to `codexastarte`.
  - [ ] Update `tauri.conf.json` reference paths (no change needed if we keep relative paths).
- [ ] Set up `.gitignore` (Tauri/Vite/Rust ignore patterns).
- [ ] Add a minimal `README.md` pointing to the proposal/spec for now; full README in PR 2.
- [ ] First commit: `chore: initial import of Tauri app from LexiLocal`.
- [ ] Verify `npm install && npm run tauri:build` produces a working `.exe` in the new repo (AC #2 baseline).

**PR 1 verification:**
- `LexiLocal` no longer contains `tauri-app/` (AC #1).
- `CodexAstarte` builds with `npm run tauri:build` and produces a `.exe` (AC #2).
- Both repos pushed to GitHub (AC #10 partial).

---

## PR 2 — Persistent config + sidebar shell (dark theme)

**Goal:** Replace the path-heuristic in `main.rs` with a real, persistent TOML config. Build the sidebar shell with dark theme. Port existing panels (Chat, Translate, REST API, Activity Log, Settings) to the section model.

**Repo:** `CodexAstarte`.

### Rust

- [ ] Add deps to `src-tauri/Cargo.toml`: `toml = "0.8"`, `chrono = { version = "0.4", features = ["clock"] }`, `tauri-plugin-clipboard-manager = "2"`, `tauri-plugin-dialog = "2"`.
- [ ] Add JS deps to `package.json`: `@tauri-apps/plugin-clipboard-manager = "^2"`, `@tauri-apps/plugin-dialog = "^2"`.
- [ ] Update `tauri.conf.json`: `productName = "CodexAstarte"`, `identifier = "com.codexastarte.app"`.
- [ ] Update `src-tauri/capabilities/default.json`: add `clipboard-manager:allow-read-text`, `clipboard-manager:allow-write-text`, `dialog:allow-open`.
- [ ] Create `src-tauri/src/config.rs` with `Config` struct, `config_path()`, `load()`, `save()` (atomic tmp+rename), defaults per spec §2.3.
- [ ] Create `src-tauri/src/server.rs` with `start`, `stop`, `status` functions using `config.server.dir` instead of `possible_server_dirs()`.
- [ ] Create `src-tauri/src/commands.rs` with: `get_config`, `set_server_dir`, `set_server_url`, `set_theme`, `start_server`, `stop_server`, `server_status`.
- [ ] Refactor `src-tauri/src/main.rs` to: load config at startup, register `AppState { config, child }`, register commands, remove the old path-heuristic.
- [ ] Update `launch-ui.bat` / `launch-ui.ps1` to launch the new `.exe` (path/name may change).

### Frontend

- [ ] Create `src/icons.ts` with 10 Lucide-style SVG icon functions.
- [ ] Create `src/lib/tauri.ts` with typed wrappers around `invoke()`.
- [ ] Create `src/lib/theme.ts` with `applyTheme(theme)` setting `document.documentElement.dataset.theme`.
- [ ] Rewrite `src/styles.css` with CSS variables on `:root[data-theme="dark"]` and `:root[data-theme="light"]`. Two complete variable sets.
- [ ] Create `src/sections/types.ts` with `Section`, `SectionController`, `SectionContext` interfaces.
- [ ] Port Chat panel → `src/sections/chat.ts` (uses `/v1/chat/completions` streaming).
- [ ] Port Translate panel → `src/sections/translate.ts`.
- [ ] Port REST API panel → `src/sections/rest.ts`.
- [ ] Port Activity Log panel → `src/sections/activity.ts`.
- [ ] Port Settings panel → `src/sections/settings.ts` (backend dir picker via `dialog`, theme toggle deferred to PR 4).
- [ ] Create `src/tools/clipboard.ts` stub (returns `{ render(): HTMLElement }` with a "coming soon" placeholder for now).
- [ ] Create `src/sections/tools.ts` that mounts the clipboard view (placeholder until PR 3).
- [ ] Rewrite `src/main.ts` to render the sidebar shell, mount the active section, handle activation.
- [ ] Render setup screen overlay when `config.server.dir === ""`. On save, re-render the shell.

### README

- [ ] Write the real `CodexAstarte/README.md`: what it is, prerequisites, install, first-run setup, usage walkthrough of each sidebar section, `config.toml` reference, troubleshooting.

**PR 2 verification (AC #3, #4, #5):**
- Delete `config.toml` next to a built `.exe`; launch → setup overlay appears; pick a valid backend dir → main UI renders (AC #3).
- Start/Stop buttons work (AC #4).
- Base URL editable in Settings; change persists across restarts (AC #5).

---

## PR 3 — Tools tab + clipboard history

**Goal:** Add the Tools section with Windows clipboard history.

**Repo:** `CodexAstarte`.

### Rust

- [ ] Create `src-tauri/src/clipboard.rs` with the polling background task (spec §3.5).
- [ ] Add clipboard commands to `commands.rs`: `get_clipboard_history`, `clear_clipboard_history`, `copy_to_clipboard`, `set_clipboard_poll_ms`.
- [ ] Wire the poller spawn in `main.rs::setup`.
- [ ] Emit `clipboard://changed` events to the frontend.

### Frontend

- [ ] Replace placeholder in `src/tools/clipboard.ts` with a real view:
  - [ ] List of items: timestamp + first ~80 chars preview + full text on hover.
  - [ ] Per-item actions: **Copy back** (`copy_to_clipboard`), **→ Chat** (fill chat input + `switchTo("chat")`), **→ Translate** (fill translate input + `switchTo("translate")`).
  - [ ] Header: **Clear**, **Pause/Resume** toggle, **Interval** input.
- [ ] Update `src/sections/tools.ts` to mount the clipboard view.
- [ ] Add `tauri.onClipboardChanged` listener in the Tools section; update the list on each event.
- [ ] When the Tools section is inactive, the listener is dropped on `destroy()`.

**PR 3 verification (AC #6, #7):**
- Copy 5 different things to the Windows clipboard while the app runs; Tools tab shows 5 entries with timestamps (AC #6).
- **Copy back** puts the item on the system clipboard (AC #7).
- **→ Chat** fills the Chat textarea and switches to the Chat tab (AC #7).
- **→ Translate** does the same for Translate (AC #7).

---

## PR 4 — Light theme + theme toggle + settings polish

**Goal:** Add the second theme and the toggle in the sidebar.

**Repo:** `CodexAstarte`.

### Frontend

- [ ] Add `:root[data-theme="light"]` CSS variable set in `src/styles.css`.
- [ ] Add theme toggle in the sidebar footer: button with sun/moon icon, calls `tauri.setTheme()`.
- [ ] In `src/sections/settings.ts`: add a "Theme" radio (dark/light) calling the same `tauri.setTheme()`.
- [ ] Verify all panels (Chat, Translate, Tools, REST API, Activity Log, Settings) read well in light mode — adjust any contrast issues.
- [ ] Verify the sidebar itself is legible in light mode.

**PR 4 verification:**
- Click theme toggle → whole UI switches theme instantly.
- Toggle theme → restart app → theme persists.
- Light theme is a real theme (all panels legible, not just inverted dark).

---

## PR 5 — End-to-end acceptance pass

**Goal:** Walk through every acceptance criterion from the spec and verify.

- [ ] AC #1: `find LexiLocal -name tauri-app -type d` returns nothing.
- [ ] AC #2: `CodexAstarte` builds, installer creates Start Menu + Desktop shortcuts named **CodexAstarte**.
- [ ] AC #3: First-launch setup screen flow.
- [ ] AC #4: Start/Stop buttons.
- [ ] AC #5: Base URL persists.
- [ ] AC #6: Tools tab shows clipboard history.
- [ ] AC #7: Clipboard actions work.
- [ ] AC #8: `LexiLocal/README.md` links to the desktop repo.
- [ ] AC #9: No backend code changes (`git diff master@{1} -- server.py run.sh requirements.txt` is empty).
- [ ] AC #10: Both repos pushed.

---

## PR-by-PR review budget

| PR | Estimated changed lines | Status |
|---|---|---|
| PR 1 — Repo split | ~50 (moves) + ~30 (README) + ~80 (new repo init) | Well under budget |
| PR 2 — Config + shell | ~700-900 | **Exceeds budget → split if needed during apply** |
| PR 3 — Clipboard | ~300-400 | At budget |
| PR 4 — Light theme | ~150-200 | Under budget |
| PR 5 — Acceptance pass | ~0 (just docs) | Under budget |

If PR 2 exceeds 400 lines after implementation, it will be split mid-apply into PR 2a (config + Rust) and PR 2b (sidebar + frontend sections).

---

## Notes for `apply`

- The user runs `npm run tauri:build` at the end of each PR that touches Tauri code. The apply phase will not run builds unless asked.
- The user creates the GitHub repo `CodexAstarte` (one-time) before PR 1's final push.
- Each PR is committed, pushed, and then `apply` pauses to let the user verify before moving to the next.
