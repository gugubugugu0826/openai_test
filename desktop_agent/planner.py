from __future__ import annotations

import json

from desktop_agent.categories import CATEGORIES
from desktop_agent.config import load_config
from desktop_agent.i18n import t
from desktop_agent.llm_provider import classify_with_llm_provider
from desktop_agent.memory import memory_classify_item
from desktop_agent.plan_explainer import explain_current_plan
from desktop_agent.scanner import OBSERVATION_FILE
from desktop_agent.state import now_str, require_file, update_state
from desktop_agent.storage import load_json, save_json


PLAN_FILE = "desktop_agent_plan.json"


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".heic"}
VIDEO_AUDIO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac",
}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"}
INSTALLER_EXTS = {".exe", ".msi", ".apk", ".dmg", ".pkg"}
CODE_EXTS = {
    ".py", ".java", ".js", ".ts", ".html", ".css", ".cpp", ".c",
    ".cs", ".go", ".rs", ".php", ".rb", ".ipynb", ".sql",
    ".json", ".xml", ".yaml", ".yml", ".md", ".r", ".rmd", ".duckdb",
}


def contains_any(text, keywords):
    text = text.lower()
    return any(keyword.lower() in text for keyword in keywords)


def item_search_text(item):
    parts = [
        item.get("name", ""),
        item.get("display_name", ""),
        item.get("suffix", ""),
        item.get("content_summary", ""),
    ]

    folder_summary = item.get("folder_summary")
    if isinstance(folder_summary, dict):
        parts.append(" ".join(folder_summary.get("sampled_items", [])[:80]))
        parts.append(" ".join(folder_summary.get("subfolders", [])[:40]))

        for hint in folder_summary.get("content_hints", []):
            if isinstance(hint, dict):
                parts.append(hint.get("file", ""))
                parts.append(hint.get("summary", ""))

        exts = folder_summary.get("extensions", {})
        if isinstance(exts, dict):
            parts.append(" ".join(exts.keys()))

    return " ".join(parts).lower()


def build_result(item, category, reason, classified_by):
    result = {
        "path": item["path"],
        "name": item["name"],
        "type": item["type"],
        "category": category,
        "reason": reason,
        "classified_by": classified_by,
    }
    if item.get("desktop_root"):
        result["desktop_root"] = item["desktop_root"]
    if item.get("source_id"):
        result["source_id"] = item["source_id"]
    return result


