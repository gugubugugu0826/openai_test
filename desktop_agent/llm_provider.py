import json
import os
import time

import requests

from desktop_agent.builtin_llm import ensure_builtin_server_running
from desktop_agent.categories import CATEGORIES
from desktop_agent.config import load_config
from desktop_agent.i18n import t
from desktop_agent.memory import load_memory


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
    prompt = f"""You are a desktop file-organizing assistant.
Classify each top-level desktop item into exactly ONE category.

Item types:
1. file - a normal file, may include content_summary
2. folder - a top-level desktop folder, may include folder_summary
3. shortcut - a desktop shortcut; judge by its name

Allowed categories (use the exact text):
{", ".join(CATEGORIES)}

Rules:
- Only classify the given top-level items; do NOT classify files inside folders.
- "path" MUST match the input exactly; never invent or rename.
- "category" MUST be one of the allowed categories above.
- Respect the user's long-term memory below; it takes priority.
- If unsure, use "无法判断" (or "其他快捷方式" for shortcuts).
- Output a STRICT JSON array only. No Markdown, no comments, no extra text.

User long-term memory:
{json.dumps(memory, ensure_ascii=False, indent=2)}

Each element format:
{{
  "path": "original path",
  "name": "original name",
  "type": "file / folder / shortcut",
  "category": "one allowed category",
  "reason": "short reason"
}}

Batch {batch_index}/{total_batches}
Items to classify:
{json.dumps(batch, ensure_ascii=False, indent=2)}
"""
    return prompt.strip()


def fallback_without_llm(item, reason):
    category = "其他快捷方式" if item["type"] == "shortcut" else "无法判断"
    result = {
        "path": item["path"],
        "name": item["name"],
        "type": item["type"],
        "category": category,
        "reason": reason,
        "classified_by": "no_llm",
    }
    if item.get("desktop_root"):
        result["desktop_root"] = item["desktop_root"]
    return result


def normalize_model_results(raw_results, batch, classified_by):
    final_results = []
    input_map = {item["path"]: item for item in batch}

    for result in raw_results:
        original = input_map.get(result.get("path"))
        if original is None:
            continue

        category = result.get("category", "无法判断")
        if category not in CATEGORIES:
            category = "无法判断"

        item = {
            "path": original["path"],
            "name": original["name"],
            "type": original["type"],
            "category": category,
            "reason": result.get("reason", ""),
            "classified_by": classified_by,
        }
        if original.get("desktop_root"):
            item["desktop_root"] = original["desktop_root"]
        final_results.append(item)

    existing_paths = {item["path"] for item in final_results}
    for item in batch:
        if item["path"] not in existing_paths:
            final_results.append(
                fallback_without_llm(item, t("llm_provider.missing_result_fallback", provider=classified_by))
            )
    return final_results


def classify_none(batch, batch_index, total_batches):
    return [
        fallback_without_llm(item, t("llm_provider.none_mode_reason"))
        for item in batch
    ]


def classify_ollama(batch, batch_index, total_batches):
    config = load_config()
    prompt = "/no_think\n" + build_classification_prompt(batch, batch_index, total_batches)
    payload = {
        "model": config.get("model", "qwen2.5-coder:14b"),
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 8192, "num_predict": 2500, "temperature": 0.1},
    }

    response = requests.post(
        config.get("ollama_url", "http://localhost:11434/api/generate"),
        json=payload,
        timeout=(10, None),
    )
    response.raise_for_status()

    content = response.json()["response"]
    raw_results = json.loads(clean_json_output(content))
    return normalize_model_results(raw_results, batch, "llm_ollama")


def _post_with_retry(url, headers, payload, timeout, retries=4, backoff=3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 503 and attempt < retries:
                last_error = requests.HTTPError(
                    t("llm_provider.retry_503", attempt=attempt, retries=retries, backoff=backoff),
                    response=response,
                )
                time.sleep(backoff)
                continue
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff)
                continue

    if last_error is not None:
        raise last_error
    raise RuntimeError(t("llm_provider.request_failed"))


def call_openai_compatible_api(api_base_url, api_model, api_key, batch, batch_index, total_batches, classified_by):
    prompt = build_classification_prompt(batch, batch_index, total_batches)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": api_model,
        "messages": [
            {"role": "system", "content": "You are a desktop file classification assistant that must return a strict JSON array only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2500,
        "stream": False,
    }

    response = _post_with_retry(api_base_url, headers=headers, payload=payload, timeout=(10, 180))
    response.raise_for_status()
    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise ValueError(t("llm_provider.bad_chat_response", error=exc))

    raw_results = json.loads(clean_json_output(content))
    return normalize_model_results(raw_results, batch, classified_by)


def classify_openai_compatible(batch, batch_index, total_batches):
    config = load_config()
    api_base_url = config.get("api_base_url", "").strip()
    api_model = config.get("api_model", "").strip()
    api_key = os.environ.get("DESKTOP_AGENT_API_KEY", "").strip() or config.get("api_key", "").strip()

    if not api_base_url:
        raise ValueError(t("llm_provider.missing_api_base"))
    if not api_model:
        raise ValueError(t("llm_provider.missing_api_model"))
    if not api_key:
        raise ValueError(t("llm_provider.missing_api_key"))

    return call_openai_compatible_api(
        api_base_url=api_base_url,
        api_model=api_model,
        api_key=api_key,
        batch=batch,
        batch_index=batch_index,
        total_batches=total_batches,
        classified_by="llm_openai_compatible",
    )


def classify_builtin(batch, batch_index, total_batches):
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
        classified_by="llm_builtin",
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
        fallback_without_llm(item, t("llm_provider.unknown_provider_fallback", provider=provider))
        for item in batch
    ]
