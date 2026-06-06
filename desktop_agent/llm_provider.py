# desktop_agent/llm_provider.py

import os
import json
import time
import requests

from desktop_agent.categories import CATEGORIES
from desktop_agent.config import load_config
from desktop_agent.memory import load_memory
from desktop_agent.builtin_llm import ensure_builtin_server_running


def clean_json_output(content: str):
    content = content.strip()
    content = content.replace("```json", "")
    content = content.replace("```python", "")
    content = content.replace("```", "")
    content = content.strip()

    start = content.find("[")
    end = content.rfind("]")

    if start != -1 and end != -1 and end > start:
        content = content[start:end + 1]

    return content


def build_classification_prompt(batch, batch_index, total_batches):
    memory = load_memory()

    prompt = f"""You are a desktop file-organizing assistant. / 你是一个桌面文件整理助手。
Classify each top-level desktop item into exactly ONE category.
为每个桌面第一层项目选择且仅选择一个类别。

Item types / 三种 type:
1. file  - a normal file, may include content_summary. 普通文件，可能含 content_summary。
2. folder - a top-level desktop folder, may include folder_summary. 桌面第一层文件夹，可能含 folder_summary。
3. shortcut - a desktop shortcut; judge by its name. 快捷方式，按名称判断软件类别。

Allowed categories (use the exact text) / 只能使用以下类别（原样使用）：
{", ".join(CATEGORIES)}

Rules / 规则：
- Only classify the given top-level items; do NOT classify files inside folders.
  只分类给定的第一层项目，不要把文件夹内部文件单独分类。
- "path" MUST match the input exactly; never invent or rename. path 必须与输入完全一致，不要编造或改名。
- "category" MUST be one of the allowed categories above. category 必须是上面类别之一。
- Respect the user's long-term memory below; it takes priority. 优先遵循下面的用户长期记忆。
- If unsure, use "无法判断" (or "其他快捷方式" for shortcuts). 不确定时用“无法判断”（快捷方式用“其他快捷方式”）。
- Output a STRICT JSON array only. No Markdown, no comments, no extra text.
  只输出严格的 JSON 数组，不要 Markdown、不要解释、不要多余文字。

User long-term memory / 用户长期记忆：
{json.dumps(memory, ensure_ascii=False, indent=2)}

Each element format / 每个元素格式：
{{
  "path": "original path / 原始路径",
  "name": "original name / 原始名称",
  "type": "file / folder / shortcut",
  "category": "one allowed category / 类别之一",
  "reason": "short reason / 简短原因"
}}

Batch {batch_index}/{total_batches}. / 这是第 {batch_index}/{total_batches} 批。
Items to classify / 需要分类的桌面项目：
{json.dumps(batch, ensure_ascii=False, indent=2)}
"""
    return prompt.strip()


def fallback_without_llm(item, reason):
    if item["type"] == "shortcut":
        category = "其他快捷方式"
    else:
        category = "无法判断"

    return {
        "path": item["path"],
        "name": item["name"],
        "type": item["type"],
        "category": category,
        "reason": reason,
        "classified_by": "no_llm"
    }


def normalize_model_results(raw_results, batch, classified_by):
    final_results = []
    input_map = {item["path"]: item for item in batch}

    for r in raw_results:
        original = input_map.get(r.get("path"))

        if original is None:
            continue

        category = r.get("category", "无法判断")
        if category not in CATEGORIES:
            category = "无法判断"

        final_results.append({
            "path": original["path"],
            "name": original["name"],
            "type": original["type"],
            "category": category,
            "reason": r.get("reason", ""),
            "classified_by": classified_by
        })

    existing_paths = {x["path"] for x in final_results}

    for item in batch:
        if item["path"] not in existing_paths:
            final_results.append(
                fallback_without_llm(
                    item,
                    f"{classified_by} 没有返回该项目，自动归入兜底分类"
                )
            )

    return final_results


def classify_none(batch, batch_index, total_batches):
    return [
        fallback_without_llm(
            item,
            "当前为无模型模式，Memory/Rule 无法判断，等待人工审核"
        )
        for item in batch
    ]