def rule_classify_item(item):
    suffix = item.get("suffix", "").lower()
    item_type = item.get("type", "file")
    text = item_search_text(item)

    if item_type == "shortcut":
        if contains_any(text, ["steam", "epic", "wegame", "hoyoplay", "genshin", "原神", "鸣潮", "apex", "minecraft", "stardew", "overcooked", "game"]):
            return build_result(item, "游戏相关", t("planner.reason.shortcut_game"), "rule")
        if contains_any(text, ["visual studio code", "vscode", "pycharm", "python", "anaconda", "pgadmin", "postgres", "github", "git", "docker", "cursor", "ollama", "openai"]):
            return build_result(item, "代码项目", t("planner.reason.shortcut_dev"), "rule")
        if contains_any(text, ["chrome", "edge", "firefox", "wechat", "微信", "qq", "telegram", "discord", "teamspeak"]):
            return build_result(item, "浏览器通讯", t("planner.reason.shortcut_browser_comm"), "rule")
        if contains_any(text, ["wps", "office", "word", "excel", "powerpoint", "zoom", "teams", "腾讯会议"]):
            return build_result(item, "办公学习", t("planner.reason.shortcut_office_study"), "rule")
        if contains_any(text, ["obs", "bilibili", "哔哩哔哩", "music", "qq音乐", "剪映", "capcut", "player"]):
            return build_result(item, "影音娱乐", t("planner.reason.shortcut_media"), "rule")
        if contains_any(text, ["google drive", "onedrive", "百度网盘", "vpn", "letsvpn", "radmin"]):
            return build_result(item, "网盘VPN", t("planner.reason.shortcut_cloud_vpn"), "rule")
        if contains_any(text, ["aida64", "crystaldisk", "ryzen master", "火绒", "geek", "everything", "control panel"]):
            return build_result(item, "系统工具", t("planner.reason.shortcut_system"), "rule")
        return None

    if item_type == "file":
        if suffix in VIDEO_AUDIO_EXTS:
            return build_result(item, "视频音频", t("planner.reason.file_video_audio"), "rule")
        if suffix in ARCHIVE_EXTS:
            return build_result(item, "压缩包", t("planner.reason.file_archive"), "rule")
        if suffix in INSTALLER_EXTS:
            return build_result(item, "安装包", t("planner.reason.file_installer"), "rule")
        if suffix in CODE_EXTS:
            return build_result(item, "代码项目", t("planner.reason.file_code"), "rule")

        if contains_any(text, ["assignment", "assign", "report", "essay", "paper", "submission", "final report", "作业", "报告", "论文", "查重", "降重"]):
            return build_result(item, "作业报告", t("planner.reason.file_assignment"), "rule_content")
        if contains_any(text, ["comp", "info", "stat", "infs", "5003", "5339", "9001", "9120", "9123", "5990", "5992", "6007", "5310", "5318", "lecture", "tutorial", "cheatsheet", "exam", "mock", "课程", "课件", "复习"]):
            return build_result(item, "课程资料", t("planner.reason.file_course"), "rule_content")
        if contains_any(text, ["resume", "cv", "cover letter", "简历", "求职", "实习"]):
            return build_result(item, "简历求职", t("planner.reason.file_resume"), "rule_content")
        if contains_any(text, ["passport", "visa", "certificate", "驾驶证", "行驶证", "不动产", "单身声明", "合同", "账单", "税", "退税", "bond", "receipt", "invoice"]):
            return build_result(item, "证件合同", t("planner.reason.file_certificate"), "rule_content")
        if suffix in IMAGE_EXTS:
            return build_result(item, "图片截图", t("planner.reason.file_image"), "rule")
        if contains_any(text, ["新建", "untitled", "未命名", "111111", "1212"]):
            return build_result(item, "临时文件", t("planner.reason.file_temporary"), "rule")
        return None

    if item_type == "folder":
        if contains_any(text, ["openai", "ollama", "agent", "api", "code", "github", "python", "package.json", "requirements.txt", "pyproject.toml", "readme.md", ".py", ".js", ".ts", ".java", ".sql"]):
            return build_result(item, "代码项目", t("planner.reason.folder_code"), "rule_folder_content")
        if contains_any(text, ["comp", "info", "stat", "infs", "5003", "5339", "9001", "9120", "9123", "5990", "5992", "6007", "5310", "5318", "lecture", "tutorial", "exam", "课程", "课件"]):
            return build_result(item, "课程资料", t("planner.reason.folder_course"), "rule_folder_content")
        if contains_any(text, ["assignment", "report", "essay", "作业", "报告", "论文"]):
            return build_result(item, "作业报告", t("planner.reason.folder_assignment"), "rule_folder_content")
        if contains_any(text, ["setup", "installer", "win-x64", "win-x86", "x86_64", "安装"]):
            return build_result(item, "安装包", t("planner.reason.folder_installer"), "rule")
        return None

    return None


def hybrid_preclassify_items(items):
    classified = []
    need_llm = []

    for item in items:
        memory_result = memory_classify_item(item)
        if memory_result:
            if item.get("source_id"):
                memory_result["source_id"] = item["source_id"]
            classified.append(memory_result)
            continue

        rule_result = rule_classify_item(item)
        if rule_result:
            classified.append(rule_result)
            continue

        need_llm.append(item)

    return classified, need_llm


def chunk_list(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _build_strategy_summary(plan: dict, observation: dict, user_intent: str) -> str:
    """Call LLM to generate a 2-4 sentence natural-language strategy description."""
    try:
        config = load_config()
        provider = config.get("llm_provider", "none").lower().strip()
        if provider == "none":
            return ""

        items = plan.get("items", [])
        sources_scanned = observation.get("sources_scanned", ["desktop"])

        from collections import Counter
        category_counts = Counter(i.get("category", "无法判断") for i in items)
        uncertain = [i for i in items if i.get("category") in ("无法判断", "其他快捷方式")]

        summary_data = {
            "来源": sources_scanned,
            "总计": len(items),
            "类别分布": dict(category_counts.most_common(8)),
            "不确定项目数": len(uncertain),
            "用户意图": user_intent or "未指定",
        }

        prompt = f"""你是文件整理助手。以下是本次整理的分类结果摘要，请用2-4句中文自然语言描述：
- 整理了哪些来源
- 主要分成了哪些类别
- 有哪些项目不确定（无法判断分类的）
- 有什么需要用户注意的地方
不要列举具体文件名，只说整体策略。

数据：
{json.dumps(summary_data, ensure_ascii=False, indent=2)}"""

        import requests, os, time
        if provider == "openai_compatible":
            api_base_url = config.get("api_base_url", "").strip()
            api_model = config.get("api_model", "").strip()
            api_key = os.environ.get("DESKTOP_AGENT_API_KEY", "").strip() or config.get("api_key", "").strip()
            if not (api_base_url and api_model and api_key):
                return ""
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            payload = {
                "model": api_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
                "stream": False,
            }
            resp = requests.post(api_base_url, headers=headers, json=payload, timeout=(10, 60))
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        elif provider == "ollama":
            payload = {
                "model": config.get("model", "qwen2.5-coder:14b"),
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 300, "temperature": 0.3},
            }
            resp = requests.post(config.get("ollama_url", "http://localhost:11434/api/generate"), json=payload, timeout=(10, 60))
            resp.raise_for_status()
            return resp.json()["response"].strip()

        elif provider == "builtin":
            from desktop_agent.builtin_llm import ensure_builtin_server_running
            chat_url = ensure_builtin_server_running()
            api_model = config.get("builtin_api_model", "builtin-model")
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": api_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
                "stream": False,
            }
            resp = requests.post(chat_url, headers=headers, json=payload, timeout=(10, 120))
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    except Exception:
        pass
    return ""


