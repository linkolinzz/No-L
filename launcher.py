# -*- coding: utf-8 -*-
# MPI Agro — Launcher + Main Menu (Flet) — refined

import os, sys, re, time, tempfile, hashlib, shutil, zipfile, threading, json, traceback, datetime, asyncio, calendar
import datetime as _dt
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
import flet as ft

# --- іконки для різних версій Flet ---
try:
    _ = ft.icons
except AttributeError:
    ft.icons = ft.Icons  # сумісність зі старими

# ========= PATHS / ENV / LOG =========
APP_DIR  = Path(__file__).resolve().parent
USER_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "MPI Agro"
ENV_PATH = USER_DIR / ".env"
LOG_PATH = USER_DIR / "launcher_errors.log"
NOTES_PATH = USER_DIR / "notes.json"
REMEMBER_PATH = USER_DIR / "remember.json"
USER_DIR.mkdir(parents=True, exist_ok=True)

def _log_exc(prefix: str, err: Exception):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now().isoformat()}] {prefix}: {err}\n")
            f.write(traceback.format_exc())
    except Exception:
        pass

def load_env():
    if not ENV_PATH.exists():
        ENV_PATH.write_text("APP_LANG=uk\r\nCLIENT_MODE=remote\r\nDISABLE_DIRECT_DB=1\r\n", encoding="utf-8")
    for raw in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))
load_env()

# ========= API/UPDATE =========
API_BASE = (os.getenv("API_BASE") or os.getenv("API_URL") or "https://api.mpi-ringroup.pp.ua").rstrip("/")
HEALTH_URL = f"{API_BASE}/health"
UPDATE_API = os.getenv("UPDATE_API", f"{API_BASE}/updates/latest")
UPDATE_TOKEN = (os.getenv("UPDATE_TOKEN") or "").strip()
DISABLE_UPDATES = (os.getenv("DISABLE_UPDATES", "0").lower() in ("1", "true", "yes"))
SERVER_POLL_SEC = int(os.getenv("SERVER_POLL_SEC", "20"))

def RES(*parts: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return str(base.joinpath(*parts))

def read_local_version(default="1.0.0") -> str:
    p = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR) / "version.txt"
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip() or default
    except Exception:
        pass
    return default

LOCAL_VERSION = read_local_version()

def write_version_file(version: str):
    try:
        p = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR) / "version.txt"
        p.write_text(version.strip(), encoding="utf-8")
    except Exception:
        pass

def apply_update_zip(zip_path: str, target_dir: str):
    td = Path(target_dir); td.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpi_agro_update_") as tmpdir:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        for root, _, files in os.walk(tmpdir):
            rel = os.path.relpath(root, tmpdir)
            dst_root = td / rel if rel != "." else td
            dst_root.mkdir(parents=True, exist_ok=True)
            for f in files:
                src_f = Path(root) / f
                dst_f = dst_root / f
                tmp_target = Path(str(dst_f) + ".updtmp")
                if tmp_target.exists():
                    tmp_target.unlink()
                shutil.copy2(src_f, tmp_target)
                try:
                    os.replace(tmp_target, dst_f)
                except PermissionError:
                    try: dst_f.unlink()
                    except Exception: pass
                    os.replace(tmp_target, dst_f)

# ========= API HELPERS =========
def api_login(api_base: str, username: str, password: str, timeout=10) -> Optional[str]:
    try:
        r = requests.post(api_base + "/auth/login", json={"username": username, "password": password}, timeout=timeout)
        if r.status_code == 200:
            return (r.json() or {}).get("access_token")
    except Exception as e:
        _log_exc("api_login", e)
    return None

