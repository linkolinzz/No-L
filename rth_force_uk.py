# pyright: reportMissingImports=false
# rth_force_uk.py — PyInstaller runtime hook
# Форсуємо українську локаль ДО будь-яких імпортів і підміняємо поширені i18n.

import os, sys, locale, importlib, importlib.util
from pathlib import Path
from datetime import datetime

def _log(msg: str):
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        logdir = base / "MPI Agro"
        logdir.mkdir(parents=True, exist_ok=True)
        (logdir / "lang_hook.log").write_text(
            f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n",
            encoding="utf-8"
        )
    except Exception:
        pass

# 1) Оточення тільки українське
os.environ.update({
    "APP_LANG": "uk",
    "LANG": "uk",
    "LANGUAGE": "uk",
    "LC_ALL": "uk_UA",
    "LC_MESSAGES": "uk_UA",
    "BABEL_DEFAULT_LOCALE": "uk",
    "QT_LANGUAGE": "uk",
})

# 2) Системна локаль
try:
    try:
        locale.setlocale(locale.LC_ALL, "uk_UA")
    except Exception:
        pass
except Exception:
    pass

# 3) Патч gettext: будь-які запити локалей -> fallback на 'uk'
try:
    import gettext  # stdlib
    _orig_translation = gettext.translation

    def _safe_translation(domain, localedir=None, languages=None, *a, **kw):
        # ігноруємо те, що передали; завжди пробуємо 'uk' з fallback
        try:
            return _orig_translation(domain, localedir, languages=["uk"], fallback=True)
        except Exception:
            return gettext.NullTranslations()

    gettext.translation = _safe_translation  # type: ignore[attr-defined]
except Exception:
    pass

# 4) Якщо є Babel — змушуємо Locale.parse завжди повертати 'uk'
try:
    if importlib.util.find_spec("babel.core") is not None:
        babel_core = importlib.import_module("babel.core")
        Locale = babel_core.Locale

        def _safe_parse(_value, *a, **k):
            try:
                return Locale.parse("uk", *a, **k)
            except Exception:
                return Locale("uk")

        babel_core.Locale.parse = staticmethod(_safe_parse)  # type: ignore[attr-defined]
except Exception:
    pass

# 5) Якщо є langcodes — теж форсимо 'uk'
try:
    if importlib.util.find_spec("langcodes") is not None:
        lc = importlib.import_module("langcodes")
        def _closest_supported_match(*a, **k): return "uk"
        lc.closest_supported_match = _closest_supported_match  # type: ignore[attr-defined]
except Exception:
    pass

# 6) Логування для діагностики
try:
    env_snapshot = {k: os.environ.get(k, "") for k in ("APP_LANG","LANG","LANGUAGE","LC_ALL","LC_MESSAGES")}
    _log(f"hook ok | env={env_snapshot} | exe={'(frozen)' if getattr(sys,'frozen',False) else 'script'}")
except Exception:
    pass
