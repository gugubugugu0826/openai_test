import os
from pathlib import Path

import requests

from desktop_agent.builtin_llm import is_builtin_server_ready, validate_builtin_files
from desktop_agent.config import load_config
from desktop_agent.i18n import t
from desktop_agent.scanner import get_scan_roots


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
            return True, t("health.config_ok_openai", provider=provider, api_model=api_model)
        if provider == "builtin":
            return True, t("health.config_ok_builtin", provider=provider, builtin_model=builtin_model)
        return True, t("health.config_ok", provider=provider, model=model)
    except Exception as exc:
        return False, t("health.config_error", error=exc)


def check_desktop_path():
    try:
        config = load_config()
        desktops = get_scan_roots(config)
        invalid = [
            str(desktop)
            for desktop in desktops
            if not desktop.exists() or not desktop.is_dir()
        ]

        if not invalid:
            paths = ", ".join(str(desktop) for desktop in desktops)
            return True, t("health.desktop_ok", paths=paths)
        return False, t("health.desktop_missing", paths=", ".join(invalid))
    except Exception as exc:
        return False, t("health.desktop_failed", error=exc)


def check_target_root():
    try:
        config = load_config()
        target = Path(config["normal_target_root"])
        target.mkdir(parents=True, exist_ok=True)

        test_file = target / ".agent_write_test.tmp"
        test_file.write_text("test", encoding="utf-8")
        test_file.unlink(missing_ok=True)

        return True, t("health.target_ok", target=target)
    except Exception as exc:
        return False, t("health.target_failed", error=exc)


def check_ollama_api():
    provider = get_provider()

    if provider in ["none", "openai_compatible", "builtin"]:
        return True, t("health.ollama_skip", provider=provider)
    if provider != "ollama":
        return False, t("health.unknown_provider", provider=provider)

    try:
        config = load_config()
        url = config["ollama_url"]
        tags_url = url.replace("/api/generate", "/api/tags")

        response = requests.get(tags_url, timeout=5)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])
        return True, t("health.ollama_ok", count=len(models))
    except Exception as exc:
        return False, t("health.ollama_failed", error=exc)


def check_model_exists():
    provider = get_provider()

    if provider == "none":
        return True, t("health.model_skip_none")
    if provider == "openai_compatible":
        return True, t("health.model_skip_openai")
    if provider == "builtin":
        return True, t("health.model_skip_builtin")
    if provider != "ollama":
        return False, t("health.unknown_provider", provider=provider)

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
            return True, t("health.model_found", model=model_name)
        return False, t("health.model_missing", model=model_name, models=model_names)
    except Exception as exc:
        return False, t("health.model_failed", error=exc)


def check_openai_compatible_config():
    provider = get_provider()

    if provider != "openai_compatible":
        return True, t("health.openai_skip", provider=provider)

    try:
        config = load_config()
        api_base_url = config.get("api_base_url", "").strip()
        api_model = config.get("api_model", "").strip()
        api_key = (
            os.environ.get("DESKTOP_AGENT_API_KEY", "").strip()
            or config.get("api_key", "").strip()
        )

        if not api_base_url:
            return False, t("health.openai_missing_base")
        if not api_model:
            return False, t("health.openai_missing_model")
        if not api_key:
            return False, t("health.openai_missing_key")

        return True, t("health.openai_ok")
    except Exception as exc:
        return False, t("health.openai_failed", error=exc)


def check_builtin_runtime():
    provider = get_provider()

    if provider != "builtin":
        return True, t("health.builtin_skip", provider=provider)

    try:
        cfg = validate_builtin_files()
        message = t(
            "health.builtin_ok",
            server=cfg["server_file"],
            model=cfg["model_file"],
            port=cfg["port"],
        )
        if is_builtin_server_ready():
            message += t("health.builtin_running_suffix")
        return True, message
    except Exception as exc:
        return False, t("health.builtin_failed", error=exc)


def check_modules():
    try:
        import desktop_agent.builtin_llm  # noqa: F401
        import desktop_agent.executor  # noqa: F401
        import desktop_agent.llm_provider  # noqa: F401
        import desktop_agent.memory  # noqa: F401
        import desktop_agent.planner  # noqa: F401
        import desktop_agent.reviewer  # noqa: F401
        import desktop_agent.scanner  # noqa: F401
        import desktop_agent.state  # noqa: F401
        import desktop_agent.workflow  # noqa: F401

        return True, t("health.modules_ok")
    except Exception as exc:
        return False, t("health.modules_failed", error=exc)


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
        results.append({"name": name, "ok": ok, "message": message})
    return results


def print_healthcheck():
    print("=" * 80)
    print(t("health.header"))
    print("=" * 80)

    results = run_healthcheck()
    all_ok = True

    for item in results:
        status = "OK" if item["ok"] else "FAIL"
        if not item["ok"]:
            all_ok = False
        print(f"[{status}] {item['name']}: {item['message']}")

    print("=" * 80)
    print(t("health.all_ok" if all_ok else "health.not_all_ok"))
    return all_ok
