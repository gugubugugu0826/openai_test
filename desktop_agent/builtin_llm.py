import os
import socket
import subprocess
import time
from pathlib import Path

import requests

from desktop_agent.config import load_config
from desktop_agent.i18n import t


_builtin_process = None


def get_app_dir():
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_builtin_config():
    config = load_config()
    app_dir = get_app_dir()

    host = config.get("builtin_server_host", "127.0.0.1")
    port = int(config.get("builtin_server_port", 18080))
    model_path = config.get("builtin_model_path", "models\\qwen-small.gguf")
    server_path = config.get("builtin_server_path", "runtime\\llama-server.exe")
    context_size = int(config.get("builtin_context_size", 4096))
    threads = int(config.get("builtin_threads", 8))

    model_file = Path(model_path)
    server_file = Path(server_path)

    if not model_file.is_absolute():
        model_file = app_dir / model_file

    if not server_file.is_absolute():
        server_file = app_dir / server_file

    return {
        "app_dir": app_dir,
        "host": host,
        "port": port,
        "model_file": model_file,
        "server_file": server_file,
        "context_size": context_size,
        "threads": threads,
        "base_url": f"http://{host}:{port}",
        "chat_url": f"http://{host}:{port}/v1/chat/completions",
    }


def is_port_open(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def is_builtin_server_ready():
    cfg = get_builtin_config()

    if not is_port_open(cfg["host"], cfg["port"], timeout=0.8):
        return False

    try:
        response = requests.get(f"{cfg['base_url']}/health", timeout=2)
        if response.status_code == 200:
            return True
        if response.status_code == 503:
            return False
    except Exception:
        pass

    try:
        response = requests.get(f"{cfg['base_url']}/v1/models", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def wait_until_ready(cfg, timeout=180, process=None):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process is not None and process.poll() is not None:
            return False
        if is_builtin_server_ready():
            return True
        time.sleep(1)
    return False


def validate_builtin_files():
    cfg = get_builtin_config()

    if not cfg["server_file"].exists():
        raise FileNotFoundError(
            t("builtin.server_missing", path=cfg["server_file"])
        )

    if not cfg["model_file"].exists():
        raise FileNotFoundError(
            t("builtin.model_missing", path=cfg["model_file"])
        )

    return cfg


def start_builtin_server():
    global _builtin_process

    cfg = validate_builtin_files()

    if is_builtin_server_ready():
        return cfg["chat_url"]

    if is_port_open(cfg["host"], cfg["port"], timeout=0.8):
        if wait_until_ready(cfg, timeout=180):
            return cfg["chat_url"]
        raise TimeoutError(t("builtin.port_busy_timeout"))

    command = [
        str(cfg["server_file"]),
        "-m",
        str(cfg["model_file"]),
        "--host",
        cfg["host"],
        "--port",
        str(cfg["port"]),
        "-c",
        str(cfg["context_size"]),
        "-t",
        str(cfg["threads"]),
    ]

    creationflags = 0
    startupinfo = None

    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    log_dir = cfg["app_dir"] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    server_log = log_dir / "builtin_llm_server.log"

    with open(server_log, "a", encoding="utf-8") as log_file:
        log_file.write("\n" + "=" * 80 + "\n")
        log_file.write(
            t("builtin.log_starting", timestamp=time.strftime("%Y-%m-%d %H:%M:%S")) + "\n"
        )
        log_file.write(t("builtin.log_command") + "\n")
        log_file.write(" ".join(command) + "\n")

    log_handle = open(server_log, "a", encoding="utf-8", errors="ignore")

    _builtin_process = subprocess.Popen(
        command,
        cwd=str(cfg["app_dir"]),
        stdout=log_handle,
        stderr=log_handle,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )

    wait_seconds = 180

    if _builtin_process.poll() is not None:
        raise RuntimeError(t("builtin.exited_immediately", path=server_log))

    if wait_until_ready(cfg, timeout=wait_seconds, process=_builtin_process):
        return cfg["chat_url"]

    if _builtin_process.poll() is not None:
        raise RuntimeError(t("builtin.exited_while_loading", path=server_log))

    raise TimeoutError(
        t("builtin.start_timeout", seconds=wait_seconds, path=server_log)
    )


def ensure_builtin_server_running():
    cfg = get_builtin_config()

    if is_builtin_server_ready():
        return cfg["chat_url"]

    return start_builtin_server()


def stop_builtin_server():
    global _builtin_process

    if _builtin_process is None:
        return

    try:
        if _builtin_process.poll() is None:
            _builtin_process.terminate()
            time.sleep(1)
            if _builtin_process.poll() is None:
                _builtin_process.kill()
    except Exception:
        pass

    _builtin_process = None
