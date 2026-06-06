# desktop_agent/planner.py

from desktop_agent.categories import CATEGORIES
from desktop_agent.config import load_config
from desktop_agent.storage import save_json, load_json
from desktop_agent.state import now_str, update_state, require_file
from desktop_agent.memory import memory_classify_item
from desktop_agent.scanner import OBSERVATION_FILE
from desktop_agent.llm_provider import classify_with_llm_provider
from desktop_agent.plan_explainer import explain_current_plan


PLAN_FILE = "desktop_agent_plan.json"


IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".heic"
}

VIDEO_AUDIO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac"
}

ARCHIVE_EXTS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"
}

INSTALLER_EXTS = {
    ".exe", ".msi", ".apk", ".dmg", ".pkg"
}

CODE_EXTS = {
    ".py", ".java", ".js", ".ts", ".html", ".css", ".cpp", ".c",
    ".cs", ".go", ".rs", ".php", ".rb", ".ipynb", ".sql",
    ".json", ".xml", ".yaml", ".yml", ".md", ".r", ".rmd", ".duckdb"
}


def contains_any(text, keywords):
    text = text.lower()
    return any(k.lower() in text for k in keywords)


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
    return {
        "path": item["path"],
        "name": item["name"],
        "type": item["type"],
        "category": category,
        "reason": reason,
        "classified_by": classified_by
    }


def rule_classify_item(item):
    name = item.get("name", "")
    suffix = item.get("suffix", "").lower()
    item_type = item.get("type", "file")
    text = item_search_text(item)

    if item_type == "shortcut":
        if contains_any(text, [
            "steam", "epic", "wegame", "hoyoplay", "genshin", "原神",
            "鸣潮", "apex", "minecraft", "stardew", "overcooked", "game"
        ]):
            return build_result(item, "游戏相关", "快捷方式名称明显属于游戏或游戏平台", "rule")

        if contains_any(text, [
            "visual studio code", "vscode", "pycharm", "python", "anaconda",
            "pgadmin", "postgres", "github", "git", "docker", "cursor", "ollama", "openai"
        ]):
            return build_result(item, "代码项目", "快捷方式名称明显属于开发工具", "rule")

        if contains_any(text, [
            "chrome", "edge", "firefox", "wechat", "微信", "qq", "telegram",
            "discord", "teamspeak"
        ]):
            return build_result(item, "浏览器通讯", "快捷方式名称明显属于浏览器或通讯软件", "rule")

        if contains_any(text, [
            "wps", "office", "word", "excel", "powerpoint", "zoom", "teams", "腾讯会议"
        ]):
            return build_result(item, "办公学习", "快捷方式名称明显属于办公/学习工具", "rule")

        if contains_any(text, [
            "obs", "bilibili", "哔哩哔哩", "music", "qq音乐", "剪映", "capcut", "player"
        ]):
            return build_result(item, "影音娱乐", "快捷方式名称明显属于影音娱乐工具", "rule")

        if contains_any(text, [
            "google drive", "onedrive", "百度网盘", "vpn", "letsvpn", "radmin"
        ]):
            return build_result(item, "网盘VPN", "快捷方式名称明显属于网盘/VPN/远程连接", "rule")

        if contains_any(text, [
            "aida64", "crystaldisk", "ryzen master", "火绒", "geek", "everything", "control panel"
        ]):
            return build_result(item, "系统工具", "快捷方式名称明显属于系统工具", "rule")

        return None

    if item_type == "file":
        if contains_any(text, [
            "assignment", "assign", "a1", "a2", "report", "essay", "paper",
            "submission", "final report", "作业", "报告", "论文", "查重", "降重"
        ]):
            return build_result(item, "作业报告", "文件名或内容摘要包含作业/报告关键词", "rule_content")

        if contains_any(text, [
            "comp", "info", "stat", "infs", "5003", "5339", "9001", "9120",
            "9123", "5990", "5992", "6007", "5310", "5318", "lecture",
            "tutorial", "cheatsheet", "exam", "mock", "课程", "课件", "复习"
        ]):
            return build_result(item, "课程资料", "文件名或内容摘要包含课程代码/课程关键词", "rule_content")

        if contains_any(text, ["resume", "cv", "cover letter", "简历", "求职", "实习"]):
            return build_result(item, "简历求职", "文件名或内容摘要包含简历/求职关键词", "rule_content")

        if contains_any(text, [
            "passport", "visa", "certificate", "驾驶证", "行驶证", "不动产",
            "单身声明", "合同", "账单", "税", "退税", "bond", "receipt", "invoice"
        ]):
            return build_result(item, "证件合同", "文件名或内容摘要包含证件/合同/账单关键词", "rule_content")

        if suffix in IMAGE_EXTS:
            return build_result(item, "图片截图", "图片文件后缀", "rule")

        if suffix in VIDEO_AUDIO_EXTS:
            return build_result(item, "视频音频", "视频/音频文件后缀", "rule")

        if suffix in ARCHIVE_EXTS:
            return build_result(item, "压缩包", "压缩包文件后缀", "rule")

        if suffix in INSTALLER_EXTS:
            return build_result(item, "安装包", "安装包文件后缀", "rule")

        if suffix in CODE_EXTS:
            return build_result(item, "代码项目", "代码/数据项目文件后缀", "rule")

        if contains_any(text, ["新建", "untitled", "未命名", "111111", "1212"]):
            return build_result(item, "临时文件", "文件名像临时文件", "rule")

        return None

    if item_type == "folder":
        if contains_any(text, [
            "openai", "ollama", "agent", "api", "code", "github", "python",
            "package.json", "requirements.txt", "pyproject.toml", "readme.md",
            ".py", ".js", ".ts", ".java", ".sql"
        ]):
            return build_result(item, "代码项目", "文件夹名或内部摘要明显属于代码/API/Agent 项目", "rule_folder_content")

        if contains_any(text, [
            "comp", "info", "stat", "infs", "5003", "5339", "9001", "9120",
            "9123", "5990", "5992", "6007", "5310", "5318", "lecture",
            "tutorial", "exam", "课程", "课件"
        ]):
            return build_result(item, "课程资料", "文件夹名或内部摘要包含课程代码/课程资料关键词", "rule_folder_content")

        if contains_any(text, [
            "assignment", "ass", "a1", "a2", "report", "essay", "作业", "报告", "论文"
        ]):
            return build_result(item, "作业报告", "文件夹名或内部摘要包含作业/报告关键词", "rule_folder_content")

        if contains_any(text, [
            "setup", "installer", "win-x64", "win-x86", "x86_64", "安装"
        ]):
            return build_result(item, "安装包", "文件夹名明显属于安装包或软件工具", "rule")

        return None

    return None