def classify_ollama(batch, batch_index, total_batches):
    config = load_config()
    prompt = "/no_think\n" + build_classification_prompt(batch, batch_index, total_batches)

    payload = {
        "model": config.get("model", "qwen2.5-coder:14b"),
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 8192,
            "num_predict": 2500,
            "temperature": 0.1
        }
    }

    response = requests.post(
        config.get("ollama_url", "http://localhost:11434/api/generate"),
        json=payload,
        timeout=(10, None)
    )

    response.raise_for_status()

    content = response.json()["response"]
    content = clean_json_output(content)
    raw_results = json.loads(content)

    return normalize_model_results(raw_results, batch, "llm_ollama")


def _post_with_retry(url, headers, payload, timeout, retries=4, backoff=3):
    """
    POST 请求，对 503（服务暂时不可用 / 模型正在加载）与连接错误自动重试。
    主要用于 builtin 本地模型刚就绪时的短暂窗口，也兼顾云端 API 偶发 503。
    """
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)

            if response.status_code == 503 and attempt < retries:
                last_error = requests.HTTPError(
                    f"503 Service Unavailable（第 {attempt}/{retries} 次，{backoff}s 后重试）",
                    response=response,
                )
                time.sleep(backoff)
                continue

            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
            if attempt < retries:
                time.sleep(backoff)
                continue

    if last_error is not None:
        raise last_error

    raise RuntimeError("请求失败：未知错误")


def call_openai_compatible_api(api_base_url, api_model, api_key, batch, batch_index, total_batches, classified_by):
    prompt = build_classification_prompt(batch, batch_index, total_batches)

    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": api_model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个严格输出 JSON 数组的桌面文件分类 Agent。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2500,
        "stream": False
    }

    response = _post_with_retry(
        api_base_url,
        headers=headers,
        payload=payload,
        timeout=(10, 180),
    )

    response.raise_for_status()
    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise ValueError(f"API 返回格式不符合 OpenAI-compatible chat/completions：{e}")

    content = clean_json_output(content)
    raw_results = json.loads(content)

    return normalize_model_results(raw_results, batch, classified_by)


def classify_openai_compatible(batch, batch_index, total_batches):
    config = load_config()

    api_base_url = config.get("api_base_url", "").strip()
    api_model = config.get("api_model", "").strip()
    api_key = (
        os.environ.get("DESKTOP_AGENT_API_KEY", "").strip()
        or config.get("api_key", "").strip()
    )

    if not api_base_url:
        raise ValueError("api_base_url 为空，请在 Config 中填写 API 地址")

    if not api_model:
        raise ValueError("api_model 为空，请在 Config 中填写模型名称")

    if not api_key:
        raise ValueError("api_key 为空，请在 Config 中填写 API Key，或设置环境变量 DESKTOP_AGENT_API_KEY")

    return call_openai_compatible_api(
        api_base_url=api_base_url,
        api_model=api_model,
        api_key=api_key,
        batch=batch,
        batch_index=batch_index,
        total_batches=total_batches,
        classified_by="llm_openai_compatible"
    )


def classify_builtin(batch, batch_index, total_batches):
    """
    使用内置 llama-server + GGUF 小模型。
    llama-server 提供 OpenAI-compatible /v1/chat/completions。
    """
    chat_url = ensure_builtin_server_running()

    config = load_config()
    api_model = config.get("builtin_api_model", "builtin-model")

    return call_openai_compatible_api(
        api_base_url=chat_url,
        api_model=api_model,
        api_key="",
        batch=batch,
        batch_index=batch_index,
        total_batches=total_batches,
        classified_by="llm_builtin"
    )


def classify_with_llm_provider(batch, batch_index, total_batches):
    config = load_config()
    provider = config.get("llm_provider", "none").lower().strip()

    if provider == "none":
        return classify_none(batch, batch_index, total_batches)

    if provider == "ollama":
        return classify_ollama(batch, batch_index, total_batches)

    if provider == "openai_compatible":
        return classify_openai_compatible(batch, batch_index, total_batches)

    if provider == "builtin":
        return classify_builtin(batch, batch_index, total_batches)

    return [
        fallback_without_llm(
            item,
            f"未知 llm_provider={provider}，按无模型模式处理"
        )
        for item in batch
    ]