from __future__ import annotations

import builtins
import json
from pathlib import Path
from tkinter import messagebox

from desktop_agent.categories import CATEGORIES


DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES = ("zh", "en")
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_current_language = DEFAULT_LANGUAGE
_original_print = builtins.print
_original_messagebox = {}
_ctk_patched = False
_runtime_patched = False


def _load_locale(language: str) -> dict:
    path = LOCALES_DIR / f"{language}.json"
    if not path.exists():
        return {"translations": {}, "categories": {}, "substrings": {}}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "translations": data.get("translations", {}),
        "categories": data.get("categories", {}),
        "substrings": data.get("substrings", {}),
    }


def _load_locales():
    locales = {}
    for language in SUPPORTED_LANGUAGES:
        locales[language] = _load_locale(language)
    return locales


LOCALES = _load_locales()


def reload_locales():
    global LOCALES
    LOCALES = _load_locales()


def _get_bucket(bucket: str, language: str):
    return LOCALES.get(language, {}).get(bucket, {})


def _lookup(bucket: str, key: str, language: str):
    return _get_bucket(bucket, language).get(key)


def _lookup_with_fallback(bucket: str, key: str):
    value = _lookup(bucket, key, _current_language)
    if value is not None:
        return value
    value = _lookup(bucket, key, DEFAULT_LANGUAGE)
    if value is not None:
        return value
    return key


def set_language(language: str | None):
    global _current_language
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    _current_language = language


def get_language() -> str:
    return _current_language


def is_english() -> bool:
    return _current_language == "en"


def t(key: str, default: str | None = None, **kwargs):
    text = _lookup_with_fallback("translations", key)
    if text == key and default is not None:
        text = default

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def translate_text(text):
    if text is None or not isinstance(text, str):
        return text
    if _current_language == "zh":
        return text

    exact = (
        _lookup("translations", text, "en")
        or _lookup("categories", text, "en")
        or _lookup("substrings", text, "en")
    )
    if exact:
        return exact

    translated = text
    for bucket_name in ("translations", "categories", "substrings"):
        bucket = _get_bucket(bucket_name, "en")
        for key in sorted(bucket, key=len, reverse=True):
            translated = translated.replace(key, bucket[key])
    return translated


def get_category_display(category: str) -> str:
    return _lookup_with_fallback("categories", category)


def get_display_to_category_map(categories=None):
    categories = categories or CATEGORIES
    return {get_category_display(category): category for category in categories}


def get_category_display_options(categories=None):
    categories = categories or CATEGORIES
    return [get_category_display(category) for category in categories]


def get_language_label(language: str) -> str:
    return "English" if language == "en" else "中文"


def get_language_by_label(label: str) -> str:
    return "en" if label == "English" else "zh"


def _wrap_messagebox(name):
    original = getattr(messagebox, name)
    _original_messagebox[name] = original

    def wrapper(title, message=None, *args, **kwargs):
        translated_title = translate_text(title)
        translated_message = translate_text(message) if isinstance(message, str) else message
        return original(translated_title, translated_message, *args, **kwargs)

    setattr(messagebox, name, wrapper)


def patch_messageboxes():
    if _original_messagebox:
        return
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askyesnocancel", "askokcancel"):
        if hasattr(messagebox, name):
            _wrap_messagebox(name)


def patch_customtkinter(ctk):
    global _ctk_patched
    if _ctk_patched:
        return

    def wrap_widget_text(widget_cls):
        original_init = widget_cls.__init__

        def patched_init(self, *args, **kwargs):
            if "text" in kwargs:
                kwargs["text"] = translate_text(kwargs["text"])
            original_init(self, *args, **kwargs)

        widget_cls.__init__ = patched_init

    for cls_name in ("CTkLabel", "CTkButton", "CTkCheckBox", "CTkRadioButton", "CTkSwitch"):
        if hasattr(ctk, cls_name):
            wrap_widget_text(getattr(ctk, cls_name))

    _ctk_patched = True


def install_runtime_output_translation():
    global _runtime_patched
    if _runtime_patched:
        return

    def translated_print(*args, **kwargs):
        if _current_language == "zh":
            return _original_print(*args, **kwargs)
        translated_args = [translate_text(arg) if isinstance(arg, str) else arg for arg in args]
        return _original_print(*translated_args, **kwargs)

    builtins.print = translated_print
    patch_messageboxes()
    _runtime_patched = True
