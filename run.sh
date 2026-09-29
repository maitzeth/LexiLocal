#!/usr/bin/env bash
# Control script for the local Ollama-backed REST server.
# Usage: ./run.sh [start|stop|status|restart|port|pull|logs]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/server.env"
PID_FILE="$SCRIPT_DIR/server.pid"
LOG_FILE="$SCRIPT_DIR/server.log"

# shellcheck source=/dev/null
if [[ -f "$ENV_FILE" ]]; then
    source "$ENV_FILE"
fi

OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
SERVER_PORT="${SERVER_PORT:-8000}"

ensure_python() {
    # Prefer a real Windows Python installation over the Microsoft Store alias.
    local candidates=(
        "/c/Users/andre/AppData/Local/Programs/Python/Python312/python.exe"
        "/c/Users/andre/AppData/Local/Programs/Python/Python311/python.exe"
        "/c/Users/andre/AppData/Local/Programs/Python/Python310/python.exe"
        "$(command -v python3 || true)"
        "$(command -v python || true)"
    )

    for py in "${candidates[@]}"; do
        if [[ -n "$py" && -x "$py" ]] && "$py" --version &>/dev/null; then
            echo "$py"
            return 0
        fi
    done

    echo "Error: Python is not installed or only the Microsoft Store alias is available." >&2
    echo "Install Python from https://python.org or disable the 'App execution aliases' for python/python3." >&2
    exit 1
}

install_deps() {
    local py
    py=$(ensure_python)
    echo "Installing Python dependencies..."
    "$py" -m pip install -q -r requirements.txt
}

cmd_start() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Server already running (PID $(cat "$PID_FILE")) on port $SERVER_PORT."
        exit 0
    fi

    local py
    py=$(ensure_python)
    install_deps

    echo "Starting Ollama Qwen2.5 server on $SERVER_HOST:$SERVER_PORT..."
    echo "Model: $OLLAMA_MODEL | Ollama: $OLLAMA_HOST"

    # Delegate to start.py — it uses the Windows subprocess API to spawn
    # server.py detached and write the real Python PID to server.pid.
    # Git Bash on Windows shims 'nohup ... &' in a way that makes $! return
    # a bash subshell PID, not python's PID. start.py bypasses that.
    if ! "$py" start.py; then
        echo "Server failed to start. Check logs: $LOG_FILE" >&2
        rm -f "$PID_FILE"
        exit 1
    fi

    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
    echo "Server running with PID $pid. Logs: $LOG_FILE"
    echo "Health check: http://$SERVER_HOST:$SERVER_PORT/health"
}

cmd_stop() {
    if [[ ! -f "$PID_FILE" ]]; then
        echo "No PID file found; server may not be running."
        return 0
    fi
    local pid
    pid=$(cat "$PID_FILE")
    # Use Windows taskkill since the PID is a Windows PID, not a bash subshell.
    if taskkill //PID "$pid" //T //F >/dev/null 2>&1; then
        echo "Stopping server (PID $pid)..."
        rm -f "$PID_FILE"
        echo "Stopped."
    else
        echo "PID $pid is not running. Cleaning up."
        rm -f "$PID_FILE"
    fi
}

cmd_status() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Server is running (PID $(cat "$PID_FILE")) on port $SERVER_PORT."
        echo "Health: http://$SERVER_HOST:$SERVER_PORT/health"
    else
        echo "Server is not running."
        rm -f "$PID_FILE" 2>/dev/null || true
    fi
}

cmd_restart() {
    cmd_stop || true
    cmd_start
}

cmd_port() {
    local new_port=${1:-}
    if [[ -z "$new_port" ]]; then
        echo "Current port: $SERVER_PORT"
        echo "Usage: ./run.sh port <new-port>"
        exit 1
    fi
    if ! [[ "$new_port" =~ ^[0-9]+$ ]]; then
        echo "Error: port must be a number." >&2
        exit 1
    fi

    # Update server.env
    if grep -q "^SERVER_PORT=" "$ENV_FILE"; then
        sed -i "s/^SERVER_PORT=.*/SERVER_PORT=$new_port/" "$ENV_FILE"
    else
        echo "SERVER_PORT=$new_port" >> "$ENV_FILE"
    fi

    echo "Port updated to $new_port in $ENV_FILE."
    if [[ -f "$PID_FILE" ]]; then
        echo "Restart server to apply: ./run.sh restart"
    fi
}

cmd_pull() {
    echo "Pulling model '$OLLAMA_MODEL' with Ollama..."
    ollama pull "$OLLAMA_MODEL"
}

cmd_logs() {
    if [[ -f "$LOG_FILE" ]]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found."
    fi
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    restart) cmd_restart ;;
    port)    cmd_port "${2:-}" ;;
    pull)    cmd_pull ;;
    logs)    cmd_logs ;;
    *)
        echo "Usage: $0 [start|stop|status|restart|port <n>|pull|logs]"
        echo ""
        echo "Examples:"
        echo "  $0 start          # install deps and start server"
        echo "  $0 stop           # stop server"
        echo "  $0 port 8080      # change port"
        echo "  $0 pull           # download the model with ollama"
        exit 1
        ;;
esac
