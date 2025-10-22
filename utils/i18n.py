# utils/i18n.py
# Примусово тільки українська мова

import os, json
from pathlib import Path

ALIASES = {
    "uk": "uk", "ua": "uk", "ukr": "uk", "uk-ua": "uk",
    "eng": "uk", "en": "uk", "en-us": "uk", "en-gb": "uk",
    "ru": "uk", "rus": "uk", "ru-ru": "uk", "": "uk", None: "uk",
}

def _read_config_lang() -> str | None:
    p = Path(__file__).resolve().parent.parent / "config.json"
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return (data.get("language") or data.get("lang") or "").strip()
        except Exception:
            pass
    return None

def get_effective_lang() -> str:
    raw = os.getenv("APP_LANG") or _read_config_lang() or "uk"
    return ALIASES.get(raw.strip().lower(), "uk")

def force_env_uk():
    os.environ["APP_LANG"] = "uk"
    os.environ["LANG"] = "uk"
    os.environ["LANGUAGE"] = "uk"
    os.environ["LC_ALL"] = "uk_UA"
    os.environ["LC_MESSAGES"] = "uk_UA"

def set_page_locale_uk(page) -> None:
    try:
        page.locale = ("uk", "UA")  # Flet
    except Exception:
        pass
