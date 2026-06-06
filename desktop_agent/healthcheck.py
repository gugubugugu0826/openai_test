# desktop_agent/healthcheck.py

import os
import requests
from pathlib import Path

from desktop_agent.config import load_config
from desktop_agent.builtin_llm import get_builtin_config, is_builtin_server_ready, validate_builtin_files


def get_provider():
    try:
        config = load_config()
        return config.get("llm_provider", "none").lower().strip()
    except Exception:
        return "unknown"


def check_config():
    try:
        config = load_config()
        provider = config.get("llm_provider", "none")
        model = config.get("model", "")
        api_model = config.get("api_model", "")
        builtin_model = config.get("builtin_model_path", "")

        if provider == "openai_compatible":
            return True, f"config.json 正常，provider：{provider}，API 模型：{api_model}"

        if provider == "builtin":
            return True, f"config.json 正常，provider：{provider}，内置模型：{builtin_model}"

        return True, f"config.json 正常，provider：{provider}，模型：{model}"
    except Exception as e:
        return False, f"config.json 错误：{e}"


def check_desktop_path():
    try:
        config = load_config()
        desktop = Path(config["desktop_path"])

        if desktop.exists() and desktop.is_dir():
            return True, f"扫描路径存在：{desktop}"

        return False, f"扫描路径不存在：{desktop}"
    except Exception as e:
        return False, f"扫描路径检查失败：{e}"


def check_target_root():
    try:
        config = load_config()
        target = Path(config["normal_target_root"])

        target.mkdir(parents=True, exist_ok=True)

        test_file = target / ".agent_write_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink(missing_ok=True)

        return True, f"目标目录可写：{target}"
    except Exception as e:
        return False, f"目标目录不可写：{e}"


def check_ollama_api():
    provider = get_provider()

    if provider in ["none", "openai_compatible", "builtin"]:
        return True, f"当前 provider={provider}，不需要检查 Ollama"

    if provider != "ollama":
        return False, f"未知 provider：{provider}"

    try:
        config = load_config()
        url = config["ollama_url"]
        tags_url = url.replace("/api/generate", "/api/tags")

        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        return True, f"Ollama API 正常，检测到模型数量：{len(models)}"
    except Exception as e:
        return False, f"Ollama API 连接失败：{e}"


def check_model_exists():
    provider = get_provider()

    if provider == "none":
        return True, "当前 provider=none，不需要检查模型"

    if provider == "openai_compatible":
        return True, "当前 provider=openai_compatible，不检查本地模型"

    if provider == "builtin":
        return True, "当前 provider=builtin，本地模型由 Builtin Runtime 检查"

    if provider != "ollama":
        return False, f"未知 provider：{provider}"

    try:
        config = load_config()
        model_name = config["model"]
        url = config["ollama_url"]
        tags_url = url.replace("/api/generate", "/api/tags")

        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        model_names = []
        for model in models:
            name = model.get("name") or model.get("model")
            if name:
                model_names.append(name)

        if model_name in model_names:
            return True, f"模型存在：{model_name}"

        return False, f"模型不存在：{model_name}，当前模型：{model_names}"
    except Exception as e:
        return False, f"模型检查失败：{e}"


def check_openai_compatible_config():
    provider = get_provider()

    if provider != "openai_compatible":
        return True, f"当前 provider={provider}，不检查云端 API 配置"

    try:
        config = load_config()

        api_base_url = config.get("api_base_url", "").strip()
        api_model = config.get("api_model", "").strip()
        api_key = (
            os.environ.get("DESKTOP_AGENT_API_KEY", "").strip()
            or config.get("api_key", "").strip()
        )

        if not api_base_url:
            return False, "api_base_url 为空"

        if not api_model:
            return False, "api_model 为空"

        if not api_key:
            return False, "api_key 为空。可在 Config 中填写，或设置环境变量 DESKTOP_AGENT_API_KEY"

        return True, "OpenAI-compatible API 配置存在"
    except Exception as e:
        return False, f"OpenAI-compatible 配置检查失败：{e}"


def check_builtin_runtime():
    provider = get_provider()

    if provider != "builtin":
        return True, f"当前 provider={provider}，不检查 builtin runtime"

    try:
        cfg = validate_builtin_files()

        message = (
            f"builtin runtime 文件存在。server={cfg['server_file']}，"
            f"model={cfg['model_file']}，port={cfg['port']}"
        )

        if is_builtin_server_ready():
            message += "，服务已运行"

        return True, message

    except Exception as e:
        return False, f"builtin runtime 检查失败：{e}"


def check_modules():
    try:
        import desktop_agent.scanner
        import desktop_agent.planner
        import desktop_agent.reviewer
        import desktop_agent.executor
        import desktop_agent.workflow
        import desktop_agent.memory
        import desktop_agent.state
        import desktop_agent.llm_provider
        import desktop_agent.builtin_llm

        return True, "核心模块导入正常"
    except Exception as e:
        return False, f"核心模块导入失败：{e}"


def run_healthcheck():
    checks = [
        ("Config", check_config),
        ("Desktop Path", check_desktop_path),
        ("Target Root", check_target_root),
        ("Ollama API", check_ollama_api),
        ("Model", check_model_exists),
        ("OpenAI-compatible Config", check_openai_compatible_config),
        ("Builtin Runtime", check_builtin_runtime),
        ("Modules", check_modules),
    ]

    results = []

    for name, func in checks:
        ok, message = func()
        results.append({
            "name": name,
            "ok": ok,
            "message": message
        })

    return results


def print_healthcheck():
    print("=" * 80)
    print("Agent Health Check：环境自检")
    print("=" * 80)

    results = run_healthcheck()

    all_ok = True

    for item in results:
        status = "OK" if item["ok"] else "FAIL"

        if not item["ok"]:
            all_ok = False

        print(f"[{status}] {item['name']}: {item['message']}")

    print("=" * 80)

    if all_ok:
        print("环境自检通过，可以运行 Agent。")
    else:
        print("环境自检未完全通过，请先修复 FAIL 项。")

    return all_ok