def api_me(api_base: str, token: str, timeout=8) -> Optional[dict]:
    if not token: return None
    try:
        r = requests.get(api_base + "/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        _log_exc("api_me", e)
    return None

def parse_health(resp: requests.Response) -> Dict[str, Any]:
    try:
        d = resp.json()
        ok = bool(d.get("ok") or str(d.get("status", "")).lower() == "ok")
        ver = str(d.get("version") or d.get("app_version") or d.get("ver") or "")
        return {"ok": ok, "version": ver}
    except Exception:
        t = (resp.text or "").lower()
        ok = ("\"ok\":true" in t) or (re.search(r"\bok\b", t) is not None)
        m = re.search(r"\b\d+\.\d+\.\d+\b", t)
        return {"ok": ok, "version": m.group(0) if m else ""}

# ========= UI HELPERS =========
FIELD_WIDTH = 360
def make_tf(label, hint, password=False, autofocus=False):
    return ft.TextField(
        label=label,
        hint_text=hint,
        width=FIELD_WIDTH,
        border_color="#6ee7ff",
        focused_border_color="#38bdf8",
        color="#e2e8eb",
        label_style=ft.TextStyle(size=14, color="#93c5fd"),
        hint_style=ft.TextStyle(size=13, color="#94a3b8"),
        text_style=ft.TextStyle(size=15),
        password=password,
        can_reveal_password=bool(password),
        autofocus=autofocus,
    )

def safe_img(src: str, *, width=96, height=96):
    p = RES(src)
    try:
        if Path(p).exists():
            return ft.Image(src=p, width=width, height=height, fit=ft.ImageFit.CONTAIN)
    except Exception:
        pass
    return ft.Icon(ft.icons.INSERT_DRIVE_FILE, size=int(max(width, height)*0.8), color="#9ca3af")

# ========= NOTES — LOCAL JSON =========
def _load_notes_local() -> List[dict]:
    try:
        if NOTES_PATH.exists():
            return json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _log_exc("load_notes_local", e)
    return []

def _save_notes_local(rows: List[dict]):
    try:
        NOTES_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _log_exc("save_notes_local", e)

def _local_add(date_iso: str, text: str, note_id: Optional[int] = None):
    rows = _load_notes_local()
    rows.append({"id": note_id, "date": date_iso, "text": text, "last_notified": None})
    _save_notes_local(rows)

def _local_update(note_id: Optional[int], text: str):
    rows = _load_notes_local(); changed = False
    for r in rows:
        if r.get("id") == note_id:
            r["text"] = text; changed = True
    if changed: _save_notes_local(rows)

def _local_delete(note_id: Optional[int]):
    rows = [r for r in _load_notes_local() if r.get("id") != note_id]
    _save_notes_local(rows)

def _notes_for_local(date_iso: str) -> List[dict]:
    return [r for r in _load_notes_local() if r.get("date") == date_iso]

def _dates_with_notes_local(year: int, month: int) -> set[str]:
    prefix = f"{year:04d}-{month:02d}-"
    return {r["date"] for r in _load_notes_local()
            if isinstance(r.get("date"), str) and r["date"].startswith(prefix)}

def _mark_notified_today_local(date_iso: str):
    rows = _load_notes_local()
    today = _dt.date.today().isoformat()
    changed = False
    for r in rows:
        if r.get("date") == date_iso:
            r["last_notified"] = today; changed = True
    if changed: _save_notes_local(rows)

# ========= NOTES — DB (fallback) =========
DB_AVAILABLE = False
PARAM_STYLE = "%s"

try:
    from database.db_manager import connect_db, db_fetch, db_exec
    from database.bootstrap import ensure_schema
    ensure_schema()
    DB_AVAILABLE = True
except Exception:
    def connect_db(): raise RuntimeError("DB unavailable")
    def db_fetch(*a, **k): return []
    def db_exec(*a, **k):  return 0
    DB_AVAILABLE = False

def _ensure_notes_table():
    global DB_AVAILABLE
    if not DB_AVAILABLE: return
    try:
        db_exec("""
            CREATE TABLE IF NOT EXISTS calendar_notes(
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                date DATE NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        try:
            db_exec("""
                CREATE TABLE IF NOT EXISTS calendar_notes(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except Exception as e2:
            _log_exc("ensure_notes_table", e2); DB_AVAILABLE = False

def _db_exec_params(sql: str, params: Tuple) -> int:
    global PARAM_STYLE
    try:
        return db_exec(sql if PARAM_STYLE == "%s" else sql.replace("%s", "?"), params)
    except Exception:
        try:
            if PARAM_STYLE == "%s":
                PARAM_STYLE = "?"
                return db_exec(sql.replace("%s", "?"), params)
            else:
                PARAM_STYLE = "%s"
                return db_exec(sql, params)
        except Exception as e:
            _log_exc("db_exec_params", e); raise

def _db_fetch_params(sql: str, params: Tuple) -> List[dict]:
    global PARAM_STYLE
    try:
        return db_fetch(sql if PARAM_STYLE == "%s" else sql.replace("%s", "?"), params)
    except Exception:
        try:
            if PARAM_STYLE == "%s":
                PARAM_STYLE = "?"
                return db_fetch(sql.replace("%s", "?"), params)
            else:
                PARAM_STYLE = "%s"
                return db_fetch(sql, params)
        except Exception as e:
            _log_exc("db_fetch_params", e); raise

def notes_list(date_iso: str) -> List[dict]:
    if DB_AVAILABLE:
        try:
            rows = _db_fetch_params(
                "SELECT id, DATE_FORMAT(date, '%%Y-%%m-%%d') AS date, text "
                "FROM calendar_notes WHERE date=%s ORDER BY id ASC",
                (date_iso,)
            )
        except Exception:
            try:
                rows = _db_fetch_params(
                    "SELECT id, date, text FROM calendar_notes WHERE date=%s ORDER BY id ASC",
                    (date_iso,)
                )
            except Exception as e:
                _log_exc("notes_list_db", e)
                rows = None
        if rows is not None and len(rows) > 0:
            return rows
    return _notes_for_local(date_iso)

def notes_dates_in_month(year: int, month: int) -> set[str]:
    db_dates: set[str] = set()
    if DB_AVAILABLE:
        try:
            rows = _db_fetch_params(
                "SELECT DATE_FORMAT(date, '%%Y-%%m-%%d') AS date "
                "FROM calendar_notes WHERE date BETWEEN %s AND %s",
                (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-31")
            )
        except Exception:
            try:
                rows = _db_fetch_params(
                    "SELECT date FROM calendar_notes WHERE date BETWEEN %s AND %s",
                    (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-31")
                )
            except Exception as e:
                _log_exc("notes_dates_in_month_db", e)
                rows = None
        if rows is not None:
            prefix = f"{year:04d}-{month:02d}-"
            db_dates = {r["date"] for r in rows
                        if isinstance(r.get("date"), str) and r["date"].startswith(prefix)}
    local_dates = _dates_with_notes_local(year, month)
    return db_dates | local_dates

def month_notes_info(year: int, month: int) -> dict:
    info: dict[str, dict] = {}
    for iso in notes_dates_in_month(year, month):
        rows = notes_list(iso)
        preview = (rows[0].get("text", "").strip() if rows else "")
        info[iso] = {"count": len(rows), "preview": preview}
    return info

def note_add(date_iso: str, text: str) -> Optional[int]:
    note_id = None
    if DB_AVAILABLE:
        try:
            _db_exec_params("INSERT INTO calendar_notes(date, text) VALUES(%s, %s)", (date_iso, text))
            try:
                rid = _db_fetch_params("SELECT MAX(id) AS id FROM calendar_notes WHERE date=%s AND text=%s", (date_iso, text))
                if rid and rid[0].get("id") is not None:
                    note_id = int(rid[0]["id"])
            except Exception:
                pass
        except Exception as e:
            _log_exc("note_add_db", e)
    _local_add(date_iso, text, note_id)
    return note_id

def note_update(note_id: Optional[int], new_text: str):
    if DB_AVAILABLE and note_id is not None:
        try: _db_exec_params("UPDATE calendar_notes SET text=%s WHERE id=%s", (new_text, note_id))
        except Exception as e: _log_exc("note_update_db", e)
    _local_update(note_id, new_text)

def note_delete(note_id: Optional[int]):
    if DB_AVAILABLE and note_id is not None:
        try: _db_exec_params("DELETE FROM calendar_notes WHERE id=%s", (note_id,))
        except Exception as e: _log_exc("note_delete_db", e)
    _local_delete(note_id)

def mark_notified_today(date_iso: str):
    _mark_notified_today_local(date_iso)

# ========= LAUNCHER (login/updates) =========
def main(page: ft.Page):
    page.title = "MPI Agro Launcher"
    page.window_width = 560
    page.window_height = 620
    page.window_resizable = False
    try:
        page.theme_mode = ft.ThemeMode.DARK
        page.locale = ft.Locale("uk", "UA")
    except Exception:
        pass

    # remember me
    remembered_login = ""
    remembered_password = ""
    remember_checked_default = False
    try:
        if REMEMBER_PATH.exists():
            data = json.loads(REMEMBER_PATH.read_text(encoding="utf-8"))
            remembered_login = (data.get("last_login") or "").strip()
            remembered_password = data.get("password") or ""
            remember_checked_default = bool(data.get("remember", False))
    except Exception:
        pass

    msg_login = ft.Text("", color="#ff6b6b", size=13, visible=False)
    msg_reg = ft.Text("", color="#ff6b6b", size=13, visible=False)
    login_login = make_tf("Логін", "Введіть ваш логін", autofocus=True)
    if remembered_login:
        login_login.value = remembered_login
    login_pass = make_tf("Пароль", "Введіть пароль", password=True)
    # If the user opted to remember credentials, pre-fill the password as well
    if remembered_password and remember_checked_default:
        login_pass.value = remembered_password
    remember_cb = ft.Checkbox(label="Запам'ятати користувача", value=remember_checked_default)
    user_ctx: Dict[str, Any] = {}

    def _save_remember_state(login: str, password: str, remember: bool):
        """
        Persist the last used login and password along with the remember flag.
        If remember=False, both login and password are cleared from the file.
        """
        try:
            data = {
                "last_login": login if remember else "",
                "password": password if remember else "",
                "remember": bool(remember),
            }
            REMEMBER_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            _log_exc("remember", e)

    def show_login_error(t):
        msg_login.value = t; msg_login.visible = True; page.update()
    def show_reg_error(t):
        msg_reg.value = t; msg_reg.visible = True; page.update()

    def do_login(_=None):
        msg_login.visible = False
        lg = (login_login.value or "").strip()
        pw = (login_pass.value or "").strip()
        if not lg or not pw:
            show_login_error("Вкажіть логін і пароль"); return
        token = api_login(API_BASE, lg, pw)
        if not token:
            show_login_error("Невірний логін/пароль або сервер недоступний"); return
        profile = api_me(API_BASE, token) or {}
        user_ctx.update({
            "id": profile.get("id"),
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "login": profile.get("login", lg),
            "role": profile.get("role", "Користувач"),
            "auth_token": token,
        })
        # Save credentials if remember is selected
        _save_remember_state(lg, pw, remember_cb.value)
        # After successful login go straight to the main menu
        launch_program(None)

    login_btn = ft.FilledButton(
        "Увійти",
        icon=ft.icons.LOGIN,
        width=FIELD_WIDTH,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        on_click=do_login
    )

    # Registration (optional)
    reg_first = make_tf("Ім'я", "Напр.: Іван")
    reg_last  = make_tf("Прізвище", "Напр.: Петренко")
    reg_login = make_tf("Логін", "Латиниця/цифри без пробілів")
    reg_pass  = make_tf("Пароль", "Мінімум 6 символів", password=True)
    reg_role_pass = make_tf("Пароль ролі", "Від адміністратора", password=True)

    def do_register(_=None):
        msg_reg.visible = False
        fn, ln, lg, pw, rp = (reg_first.value or "").strip(), (reg_last.value or "").strip(), (reg_login.value or "").strip(), (reg_pass.value or "").strip(), (reg_role_pass.value or "").strip()
        if not (fn and ln and lg and pw and rp):
            show_reg_error("Усі поля обов'язкові"); return
        try:
            r = requests.post(API_BASE + "/auth/register",
                              json={"first_name": fn,"last_name": ln,"login": lg,"password": pw,"role_password": rp},
                              timeout=12)
            if r.status_code != 200:
                try: detail = r.json().get("detail", f"HTTP {r.status_code}")
                except Exception: detail = f"HTTP {r.status_code}"
                show_reg_error(str(detail)); return
        except Exception as e:
            show_reg_error(str(e)); return
        token = api_login(API_BASE, lg, pw)
        if not token:
            show_reg_error("Зареєстровано, але сервіс логіну недоступний."); return
        profile = api_me(API_BASE, token) or {}
        user_ctx.update({
            "id": profile.get("id"),
            "first_name": profile.get("first_name", fn),
            "last_name": profile.get("last_name", ln),
            "login": profile.get("login", lg),
            "role": profile.get("role", "Користувач"),
            "auth_token": token,
        })
        # Save credentials if remember is selected
        _save_remember_state(lg, pw, remember_cb.value)
        # After successful registration go straight to the main menu
        launch_program(None)

    reg_btn = ft.FilledButton("Зареєструватися", icon=ft.icons.PERSON_ADD, width=FIELD_WIDTH,
                              style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                              on_click=do_register)

    # Tabs
    auth_tabs = ft.Tabs(
        tabs=[
            ft.Tab(text="Вхід", content=ft.Container(
                content=ft.Column([login_login, login_pass, remember_cb, login_btn, msg_login],
                                  spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(top=15))),
            ft.Tab(text="Реєстрація", content=ft.Container(
                content=ft.Column([reg_first, reg_last, reg_login, reg_pass, reg_role_pass, reg_btn, msg_reg],
                                  spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(top=15))),
        ], expand=1,
    )

    # --- логотип на екрані авторизації (x2) ---
    logo = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        content=ft.Image(src=str((APP_DIR / "icons" / "app_icon1.png")), width=1600, fit=ft.ImageFit.CONTAIN),
        opacity=0.28,
        visible=True,
    )

    body = ft.Container(
        content=ft.Column(
            [ft.Text("MPI Agro Launcher", size=22, color="#e2e8f0"),
             ft.Divider(color="#1f3b63"),
             auth_tabs],
            expand=True
        ),
        expand=True,
        padding=20
    )

    # --- фон екрану оновлення з великим логотипом ---
    update_bg = ft.Stack(
        expand=True,
        controls=[
            ft.Image(src=str((APP_DIR / "icons" / "preview.png")), expand=True, fit=ft.ImageFit.COVER),
            ft.Container(expand=True, bgcolor="#0b1220", opacity=0.60),
            ft.Container(
                content=ft.Image(src=str((APP_DIR / "icons" / "app_icon1.png")), width=1200, fit=ft.ImageFit.CONTAIN),
                alignment=ft.alignment.center,
                opacity=0.22,
            ),
        ],
        visible=False
    )

    root = ft.Stack(expand=True, controls=[update_bg, logo, ft.Container(expand=True, content=body)])
    page.add(root)

    # --- Update screen widgets ---
    status_txt = ft.Text(f"Перевірка оновлень… (локальна {LOCAL_VERSION})", color="#ffffff", size=16)
    progress = ft.ProgressBar(height=20, bgcolor="#274060", color="#00ace6", expand=True)
    launch_btn = ft.FilledButton("Запуск", icon=ft.icons.PLAY_ARROW, disabled=True, width=160)

    server_dot = ft.Container(width=10, height=10, border_radius=50, bgcolor="#ef4444")
    server_title = ft.Text("Сервер: офлайн", size=14, weight="w600", color="#e2e8f0")
    server_sub = ft.Text("—", size=12, color="#cbd5e1")
    server_card = ft.Container(
        content=ft.Row([server_dot, ft.Column([server_title, server_sub], spacing=2),
                        ft.Container(expand=True),
                        ft.IconButton(icon=ft.icons.REFRESH, on_click=lambda e: check_server_async())],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.symmetric(horizontal=12, vertical=10), border_radius=12, bgcolor="#0f172a")
    server_card.visible = False

    update_view = ft.Column(
        [ft.Container(expand=True), server_card, ft.Container(height=12),
         status_txt, ft.Container(height=12),
         ft.Row([progress, ft.Container(width=16), launch_btn], alignment=ft.MainAxisAlignment.END)],
        expand=True, alignment=ft.MainAxisAlignment.END, horizontal_alignment=ft.CrossAxisAlignment.END,
    )

    def set_status(msg, prog=None, enable=None):
        status_txt.value = msg
        progress.value = None if prog is None else max(0.0, min(1.0, float(prog)))
        if enable is not None:
            launch_btn.disabled = not enable
        page.update()

    def finish_ready():
        set_status("Готово до роботи", 1.0, True)

    def _set_server_ui(ok, title, sub):
        server_dot.bgcolor = "#22c55e" if ok else "#ef4444"
        server_title.value = title
        server_sub.value = sub
        page.update()

    def check_server_now():
        t0 = time.perf_counter()
        try:
            r = requests.get(HEALTH_URL, timeout=6); lat = int((time.perf_counter() - t0) * 1000)
            if r.status_code != 200:
                _set_server_ui(False, "Сервер: офлайн", f"HTTP {r.status_code} • {lat} мс")
                return
            d = parse_health(r)
            _set_server_ui(d["ok"], "Сервер: онлайн" if d["ok"] else "Сервер: офлайн", f"v{d['version'] or '—'} • {lat} мс")
        except Exception as e:
            _set_server_ui(False, "Сервер: офлайн", str(e))

    def check_server_async():
        threading.Thread(target=check_server_now, daemon=True).start()

    poll_timer: Optional[threading.Timer] = None
    def schedule_poll():
        nonlocal poll_timer
        if poll_timer:
            try: poll_timer.cancel()
            except Exception: pass
        def _tick():
            check_server_async(); schedule_poll()
        poll_timer = threading.Timer(SERVER_POLL_SEC, _tick); poll_timer.daemon = True; poll_timer.start()

    def check_update():
        if DISABLE_UPDATES:
            finish_ready(); return
        headers = {"Authorization": f"Bearer {UPDATE_TOKEN}"} if UPDATE_TOKEN else {}
        try:
            r = requests.get(UPDATE_API, timeout=20, headers=headers)
            if r.status_code == 404: finish_ready(); return
            if r.status_code != 200: set_status(f"Сервер оновлень відповів {r.status_code}", 0.0, True); return
            man = r.json()
        except Exception as e:
            _log_exc("updates/latest", e); set_status(f"Оновлення недоступні: {e}", 0.0, True); return

        remote_version = (man.get("version") or "").strip()
        url = (man.get("download_url") or "").strip()
        sha256 = (man.get("sha256") or "").strip().lower() or None
        if not remote_version or not url:
            finish_ready(); return

        def _ver_tuple(s: str) -> tuple:
            parts = (s + ".0.0").split(".")[:3]; return tuple(int(x) if x.isdigit() else 0 for x in parts)
        if _ver_tuple(remote_version) <= _ver_tuple(LOCAL_VERSION):
            finish_ready(); return

        set_status(f"Завантаження {remote_version}…", 0.0, False)
        fd, tmp_path = tempfile.mkstemp(prefix="upd_", suffix=".bin"); os.close(fd)
        try:
            with requests.get(url, stream=True, timeout=30, headers=headers) as resp:
                if resp.status_code != 200: set_status(f"Помилка завантаження: HTTP {resp.status_code}", 0.0, True); return
                total = int(resp.headers.get("content-length", 0)); got = 0; has_len = total > 0
                h = hashlib.sha256()
                with open(tmp_path, "wb") as out:
                    for chunk in resp.iter_content(1024 * 256):
                        if not chunk: continue
                        out.write(chunk)
                        if sha256: h.update(chunk)
                        if has_len:
                            got += len(chunk); set_status(f"Завантаження {remote_version}…", got/total, False)
                        else:
                            set_status(f"Завантаження {remote_version}…", None, False)
            if sha256 and h.hexdigest().lower() != sha256:
                set_status("Хеш не збігається", 0.0, True); os.remove(tmp_path); return
            app_dir = str(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR)
            set_status("Розпакування оновлення (ZIP)…", None, False); apply_update_zip(tmp_path, app_dir)
            write_version_file(remote_version); set_status(f"Оновлено до {remote_version}", 1.0, True)
        finally:
            try: os.remove(tmp_path)
            except Exception: pass

    def open_update_screen():
        # Restore the update manager UI: hide the login logo and show the update background.
        logo.visible = False
        update_bg.visible = True
        # Replace the body content with the update view containing status, progress and launch button
        body.content = update_view
        # Make the server status card visible
        server_card.visible = True
        # Update the page after modifications
        page.update()
        # Start polling the server status and checking for updates asynchronously
        check_server_async()
        schedule_poll()
        threading.Thread(target=check_update, daemon=True).start()

    def open_auth_screen(e=None):
        """
        Display the login/registration screen after the update manager finishes.
        Restores the original launcher UI and hides the update screen.
        
        Accepts an optional event parameter because Flet will pass an event object
        when this function is used as an on_click handler.
        """
        # Show login/registration UI
        logo.visible = True
        update_bg.visible = False
        server_card.visible = False
        body.content = ft.Column(
            [ft.Text("MPI Agro Launcher", size=22, color="#e2e8f0"),
             ft.Divider(color="#1f3b63"),
             auth_tabs],
            expand=True
        )
        page.update()

    # Register callbacks on the page so they can be called later (e.g., on logout or exit)
    # Ensure page.data is a dictionary even if it was None or some other type
    try:
        if not isinstance(page.data, dict):
            page.data = {}
    except Exception:
        page.data = {}
    # Store both authentication and update screen callbacks so that other code (e.g., the
    # user chip exit menu) can access them. This allows the system to return to either the
    # update manager or the auth screen depending on context.
    page.data["open_auth_screen"] = open_auth_screen
    page.data["open_update_screen"] = open_update_screen

    # Launch main
    def launch_program(_):
        install_dir = str(Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else APP_DIR)
        try:
            srv_dir = Path(install_dir) / "server"; srv_dir.mkdir(parents=True, exist_ok=True)
            sess_path = srv_dir / "session.json"
            payload = {"user": {}}
            u = payload["user"]
            if user_ctx.get("id") is not None:     u["id"] = int(user_ctx["id"])
            if user_ctx.get("login"):              u["login"] = user_ctx["login"]
            if user_ctx.get("first_name"):         u["first_name"] = user_ctx["first_name"]
            if user_ctx.get("last_name"):          u["last_name"] = user_ctx["last_name"]
            if user_ctx.get("role"):               u["role"] = user_ctx["role"]
            sess_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            _log_exc("session.json", e)

        overlay = ft.Container(
            expand=True, bgcolor="#0b0f18", opacity=0.95, alignment=ft.alignment.center,
            content=ft.Column([ft.ProgressRing(width=42, height=42),
                               ft.Text("Запуск головного меню…", color="#e2e8f0")],
                              spacing=14, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        page.overlay.append(overlay); page.update()

        try:
            app_main(page)
            if not page.views:
                raise RuntimeError("app_main(page) завершилась, але жодного представлення не додано до Page.")
        except Exception as err:
            _log_exc("app_main", err)
            dlg = ft.AlertDialog(modal=True, title=ft.Text("Помилка запуску головного меню"),
                                 content=ft.Text(str(err), color="#ff6b6b"),
                                 actions=[ft.TextButton("OK", on_click=lambda e: (setattr(dlg,"open",False), page.update()))])
            if dlg not in page.overlay: page.overlay.append(dlg)
            dlg.open = True; page.dialog = dlg; page.update()
        finally:
            try: page.overlay.remove(overlay)
            except Exception: pass
            page.update()

    # When the update manager finishes, clicking "Запуск" should open the authentication screen
    launch_btn.on_click = open_auth_screen
    # Login and register buttons continue to trigger their respective handlers
    login_btn.on_click  = do_login
    reg_btn.on_click    = do_register

    # Display the update manager screen immediately on startup
    open_update_screen()

# ========= EMBEDDED MAIN APPLICATION =========
try:
    from utils.i18n import set_page_locale_uk
except Exception:
    def set_page_locale_uk(page: ft.Page):
        try: page.locale = ft.Locale("uk","UA")
        except Exception: pass

try:
    from components.notif_banner import NotifBanner
except Exception:
    class NotifBanner:
        def __init__(self, *a, **k): pass

def _fallback_view(name: str):
    def _v(page: ft.Page):
        return ft.View(f"/{name}", controls=[ft.Container(ft.Text(f"{name}: сторінка тимчасово недоступна"), padding=20)])
    return _v

def import_view(candidates, attr):
    for mod_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=[attr])
            return getattr(mod, attr)
        except Exception:
            continue
    return _fallback_view(candidates[-1].split(".")[-1])

# Removed import of the warehouse module as the "Склад" section has been deprecated.


product_base_view    = import_view(["pages.product_base","product_base"],           "product_base_view")
monitoring_view      = import_view(["pages.monitoring","monitoring"],               "monitoring_view")
casting_request_view = import_view(["pages.casting_request","casting_request"],     "view")
casting_view         = import_view(["pages.casting","casting"],                     "view")
drying_view          = import_view(["pages.drying","drying"],                       "view")
casting_quality_view = import_view(["pages.casting_quality","casting_quality"],     "view")
trimming_view        = import_view(["pages.trimming","trimming"],                   "view")
cutting_view         = import_view(["pages.cutting","cutting"],                     "view")
cleaning_view        = import_view(["pages.cleaning","cleaning"],                   "view")
final_quality_view   = import_view(["pages.final_quality","final_quality"],         "view")
# The warehouse view is removed; assign None to avoid unresolved references.
warehouse_view       = None

# ========= MAIN MENU + POPUP CALENDAR =========
def app_main(page: ft.Page):
    set_page_locale_uk(page)
    try: page.locale = ft.Locale("uk","UA")
    except Exception: pass

    try: _ensure_notes_table()
    except Exception: pass

    page.title = "MPI Agro"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_maximized = True
    page.bgcolor = "#0f0f17"

    # back nav helpers
    def _top_route() -> str: return page.views[-1].route if page.views else "/"
    def back_to_root(_=None):
        if len(page.views) > 1:
            page.views.pop(); page.go(_top_route())
    page.on_view_pop = back_to_root
    page.on_route_change = lambda _: page.update()

    # --- CLOCK ---
    time_lbl = ft.Text(size=32, weight="bold", color="#22d3ee")
    date_lbl = ft.Text(size=18, weight="bold", color="#ffffff")
    ukr_wd_short = ["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]
    ukr_months   = ["січень","лютий","березень","квітень","травень","червень","липень","серпень","вересень","жовтень","листопад","грудень"]

    # === USER CHIP (замість дзвіночка) ===
    def _read_any_json(paths):
        for p in paths:
            try:
                if Path(p).exists():
                    return json.loads(Path(p).read_text(encoding="utf-8"))
            except Exception: pass
        return None
    def _get_session_user() -> dict:
        data = _read_any_json([RES("auth","session.json"), RES("session.json"), RES("server","session.json")])
        if isinstance(data, dict): return data.get("user", data)
        return {}
    def _initials(first: str, last: str, full_fallback: str = "") -> str:
        first, last = (first or "").strip(), (last or "").strip()
        if first or last: return ((first[:1] or "") + (last[:1] or "")).upper()
        parts = (full_fallback or "").strip().split()
        return (parts[0][:1] + (parts[1][:1] if len(parts)>1 else "")).upper() or "U"

    u = _get_session_user()
    fn, ln = (u.get("first_name") or "").strip(), (u.get("last_name") or "").strip()
    full = (u.get("full_name") or u.get("name") or "").strip()
    disp = full if full else (f"{fn} {ln}".strip() or (u.get("login") or "Користувач"))
    role = (u.get("role") or "—").strip()

    # --- Logout handler: return the user to the authentication screen ---
    def logout_user(_=None):
        """
        Clear the main menu views and display the authentication screen again.
        Uses the open_auth_screen callback stored on the page during launcher init.
        """
        try:
            # Remove all views from the page to reset navigation state
            page.views.clear()
            # Invoke the stored callback to display the login/registration UI
            cb = None
            try:
                cb = page.data.get("open_auth_screen") if isinstance(page.data, dict) else None
            except Exception:
                cb = None
            if callable(cb):
                cb()
        except Exception:
            pass

    def _build_user_chip(display_name: str, role: str, initials: str):
        core = ft.Container(
            content=ft.Row(
                [
                    ft.CircleAvatar(content=ft.Text(initials, size=12, weight="bold"), radius=14, bgcolor="#334155"),
                    ft.Column([ft.Text(display_name, size=14, weight="w600"),
                               ft.Text(role, size=12, color="#cbd5e1")], spacing=0),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=12,
            bgcolor="#111827",
        )
        badge_text = ft.Text("", size=10, weight="bold", color="#ffffff")
        badge = ft.Container(badge_text, bgcolor="#e11d48", border_radius=9999,
                             padding=ft.padding.symmetric(horizontal=5, vertical=2), visible=False)
        badge_host = ft.Container(badge, right=-4, top=-6)
        chip_stack = ft.Stack([core, badge_host])

        def _open_notifications(_=None):
            today_iso = _dt.date.today().isoformat()
            rows = notes_list(today_iso)
            lines = [r.get("text", "").strip() for r in rows if r.get("text")]
            present_card("Сповіщення на сьогодні", lines or ["Немає сповіщень"])
            _set_unread(0)

        # Define menu actions for profile, notifications, messages, and exit. Each action
        # calls a custom modal that darkens the page and shows the content without icons.
        def _menu_profile(e=None):
            # Display the user profile in a modal with a tinted background
            present_custom_modal("Профіль", [display_name, f"Роль: {role}"])

        def _menu_notifications(e=None):
            today_iso = _dt.date.today().isoformat()
            rows = notes_list(today_iso)
            lines = [r.get("text", "").strip() for r in rows if r.get("text")]
            present_custom_modal("Сповіщення на сьогодні", lines or ["Немає сповіщень"])
            _set_unread(0)

        def _menu_messages(e=None):
            present_custom_modal("Повідомлення", ["Список чатів наразі недоступний"])

        def _menu_exit(e=None):
            """
            Navigate back to the update manager on exit.

            When exiting from the user chip we need to make sure any active overlays
            (such as darkened backgrounds or modal windows) are removed, otherwise
            the app may appear as a black screen. After cleaning overlays and
            views, invoke the stored callback to restore the update manager.
            """
            try:
                # Remove any overlay controls (e.g. custom modals) so they don't
                # obscure the page after navigating back.
                try:
                    page.overlay.clear()
                except Exception:
                    pass
                # Determine which callback to invoke: prefer the update screen if available,
                # otherwise fall back to the auth screen.
                cb = None
                if isinstance(page.data, dict):
                    cb = page.data.get("open_update_screen") or page.data.get("open_auth_screen")
                # Collapse the navigation stack back to the root view. Avoid leaving the
                # views list empty to prevent a blank page. Pop until only the first view remains.
                try:
                    while len(page.views) > 1:
                        page.views.pop()
                except Exception:
                    pass
                # Navigate to the root route (last remaining view's route) to ensure
                # the root view is active.
                try:
                    root_route = page.views[-1].route if page.views else "/"
                    page.go(root_route)
                except Exception:
                    pass
                # Invoke the selected callback to show the update or auth screen
                if callable(cb):
                    cb()
                # Ensure the page is redrawn after modifications
                page.update()
            except Exception:
                pass

        # Create a popup menu with our custom actions (no icons for each item)
        user_menu = ft.PopupMenuButton(
            content=chip_stack,
            items=[
                ft.PopupMenuItem(text="Профіль", on_click=_menu_profile),
                ft.PopupMenuItem(text="Сповіщення", on_click=_menu_notifications),
                ft.PopupMenuItem(text="Повідомлення", on_click=_menu_messages),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(text="Вихід", on_click=_menu_exit),
            ],
        )

        def _set_unread(n: int):
            n = max(0, int(n or 0))
            badge_text.value = str(n)
            badge.visible = n > 0
            chip_stack.update()

        # Return the popup menu button and the unread setter
        return user_menu, _set_unread

    chip_control, _set_unread = _build_user_chip(disp, role, _initials(fn, ln, disp))

    # ===== КАЛЕНДАР =====
    today = _dt.date.today()
    cal_year, cal_month = today.year, today.month
    selected_date: _dt.date | None = today
    month_info: dict[str, dict] = {}

    dp = ft.DatePicker(first_date=_dt.date(1990,1,1), last_date=_dt.date(2100,12,31), help_text="Оберіть дату")
    page.overlay.append(dp)

    # для повідомлень (картка поверх сторінки)
    def present_card(title: str, lines: List[str], on_close=None):
        bg_path = RES("icons", "app_icon1.png")
        items = [l.strip() for l in (lines or []) if l and l.strip()]
        est_h = 20 * max(1, len(items))
        card_h = max(220, min(360, 130 + est_h))
        def _close(_=None):
            try: page.overlay.remove(overlay)
            except Exception: pass
            page.update()
            if callable(on_close): on_close()
        img_layer = ft.Container(content=ft.Image(src=bg_path, fit=ft.ImageFit.COVER, opacity=1.0), expand=True,
                                 alignment=ft.alignment.center)
        card = ft.Container(width=520, height=card_h, border_radius=16, clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            border=ft.border.all(1, "#1f2937"),
                            shadow=ft.BoxShadow(blur_radius=24, color="#00000088"),
                            content=ft.Stack([img_layer, ft.Container(padding=16, content=ft.Column([
                                ft.Text(title, size=18, weight="bold", color="#e2e8f0"),
                                ft.Container(height=card_h - 130,
                                             content=ft.Column([ft.Text(f"• {t}", size=14, color="#e5e7eb") for t in items],
                                                               spacing=6, tight=True, scroll=ft.ScrollMode.ALWAYS)),
                                ft.Row([ft.FilledButton("ОК", icon=ft.icons.CHECK, on_click=_close)],
                                      alignment=ft.MainAxisAlignment.END),
                            ], spacing=8))]))
        overlay = ft.Container(expand=True, bgcolor="#000000", opacity=0.55,
                               content=ft.Container(content=card, alignment=ft.alignment.center), on_click=_close)
        page.overlay.append(overlay); page.update()

    # -------------------------------------------------------------------------
    # Custom modal for profile, notifications, and messages
    # This dialog darkens the page more, uses a tinted gradient background, and
    # does not display any extra icons or images. It accepts a title and a list
    # of strings to display. Each item is prefaced with a bullet to separate
    # lines, similar to present_card.
    def present_custom_modal(title: str, lines: List[str]):
        # Prepare items list, trimming empty strings
        items = [l.strip() for l in (lines or []) if l and l.strip()]
        # Compute desired width and height based on the current window size (80% of width and height).
        # Fall back to fixed values if window dimensions are not available.
        try:
            win = getattr(page, "window", None)
            win_w = float(getattr(win, "width", 0)) if win else 0
            win_h = float(getattr(win, "height", 0)) if win else 0
        except Exception:
            win_w = win_h = 0
        # Use 80% of window dimensions when available, otherwise default to 600x400.
        card_w = int(max(320, (win_w * 0.8) if win_w else 600))
        card_h = int(max(240, (win_h * 0.8) if win_h else 400))
        # Bound the height to accommodate content but not exceed the computed value
        est_h = 20 * max(1, len(items))
        inner_h = max(0, card_h - 130)
        # Define the close handler to remove the overlay and update the page
        def _close(_=None):
            try:
                page.overlay.remove(overlay)
            except Exception:
                pass
            page.update()
        # Build the card container. Use a solid dark blue colour matching the provided screenshot (#141431).
        card = ft.Container(
            width=card_w,
            height=card_h,
            border_radius=16,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            bgcolor="#141431",  # solid background to avoid transparency
            opacity=1.0,  # ensure the container itself is fully opaque
            border=ft.border.all(1, "#1f2937"),
            shadow=ft.BoxShadow(blur_radius=24, color="#00000088"),
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    [
                        ft.Text(title, size=18, weight="bold", color="#e2e8f0"),
                        ft.Container(
                            height=inner_h,
                            content=ft.Column(
                                [ft.Text(f"• {t}", size=14, color="#e5e7eb") for t in items],
                                spacing=6,
                                tight=True,
                                scroll=ft.ScrollMode.ALWAYS,
                            ),
                        ),
                        ft.Row(
                            [ft.FilledButton("ОК", on_click=_close)],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=8,
                ),
            ),
        )
        # Darker overlay to dim the entire page
        overlay = ft.Container(
            expand=True,
            bgcolor="#000000",
            # Increase overlay opacity to reduce bleed-through of the underlying UI
            opacity=0.90,
            content=ft.Container(content=card, alignment=ft.alignment.center),
            on_click=_close,
        )
        page.overlay.append(overlay)
        page.update()

    cal_title = ft.Text("", size=15, weight="bold", color="#e2e8f0")
    cal_grid = ft.Column(spacing=4)
    cal_notes_btn = ft.FilledButton("Нотатки", icon=ft.icons.NOTE_ADD)
    notes_overlay = ft.Container(visible=False)

    def _build_day_cell(day_date: _dt.date | None, info: dict | None, is_selected: bool) -> ft.Container:
        if day_date is None:
            return ft.Container(width=40, height=36)
        has_note = info is not None
        label = ft.Text(str(day_date.day), size=13, color="#ff0000" if has_note else "#e5e7eb",
                        weight="w700" if has_note else None)
        ring = ft.Container(width=30, height=30, border_radius=18, alignment=ft.alignment.center, content=label)
        day_stack = ft.Stack([ft.Container(content=ring, alignment=ft.alignment.center)], width=40, height=36)
        cell_bg = "#152035" if is_selected else "#0b0b1a"
        def _tap(_):
            nonlocal selected_date
            selected_date = day_date
            _rebuild_calendar()
        cell = ft.Container(content=day_stack, width=40, height=36, bgcolor=cell_bg, border_radius=10, ink=True,
                            on_click=_tap, border=ft.border.all(1, "#111827"), animate=ft.Animation(150, "easeOut"),
                            tooltip=(f"Нотаток: {info.get('count', 0)}\n"
                                     f"{(info.get('preview','') or '').strip().replace(chr(10),' ')[:120]}…")
                                    if has_note else None)
        return cell

    def _rebuild_calendar():
        nonlocal month_info
        cal_title.value = f"{ukr_months[cal_month-1].capitalize()} {cal_year}"
        month_info = month_notes_info(cal_year, cal_month)
        first_weekday, num_days = calendar.monthrange(cal_year, cal_month)  # Monday=0
        start_pad = (first_weekday - 0) % 7
        rows: List[ft.Row] = []
        rows.append(ft.Row([ft.Container(ft.Text(w, size=12, color="#93c5fd"), width=40, alignment=ft.alignment.center)
                            for w in ["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]], spacing=2))
        cells: List[ft.Control] = []
        for _ in range(start_pad):
            cells.append(_build_day_cell(None, None, False))
        for d in range(1, num_days + 1):
            ddate = _dt.date(cal_year, cal_month, d)
            iso = ddate.isoformat()
            info = month_info.get(iso)
            is_selected = (selected_date == ddate)
            cells.append(_build_day_cell(ddate, info, is_selected))
        while len(cells) % 7 != 0:
            cells.append(_build_day_cell(None, None, False))
        rows.extend(ft.Row(cells[i:i+7], spacing=2) for i in range(0, len(cells), 7))
        cal_grid.controls = rows
        page.update()

    def _prev_month(_):
        nonlocal cal_year, cal_month
        cal_month -= 1
        if cal_month == 0: cal_month = 12; cal_year -= 1
        _rebuild_calendar()

    def _next_month(_):
        nonlocal cal_year, cal_month
        cal_month += 1
        if cal_month == 13: cal_month = 1; cal_year += 1
        _rebuild_calendar()

    def _notes_row(note: dict):
        nid = note.get("id")
        tf = ft.TextField(value=note.get("text",""), multiline=True, min_lines=1, max_lines=4, expand=True,
                          read_only=True, border=ft.InputBorder.OUTLINE)
        edit_mode = {"on": False}
        def _toggle_edit(_):
            edit_mode["on"] = not edit_mode["on"]
            tf.read_only = not edit_mode["on"]
            save_btn.visible = edit_mode["on"]; cancel_btn.visible = edit_mode["on"]; edit_btn.visible = not edit_mode["on"]
            row.update()
        def _save(_):
            txt = (tf.value or "").strip()
            if not txt: return
            note_update(nid, txt); _rebuild_calendar(); _refresh_notes_list()
            _update_unread_from_rows(notes_list((selected_date or _dt.date.today()).isoformat()))
            page.snack_bar = ft.SnackBar(ft.Text("Нотатку оновлено")); page.snack_bar.open = True; page.update()
        def _cancel(_):
            tf.value = note.get("text",""); _toggle_edit(None)
        def _delete(_):
            confirm = ft.AlertDialog(modal=True, title=ft.Text("Видалити нотатку?"),
                                     actions=[ft.TextButton("Скасувати", on_click=lambda e: (setattr(confirm,"open",False), page.update())),
                                              ft.FilledButton("Видалити", icon=ft.icons.DELETE, on_click=lambda e: (_do_delete(), setattr(confirm,"open",False), page.update()))])
            if confirm not in page.overlay: page.overlay.append(confirm)
            confirm.open = True; page.dialog = confirm; page.update()
        def _do_delete():
            note_delete(nid); _rebuild_calendar(); _refresh_notes_list()
            _update_unread_from_rows(notes_list((selected_date or _dt.date.today()).isoformat()))
        save_btn   = ft.IconButton(ft.icons.CHECK,  tooltip="Зберегти",  visible=False, on_click=_save)
        cancel_btn = ft.IconButton(ft.icons.CLOSE,  tooltip="Скасувати", visible=False, on_click=_cancel)
        edit_btn   = ft.IconButton(ft.icons.EDIT,   tooltip="Редагувати", on_click=_toggle_edit)
        del_btn    = ft.IconButton(ft.icons.DELETE, tooltip="Видалити",   on_click=_delete)
        row = ft.Row([tf, ft.Row([save_btn, cancel_btn, edit_btn, del_btn], spacing=0)],
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        return row

    notes_list_col = ft.Column(spacing=8, height=220, scroll="always")
    new_note_tf = ft.TextField(hint_text="Нова нотатка…", multiline=True, min_lines=2, max_lines=4, expand=True)
    notes_date_lbl = ft.Text("", size=12, color="#93c5fd")

    def _refresh_notes_list():
        d = selected_date or _dt.date.today()
        notes_date_lbl.value = d.strftime("%d.%m.%Y")
        rows = notes_list(d.isoformat())
        notes_list_col.controls = [_notes_row(r) for r in rows] if rows else [ft.Text("Немає нотаток на цю дату", color="#94a3b8")]
        notes_overlay.update()

    def _update_unread_from_rows(rows: list[dict]):
        _set_unread(len([r for r in rows if (r.get("text") or "").strip()]))

    def _add_new_note(_):
        d = selected_date or _dt.date.today()
        txt = (new_note_tf.value or "").strip()
        if not txt: return
        note_add(d.isoformat(), txt); new_note_tf.value = ""
        _refresh_notes_list(); _rebuild_calendar()
        _update_unread_from_rows(notes_list(d.isoformat()))
        page.snack_bar = ft.SnackBar(ft.Text("Нотатку додано")); page.snack_bar.open = True; page.update()

    notes_overlay_content = ft.Container(
        content=ft.Column(
            [
                ft.Row([ft.Text("Нотатки", size=16, weight="bold"),
                        ft.Container(expand=True),
                        ft.IconButton(ft.icons.CLOSE, tooltip="Закрити", on_click=lambda e: _toggle_notes_overlay(False))],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                notes_date_lbl,
                ft.Divider(color="#1e293b"),
                notes_list_col,
                ft.Row([new_note_tf, ft.FilledButton("Додати", icon=ft.icons.ADD, on_click=_add_new_note)],
                       alignment=ft.MainAxisAlignment.END),
            ], spacing=8
        ),
        padding=12, bgcolor="#0b1220", opacity=0.95, width=360, border_radius=14,
    )

    cal_card = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.icons.CHEVRON_LEFT, tooltip="Попередній місяць", on_click=_prev_month),
                        ft.Container(cal_title, expand=True, alignment=ft.alignment.center),
                        ft.IconButton(ft.icons.CHEVRON_RIGHT, tooltip="Наступний місяць", on_click=_next_month),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER, height=40,
                ),
                ft.Divider(height=1, color="#1e293b"),
                ft.Container(cal_grid, expand=True, padding=ft.padding.symmetric(horizontal=4, vertical=6)),
                ft.Row([cal_notes_btn], alignment=ft.MainAxisAlignment.START)
            ],
            spacing=4, expand=True,
        ),
        width=320, height=400, bgcolor="#070e1c",
        border_radius=18, padding=8,
        shadow=ft.BoxShadow(blur_radius=18, color="#00000073"),
        border=ft.border.all(1, "#111827"),
    )

    cal_popover = ft.Container(content=ft.Stack([cal_card, ft.Container(notes_overlay, alignment=ft.alignment.center)]),
                               visible=False)
    cal_popover.right = 20
    cal_popover.top   = 78

    scrim = ft.Container(expand=True, bgcolor="#000000", opacity=0.05,
                         visible=False, on_click=lambda e: _toggle_calendar(force=False))

    overlay_host = ft.Stack([scrim, cal_popover], expand=True)
    if overlay_host not in page.overlay:
        page.overlay.append(overlay_host)

    def _toggle_notes_overlay(show: bool):
        notes_overlay.visible = show
        notes_overlay.content = notes_overlay_content if show else None
        if show:
            d = selected_date or _dt.date.today()
            notes_date_lbl.value = d.strftime("%d.%m.%Y")
            _refresh_notes_list()
        cal_popover.update()
    cal_notes_btn.on_click = lambda e: _toggle_notes_overlay(True)

    def _toggle_calendar(_=None, force: Optional[bool] = None):
        want = (not cal_popover.visible) if force is None else force
        cal_popover.visible = want
        scrim.visible = want
        if want:
            _rebuild_calendar()
            _toggle_notes_overlay(False)
        page.update()

    def _on_date_change(e):
        try:
            iso = None
            if hasattr(e, "data") and isinstance(e.data, str) and e.data:
                iso = e.data
            if not iso and getattr(dp, "value", None):
                v = dp.value
                if isinstance(v, _dt.date): iso = v.isoformat()
                elif isinstance(v, str) and v: iso = v
            if not iso: return
            y, m, d = map(int, iso.split("-"))
            nonlocal cal_year, cal_month, selected_date
            cal_year, cal_month, selected_date = y, m, _dt.date(y, m, d)
            _rebuild_calendar(); _toggle_calendar(force=True); _toggle_notes_overlay(True)
        except Exception as ex:
            _log_exc("date_change", ex)
    dp.on_change = _on_date_change

    def _kb(e: ft.KeyboardEvent):
        if e.key == "Escape" and cal_popover.visible:
            _toggle_calendar(force=False)
    page.on_keyboard_event = _kb

    async def _clock():
        while True:
            now = _dt.datetime.now()
            time_lbl.value = now.strftime("%H:%M:%S")
            wd = ukr_wd_short[now.weekday() if now.weekday() < len(ukr_wd_short) else 0]
            date_lbl.value = f"{wd}  {now:%d.%m.%Y}"
            page.update(); await asyncio.sleep(1)
    page.run_task(_clock)

    version_text = ft.Text(f"v{read_local_version()}", size=14, weight="bold", color="#22c55e")
    async def _version_poller():
        prev = None
        while True:
            cur = read_local_version()
            if cur != prev: version_text.value = f"v{cur}"; page.update(); prev = cur
            await asyncio.sleep(5)
    page.run_task(_version_poller)

    async def _notes_notifier():
        last_tick = None
        while True:
            today_iso = _dt.date.today().isoformat()
            if today_iso != last_tick:
                rows = notes_list(today_iso)
                if rows:
                    _update_unread_from_rows(rows)
                    lines = [r.get("text","").strip() for r in rows if r.get("text")]
                    present_card("Нагадування на сьогодні", lines, on_close=None)
                    mark_notified_today(today_iso)
                last_tick = today_iso
            await asyncio.sleep(60)
    page.run_task(_notes_notifier)

    date_click = ft.GestureDetector(
        content=ft.Column([time_lbl, date_lbl], horizontal_alignment=ft.CrossAxisAlignment.END),
        mouse_cursor=ft.MouseCursor.CLICK,
        on_tap=_toggle_calendar,
    )

    right_bar = ft.Row([ft.Container(chip_control), date_click],
                       spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    title_row = ft.Row([ft.Text("Головне Меню", size=34, weight="bold", color="#22d3ee"),
                        ft.Container(version_text, padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                     border_radius=12, bgcolor="#111827")],
                       spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    header = ft.Row([ft.Container(title_row, padding=20), right_bar],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    tiles_meta = [
        ("База виробів",           "icons/product_base.png",        product_base_view),
        ("Моніторинг",             "icons/monitoring.png",          monitoring_view),
        ("Заявка на лиття",        "icons/casting_request.png",     casting_request_view),
        ("Лиття",                  "icons/casting.png",             casting_view),
        ("Сушка",                  "icons/drying-icons.png",        drying_view),
        ("К/Я Лиття",              "icons/casting_quality.png",     casting_quality_view),
        ("Обрізка",                "icons/trimming-icons.png",      trimming_view),
        ("Різка",                  "icons/cutting-icons.png",       cutting_view),
        ("Зачистка",               "icons/cleaning-icons.png",      cleaning_view),
        ("Фінальний К/Я",          "icons/final_quality-icons.png", final_quality_view),
        # ("Склад",                  "icons/warehouse.png",           warehouse_view),  # removed warehouse tile
    ]

    # --- великі прозорі іконки на картках ---
    def make_tile(lbl: str, icon_path: str, vf):
        icon_img = safe_img(icon_path, width=140, height=140)  # ~50% ширини картки
        icon_box = ft.Container(icon_img, padding=4, border_radius=16)  # без фону — PNG має бути прозорим
        title_view = ft.Text(lbl, size=22, weight="bold", color="#e2e8f0", no_wrap=True)
        content = ft.Row([icon_box, title_view], spacing=24,
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         alignment=ft.MainAxisAlignment.START)
        card = ft.Container(
            content=content,
            gradient=ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                       colors=["#161634", "#0e0e24"]),
            border_radius=18, padding=24, ink=True,
            on_click=lambda e: ((lambda view=_wrap_view(vf(page), lbl): (page.views.append(view), page.go(view.route)))()),
            animate=ft.Animation(220, "easeInOut"),
        )
        def _hover(e): card.scale = 1.05 if e.data == "true" else 1.0; card.update()
        card.on_hover = _hover
        return card

    def _wrap_view(v, title):
        if not isinstance(v, ft.View): v = ft.View(f"/{title}", controls=[v])
        v.appbar = ft.AppBar(leading=ft.IconButton(ft.icons.ARROW_BACK, on_click=back_to_root),
                             title=ft.Text(title), center_title=False, bgcolor="#0b0b1a", color="#e2e8f0")
        v.scroll = ft.ScrollMode.AUTO; return v

    tiles = [make_tile(*t) for t in tiles_meta]
    tiles_area = ft.Container(ft.ResponsiveRow([ft.Container(t, col={"sm":12,"md":6,"xl":4}, padding=10) for t in tiles]), padding=10)

    page.views.append(ft.View("/",
        controls=[header,
                  ft.Container(ft.Column([ft.Text("Оберіть розділ", size=22, weight="bold", color="#e2e8f0"), tiles_area],
                                         tight=True), padding=10)], scroll=ft.ScrollMode.AUTO))
    page.go("/")
    try: NotifBanner(page, user_key=disp)
    except Exception: pass

# ========= ENTRY =========
if __name__ == "__main__":
    ft.app(target=main, view=ft.AppView.FLET_APP)