def preview_plan(user_intent: str = "", source_context: str = ""):
    if not require_file(OBSERVATION_FILE, "python desktop_agent_cli.py scan"):
        return

    config = load_config()
    provider = config.get("llm_provider", "none").lower().strip()

    observation = load_json(OBSERVATION_FILE)
    items = observation["items"]

    print("=" * 80)
    print(t("planner.header"))
    print("=" * 80)
    print(t("planner.strategy"))
    print(t("planner.provider", provider=provider))

    if user_intent:
        print(t("planner.intent_label", intent=user_intent, default=f"整理意图：{user_intent}"))

    sources_scanned = observation.get("sources_scanned", ["desktop"])
    if len(sources_scanned) > 1 or source_context:
        label = source_context or "、".join(sources_scanned)
        print(t("planner.sources_label", sources=label, default=f"扫描来源：{label}"))

    memory_rule_results, need_llm_items = hybrid_preclassify_items(items)

    print("")
    print(t("planner.preclassified", count=len(memory_rule_results)))
    print(t("planner.need_llm", count=len(need_llm_items)))

    plan = {
        "created_at": now_str(),
        "source_observation": OBSERVATION_FILE,
        "strategy": "memory_rule_content_llm_provider_hybrid",
        "llm_provider": provider,
        "user_intent": user_intent,
        "sources_scanned": sources_scanned,
        "items": [],
    }

    for item in memory_rule_results:
        plan["items"].append(item)

    save_json(PLAN_FILE, plan)

    if need_llm_items:
        if provider == "none":
            print("")
            print(t("planner.provider_none_skip"))
            print(t("planner.provider_none_fallback", count=len(need_llm_items)))

        batches = list(chunk_list(need_llm_items, config.get("batch_size", 8)))
        total_batches = len(batches)

        for batch_index, batch in enumerate(batches, start=1):
            print("")
            print(t("planner.batch_processing", index=batch_index, total=total_batches, count=len(batch)))

            try:
                results = classify_with_llm_provider(batch, batch_index, total_batches, user_intent=user_intent)
                for item in results:
                    plan["items"].append(item)
                save_json(PLAN_FILE, plan)
                print(t("planner.batch_done"))
            except Exception as exc:
                print(t("planner.batch_failed", error=exc))
                for item in batch:
                    category = "其他快捷方式" if item["type"] == "shortcut" else "无法判断"
                    result = {
                        "path": item["path"],
                        "name": item["name"],
                        "type": item["type"],
                        "category": category,
                        "reason": t("planner.reason.provider_failed", error=exc),
                        "classified_by": "provider_failed",
                    }
                    if item.get("source_id"):
                        result["source_id"] = item["source_id"]
                    plan["items"].append(result)
                save_json(PLAN_FILE, plan)

    print("")
    print(t("planner.plan_saved", path=PLAN_FILE))
    print(t("planner.final_count", count=len(plan["items"])))

    update_state(
        "last_preview_at",
        t("planner.state_done", count=len(plan["items"]), provider=provider),
    )

    # Generate strategy summary (non-blocking, best-effort)
    strategy_summary = _build_strategy_summary(plan, observation, user_intent)
    if strategy_summary:
        plan["strategy_summary"] = strategy_summary
        save_json(PLAN_FILE, plan)
        print("")
        print(t("planner.strategy_summary_label", default="── AI策略摘要 ──"))
        print(strategy_summary)

    explain_current_plan()
