use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Stdio;
use tokio::process::{Child, Command};
use tokio::sync::Mutex;

struct ServerProcess {
    child: Mutex<Option<Child>>,
}

static SERVER: Lazy<ServerProcess> = Lazy::new(|| ServerProcess {
    child: Mutex::new(None),
});

#[derive(Serialize, Deserialize, Debug)]
struct HealthResponse {
    status: String,
    ollama_host: String,
    model: String,
}

#[derive(Serialize)]
struct ServerStatus {
    running: bool,
    pid: Option<u32>,
    health: Option<HealthResponse>,
    error: Option<String>,
}

fn possible_server_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();

    // 1. Explicit override via environment variable.
    if let Ok(env_dir) = std::env::var("OLLAMA_QWEN_SERVER_DIR") {
        dirs.push(PathBuf::from(env_dir));
    }

    // 2. Fixed development path for this machine.
    dirs.push(PathBuf::from("C:/Users/andre/Documents/Projects/ollama-qwen-server"));

    // 3. Next to the Tauri app bundle directory.
    //    Bundle layout: .../ollama-qwen-server/tauri-app/src-tauri/target/release/ollama-qwen-ui.exe
    if let Some(exe_dir) = std::env::current_exe().ok().and_then(|p| p.parent().map(|p| p.to_path_buf())) {
        // target/release -> target -> src-tauri -> tauri-app -> ollama-qwen-server
        dirs.push(exe_dir.join("../../../../ollama-qwen-server"));
        // Or the exe is next to the server folder.
        dirs.push(exe_dir.join("../ollama-qwen-server"));
        dirs.push(exe_dir.join("ollama-qwen-server"));
    }

    // 4. Current working directory or one level up.
    if let Ok(cwd) = std::env::current_dir() {
        dirs.push(cwd.join("ollama-qwen-server"));
        dirs.push(cwd.join("../ollama-qwen-server"));
    }

    dirs
}

fn find_server_dir() -> Option<PathBuf> {
    for dir in possible_server_dirs() {
        let canonical = dir.canonicalize();
        if let Ok(canonical) = canonical {
            let run_sh = canonical.join("run.sh");
            let server_py = canonical.join("server.py");
            if run_sh.exists() && server_py.exists() {
                return Some(canonical);
            }
        }
    }
    None
}

#[tauri::command]
async fn start_server() -> Result<ServerStatus, String> {
    {
        let mut guard = SERVER.child.lock().await;
        if let Some(child) = guard.as_mut() {
            match child.try_wait() {
                Ok(None) => {
                    return Ok(ServerStatus {
                        running: true,
                        pid: child.id(),
                        health: None,
                        error: None,
                    });
                }
                _ => {
                    *guard = None;
                }
            }
        }

        let dir = find_server_dir()
            .ok_or("Could not find the server project directory. Set OLLAMA_QWEN_SERVER_DIR.")?;

        let child = Command::new("bash")
            .arg(dir.join("run.sh"))
            .arg("start")
            .current_dir(&dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("Failed to start server: {e}. Is Git Bash installed?"))?;

        *guard = Some(child);
    }

    // Give the server a moment to boot, then check health.
    tokio::time::sleep(tokio::time::Duration::from_millis(2500)).await;
    Ok(check_server_health_internal().await)
}

#[tauri::command]
async fn stop_server() -> Result<ServerStatus, String> {
    let mut guard = SERVER.child.lock().await;
    if let Some(child) = guard.as_mut() {
        let _ = child.kill().await;
        let _ = child.wait().await;
    }
    *guard = None;

    Ok(ServerStatus {
        running: false,
        pid: None,
        health: None,
        error: None,
    })
}

#[tauri::command]
async fn server_status() -> Result<ServerStatus, String> {
    let guard = SERVER.child.lock().await;
    let running = guard.as_ref().and_then(|c| c.id()).is_some();
    let pid = guard.as_ref().and_then(|c| c.id());

    Ok(ServerStatus {
        running,
        pid,
        health: None,
        error: None,
    })
}

async fn check_server_health_internal() -> ServerStatus {
    match reqwest::get("http://localhost:8000/health").await {
        Ok(resp) => match resp.json::<HealthResponse>().await {
            Ok(health) => ServerStatus {
                running: health.status == "ok",
                pid: None,
                health: Some(health),
                error: None,
            },
            Err(e) => ServerStatus {
                running: false,
                pid: None,
                health: None,
                error: Some(format!("Parse error: {e}")),
            },
        },
        Err(e) => ServerStatus {
            running: false,
            pid: None,
            health: None,
            error: Some(format!("{e}")),
        },
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![start_server, stop_server, server_status])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
