# Apply report: split-tauri-repo

All 5 PRs shipped to both `LexiLocal` and `Codex-Astartes` repos.

## Commits

### `LexiLocal` (https://github.com/maitzeth/LexiLocal)
- `1ed8388` docs(sdd): split-tauri-repo change artifacts (proposal, spec, design, tasks)
- `ca08daf` docs(sdd): rename desktop repo to Codex-Astartes (matches GitHub URL)
- `d6e0190` chore: extract tauri app into Codex-Astartes repo

### `Codex-Astartes` (https://github.com/maitzeth/Codex-Astartes)
- `00a3e35` chore: initial import of Tauri app from LexiLocal
- `2fdaf39` feat(rust): add persistent config, backend lifecycle, and command surface
- `305da27` feat(ui): sidebar shell with 6 sections, dark theme, setup screen
- `a7d8203` feat(clipboard): real Windows clipboard history in Tools tab
- `66fc829` feat(theme): add light theme with full variable palette
- `9e9ce1b` docs: full README for Codex-Astartes

## Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | `LexiLocal` repo contains no `tauri-app/` | Pass (0 tracked files) |
| 2 | `Codex-Astartes` builds and produces a working `.exe` | Pass (6.7 MB exe + 1.7 MB NSIS installer; launches without crash) |
| 3 | First-launch setup screen | Pass (renders overlay when `config.server.dir` empty) |
| 4 | Start/Stop buttons work | Pass (Rust commands read `config.server.dir`, no heuristic) |
| 5 | Base URL persists | Pass (Settings UI + `config.toml`) |
| 6 | Tools tab + clipboard history | Pass (poller emits `clipboard://changed`, persists to TOML) |
| 7 | Clipboard actions (Copy, → Chat, → Translate) | Pass |
| 8 | `LexiLocal/README.md` links to `Codex-Astartes` | Pass (9 references) |
| 9 | No backend code changes | Pass (no commits to server.py/run.sh/requirements.txt during this change) |
| 10 | Both repos pushed | Pass |

## Artifacts

- Backend: `LexiLocal` at `C:/Users/andre/Documents/Projects/ollama-qwen-server`
- Frontend: `Codex-Astartes` at `C:/Users/andre/Documents/Projects/Codex-Astartes`
- SDD artifacts: `LexiLocal/openspec/changes/split-tauri-repo/`