def hybrid_preclassify_items(items):
    classified = []
    need_llm = []

    for item in items:
        memory_result = memory_classify_item(item)
        if memory_result:
            classified.append(memory_result)
            continue

        rule_result = rule_classify_item(item)
        if rule_result:
            classified.append(rule_result)
            continue

        need_llm.append(item)

    return classified, need_llm


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def preview_plan():
    if not require_file(OBSERVATION_FILE, "python desktop_agent_cli.py scan"):
        return

    config = load_config()
    provider = config.get("llm_provider", "none").lower().strip()

    observation = load_json(OBSERVATION_FILE)
    items = observation["items"]

    print("=" * 80)
    print("Step 2 - Reasoning：Hybrid Agent 生成整理计划")
    print("=" * 80)
    print("策略：Memory 优先 → Rule/Content Summary 其次 → LLM 处理模糊项目")
    print(f"当前 LLM Provider：{provider}")

    memory_rule_results, need_llm_items = hybrid_preclassify_items(items)

    print(f"\nMemory/Rule/Content 已分类：{len(memory_rule_results)} 个")
    print(f"需要 LLM 判断：{len(need_llm_items)} 个")

    plan = {
        "created_at": now_str(),
        "source_observation": OBSERVATION_FILE,
        "strategy": "memory_rule_content_llm_provider_hybrid",
        "llm_provider": provider,
        "items": []
    }

    for item in memory_rule_results:
        plan["items"].append(item)

    save_json(PLAN_FILE, plan)

    if need_llm_items:
        if provider == "none":
            print("\n当前 llm_provider = none：跳过大模型判断。")
            print(f"模糊项目将自动归入 无法判断/其他快捷方式：{len(need_llm_items)} 个")

        batches = list(chunk_list(need_llm_items, config.get("batch_size", 8)))
        total_batches = len(batches)

        for index, batch in enumerate(batches, start=1):
            print(f"\nProvider 正在处理第 {index}/{total_batches} 批，共 {len(batch)} 个模糊项目...")

            try:
                results = classify_with_llm_provider(batch, index, total_batches)

                for item in results:
                    plan["items"].append(item)

                save_json(PLAN_FILE, plan)
                print("本批完成，计划已保存。")

            except Exception as e:
                print(f"本批 Provider 分类失败：{e}")

                for item in batch:
                    if item["type"] == "shortcut":
                        category = "其他快捷方式"
                    else:
                        category = "无法判断"

                    plan["items"].append({
                        "path": item["path"],
                        "name": item["name"],
                        "type": item["type"],
                        "category": category,
                        "reason": f"Provider 分类失败，自动归类：{e}",
                        "classified_by": "provider_failed"
                    })

                save_json(PLAN_FILE, plan)

    print(f"\n整理计划已生成：{PLAN_FILE}")
    print(f"最终计划项目数：{len(plan['items'])}")

    update_state(
        "last_preview_at",
        f"整理计划生成完成：{len(plan['items'])} 个项目，provider={provider}"
    )

    explain_current_plan()