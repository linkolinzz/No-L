# pages/drying.py
# test comment inserted here
import flet as ft
import datetime, asyncio, threading, concurrent.futures
from database.db_manager import connect_db
import compat

TIMER_MINUTES = 1010  # 16 год 50 хв

# ── сумісність із Flet 0.28 ──
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons
if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
    ft.colors = ft.Colors

# ─────────────────── GLOBAL ASYNC LOOP ───────────────────
ASYNC_LOOP: asyncio.AbstractEventLoop | None = None
def ensure_async_loop():
    global ASYNC_LOOP
    if ASYNC_LOOP and ASYNC_LOOP.is_running():
        return ASYNC_LOOP
    ASYNC_LOOP = asyncio.new_event_loop()
    threading.Thread(target=ASYNC_LOOP.run_forever, daemon=True).start()
    return ASYNC_LOOP
ensure_async_loop()

# ─────────────────── DB helpers ───────────────────
def db_fetch(sql, p=None):
    with connect_db() as cn:
        cu = cn.cursor(dictionary=True)
        cu.execute(sql, p or ())
        return cu.fetchall()
def db_exec(sql, p=None):
    with connect_db() as cn:
        cu = cn.cursor()
        cu.execute(sql, p or ())
        cn.commit()
