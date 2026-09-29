"""Spawn the FastAPI server in a detached process and record the real PID.

Git Bash on Windows shims `nohup ... &` in a way that makes `$!` return a
bash-subshell PID instead of the actual python.exe PID. This wrapper uses
the Windows subprocess API directly so we get the real PID and can kill
it cleanly later.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID_FILE = HERE / "server.pid"
LOG_FILE = HERE / "server.log"
PY_EXE = sys.executable

# Read OLLAMA_HOST, SERVER_HOST, SERVER_PORT from server.env so the child
# process sees the same config the parent did.
env_path = HERE / "server.env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# Detach from this helper so killing the helper doesn't kill the server.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

log = open(LOG_FILE, "ab", buffering=0)
proc = subprocess.Popen(
    [PY_EXE, str(HERE / "server.py")],
    stdout=log,
    stderr=log,
    stdin=subprocess.DEVNULL,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    cwd=str(HERE),
    env=os.environ.copy(),
)

PID_FILE.write_text(str(proc.pid), encoding="utf-8")
print(f"Server started with PID {proc.pid}")
