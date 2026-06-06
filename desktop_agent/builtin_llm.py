# desktop_agent/builtin_llm.py

import os
import time
import socket
import subprocess
from pathlib import Path

import requests

from desktop_agent.config import load_config


_builtin_process = None


def get_app_dir():
    """
    普通 Python 运行时：项目根目录
    PyInstaller 打包后：exe 所在目录
    """
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

    # llama-server 的 /health：模型加载完成前返回 503(loading)，加载完成才返回 200。
    # 只有 200 才算“真正可用”，否则会出现“端口已开但模型没加载好”→ 推理 503。
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
    """轮询直到模型真正加载完成（/health=200）。process 退出则提前失败。"""
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
            f"找不到内置模型服务程序：{cfg['server_file']}\n"
            "请把 llama-server.exe 放到 runtime 文件夹。"
        )

    if not cfg["model_file"].exists():
        raise FileNotFoundError(
            f"找不到内置模型文件：{cfg['model_file']}\n"
            "请把 GGUF 小模型放到 models 文件夹，并命名为 qwen-small.gguf。"
        )

    return cfg


def start_builtin_server():
    """
    启动 llama-server。
    如果端口已经可用，就认为服务已经启动。
    """
    global _builtin_process

    cfg = validate_builtin_files()

    if is_builtin_server_ready():
        return cfg["chat_url"]

    # 端口已被占用（模型可能正在加载，或用户/上次进程已启动服务）：
    # 不要重复启动（会因端口占用而立即退出），直接等待其加载完成。
    if is_port_open(cfg["host"], cfg["port"], timeout=0.8):
        if wait_until_ready(cfg, timeout=180):
            return cfg["chat_url"]
        raise TimeoutError(
            "内置模型服务端口已占用，但模型在 180 秒内仍未加载完成。\n"
            "如果是上次的服务卡住，请结束 llama-server.exe 进程后重试。"
        )

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
        log_file.write(f"Starting builtin llama-server at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write("Command:\n")
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

    # 等待“模型真正加载完成”，而不是“端口刚打开”。
    wait_seconds = 180

    if _builtin_process.poll() is not None:
        raise RuntimeError(
            "内置模型服务启动后立即退出。\n"
            f"请查看日志：{server_log}"
        )

    if wait_until_ready(cfg, timeout=wait_seconds, process=_builtin_process):
        return cfg["chat_url"]

    if _builtin_process.poll() is not None:
        raise RuntimeError(
            "内置模型服务启动后退出，可能是模型文件损坏或内存不足。\n"
            f"请查看日志：{server_log}"
        )

    raise TimeoutError(
        f"内置模型服务启动超时（模型加载未在 {wait_seconds} 秒内完成）。\n"
        "可能是机器较慢或内存不足，可稍后重试，或改用“极速规则分类”。\n"
        f"详见日志：{server_log}"
    )


def ensure_builtin_server_running():
    """
    确保 builtin llama-server 可用，返回 OpenAI-compatible chat completions URL。
    """
    cfg = get_builtin_config()

    if is_builtin_server_ready():
        return cfg["chat_url"]

    return start_builtin_server()


def stop_builtin_server():
    """
    可选：停止当前 GUI 启动的 builtin 进程。
    注意：如果端口上是用户自己启动的服务，不会被这里关闭。
    """
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