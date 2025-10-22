# monitoring_cards/stage_cards.py
# -*- coding: utf-8 -*-

import asyncio, threading
import flet as ft
from typing import List, Optional

from database.db_manager import db_fetch
from utils.logger import log

# Деталі по етапах
from monitoring_cards.details.casting_details import show_casting_details
from monitoring_cards.details.drying_details import show_drying_details
from monitoring_cards.details.casting_quality_details import show_casting_quality_details
from monitoring_cards.details.trimming_details import show_trimming_details
from monitoring_cards.details.cutting_details import show_cutting_details
from monitoring_cards.details.cleaning_details import show_cleaning_details
from monitoring_cards.details.final_quality_details import show_final_quality_details


STAGES = [
    ("Лиття",         "casting",         "casting",         "quantity",            None,                 "hatian-icons1.png"),
    ("Сушка",         "drying",          "drying",          "qty",                 "drying_needed",      "drying-icons.png"),
    ("К/Я Лиття",     "casting_quality", "casting_quality", "accepted_quantity",   None,                 "casting_quality.png"),
    ("Обрізка",       "trimming",        "trimming",        "processed_quantity",  "trimming_needed",    "trimming-icons.png"),
    ("Різка",         "cutting",         "cutting",         "processed_quantity",  "cutting_needed",     "cutting-icons.png"),
    ("Зачистка",      "cleaning",        "cleaning",        "processed_quantity",  "cleaning_needed",    "cleaning-icons.png"),
    ("Фінальний К/Я", "final_quality",   "final_quality",   "accepted_quantity",   None,                 "final_quality-icons.png"),
]

# лишено для сумісності (не використовуємо «Брак» у відображенні)
DEFECT_COLS = {
    "casting":         "defect_quantity",
    "casting_quality": "defect_quantity",
    "trimming":        "defect_quantity",
    "cutting":         "defect_quantity",
    "cleaning":        "defect_quantity",
}

DETAIL_DISPATCH = {
    "casting":         show_casting_details,
    "drying":          show_drying_details,
    "casting_quality": show_casting_quality_details,
    "trimming":        show_trimming_details,
    "cutting":         show_cutting_details,
    "cleaning":        show_cleaning_details,
    "final_quality":   show_final_quality_details,
}

# ───────── helpers ─────────
class _NullPage:
    def __getattr__(self, _):
        def _noop(*a, **k):  # noqa: ANN001
            return None
        return _noop

def _safe_sum(sql: str, params: tuple) -> int:
    try:
        row = db_fetch(sql, params)[0]
        v = row.get("v") if "v" in row else (row.get("total") or row.get("need") or row.get("good") or row.get("c"))
        return int(v or 0)
    except Exception:
        return 0

def _placeholder(request_number: str) -> List[ft.Control]:
    text = (
        "Введіть номер заявки, щоб побачити прогрес по етапах."
        if not request_number else f"Немає даних для заявки: {request_number}"
    )
    return [
        ft.Container(
            bgcolor="#1E1F22",
            border_radius=12,
            padding=24,
            content=ft.Column(
                [
                    ft.Text("Моніторинг етапів", size=18, weight=ft.FontWeight.W_600),
                    ft.Text(text, size=14, color="#A0A0B0"),
                ],
                tight=True, spacing=8,
            ),
        )
    ]

def _metric_col(label: str, value: str, color_value: str) -> ft.Column:
    return ft.Column(
        spacing=2,
        horizontal_alignment=ft.CrossAxisAlignment.END,
        controls=[
            ft.Text(label, size=12, color="#A0A0B0", no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(value, size=14, color=color_value, weight="w600", no_wrap=True),
        ],
    )

def _articles_for_stage(request_number: str, flag: Optional[str]) -> list[dict]:
    """Повертає список виробів у заявці для даного етапу (лише код+назва, без кількостей)."""
    if flag:
        return db_fetch(
            """
            SELECT DISTINCT cr.article_code AS code, COALESCE(pb.name,'') AS name
              FROM casting_requests cr
              JOIN product_base pb ON pb.article_code = cr.article_code
             WHERE cr.request_number=%s AND pb.""" + flag + """=1
             ORDER BY code
            """,
            (request_number,),
        )
    else:
        return db_fetch(
            """
            SELECT DISTINCT cr.article_code AS code, COALESCE(pb.name,'') AS name
              FROM casting_requests cr
              LEFT JOIN product_base pb ON pb.article_code = cr.article_code
             WHERE cr.request_number=%s
             ORDER BY code
            """,
            (request_number,),
        )

def _plain_articles_block(request_number: str, flag: Optional[str]) -> ft.Column:
    """Текстовий список під заголовком 'Артикул\\Найменування' — без підв’язок і кількостей."""
    items = _articles_for_stage(request_number, flag)
    rows: List[ft.Control] = [
        ft.Text("Артикул\\Найменування", size=12, color="#A0A0B0", no_wrap=True),
    ]
    MAX_LINES = 7
    if not items:
        rows.append(ft.Text("—", size=12, color="#94A3B8", no_wrap=True))
    else:
        for i, r in enumerate(items):
            if i >= MAX_LINES:
                rows.append(ft.Text(f"… та ще {len(items) - MAX_LINES}", size=12, color="#94A3B8", no_wrap=True))
                break
            label = f"{r['code']} — {r.get('name') or ''}".strip()
            rows.append(
                ft.Text(
                    label, size=12, color="#CBD5E1",
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True,
                )
            )
    return ft.Column(rows, spacing=2)


# ───── таймер «Сушка» ─────
ASYNC_LOOP: asyncio.AbstractEventLoop | None = None
def _ensure_async_loop():
    global ASYNC_LOOP
    if ASYNC_LOOP and ASYNC_LOOP.is_running():
        return ASYNC_LOOP
    ASYNC_LOOP = asyncio.new_event_loop()
    threading.Thread(target=ASYNC_LOOP.run_forever, daemon=True).start()
    return ASYNC_LOOP

def _drying_min_remaining_minutes() -> Optional[int]:
    row = db_fetch(
        "SELECT MIN(TIMESTAMPDIFF(MINUTE,NOW(),end_time)) AS m "
        "FROM drying WHERE end_time IS NOT NULL AND NOW() < end_time"
    )
    return row[0]["m"] if row and row[0]["m"] is not None else None

def _fmt_left(mins: Optional[int]) -> str:
    if mins is None or mins <= 0:
        return "Готово"
    h = mins // 60
    m = mins % 60
    return f"Залишилось: {h} год {m:02d} хв"


# ───── public API ─────
def calculate_progress(request_number: str) -> int:
    total = _safe_sum("SELECT SUM(quantity) AS v FROM casting_requests WHERE request_number=%s", (request_number,))
    if total == 0:
        return 0
    accepted = _safe_sum("SELECT SUM(accepted_quantity) AS v FROM final_quality WHERE request_number=%s", (request_number,))
    return min(int(accepted / total * 100), 100)

def get_active_stages(request_number: str) -> list[str]:
    active: list[str] = []
    for name, key, table, expr, flag, _ in STAGES:
        if flag:
            need = _safe_sum(
                f"""
                SELECT SUM(cr.quantity) AS v
                FROM casting_requests cr
                JOIN product_base pb ON pb.article_code = cr.article_code
                WHERE cr.request_number=%s AND pb.{flag}=1
                """,
                (request_number,),
            )
        else:
            need = _safe_sum("SELECT SUM(quantity) AS v FROM casting_requests WHERE request_number=%s", (request_number,))
        good = _safe_sum(f"SELECT SUM({expr}) AS v FROM {table} WHERE request_number=%s", (request_number,))
        if need > 0 and good < need:
            active.append(name)
    return active


def build_all_stage_cards(request_number: Optional[str] = None, page: Optional[ft.Page] = None) -> List[ft.Container]:
    req = (request_number or "").strip()
    pg: ft.Page = page if page is not None else _NullPage()
    if not req:
        return _placeholder(req)

    log(f"[monitoring_cards] Building stage cards for {req}")
    cards: List[ft.Container] = []

    for name, key, table, expr, flag, icon in STAGES:
        # потреба
        if flag:
            need = _safe_sum(
                f"""
                SELECT SUM(cr.quantity) AS v
                FROM casting_requests cr
                JOIN product_base pb ON pb.article_code = cr.article_code
                WHERE cr.request_number=%s AND pb.{flag}=1
                """,
                (req,),
            )
        else:
            need = _safe_sum("SELECT SUM(quantity) AS v FROM casting_requests WHERE request_number=%s", (req,))
        if need == 0:
            continue

        # факт
        good = _safe_sum(f"SELECT SUM({expr}) AS v FROM {table} WHERE request_number=%s", (req,))
        pct = min(int((good / need) * 100), 100) if need else 0
        bar_color = "#10B981" if pct >= 80 else "#F59E0B" if pct >= 50 else "#EF4444"

        # блоки: простий список виробів + метрики
        products_col = _plain_articles_block(req, flag)
        metrics_col  = _metric_col("Потрібно\\Факт", f"{need}\\{good}", "#22D3EE")

        # таймер для «Сушка»
        timer_area: Optional[ft.Control] = None
        if key == "drying":
            timer_lbl = ft.Text(
                _fmt_left(_drying_min_remaining_minutes()),
                size=20, weight="bold", color="#F59E0B", no_wrap=True,
            )

            async def _tick():
                while True:
                    mm = _drying_min_remaining_minutes()
                    tv = _fmt_left(mm)
                    timer_lbl.value = tv
                    timer_lbl.color = "#10B981" if tv == "Готово" else "#F59E0B"
                    try:
                        pg.update()
                    except Exception:
                        pass
                    if tv == "Готово":
                        return
                    await asyncio.sleep(60)

            asyncio.run_coroutine_threadsafe(_tick(), _ensure_async_loop())
            timer_area = ft.Container(content=timer_lbl, padding=ft.padding.only(bottom=6))

        # картка
        cards.append(
            ft.Container(
                height=300,
                expand=True,
                col={"xs": 12, "sm": 6, "md": 6, "lg": 4},
                margin=8, padding=0, border_radius=12, bgcolor="#1E1F22",
                ink=True,
                on_click=(lambda e, k=key: DETAIL_DISPATCH[k](pg, req)) if page is not None else None,
                content=ft.ResponsiveRow(
                    spacing=0, run_spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            ft.Image(src=f"icons/{icon}", fit=ft.ImageFit.CONTAIN),
                            bgcolor="#16181B",
                            padding=12,
                            col={"xs": 4, "sm": 4, "md": 5, "lg": 5},
                            height=300,
                        ),
                        ft.Container(
                            padding=16,
                            col={"xs": 8, "sm": 8, "md": 7, "lg": 7},
                            content=ft.Column(
                                [
                                    ft.Text(name, size=18, weight="bold", color="#E2E8F0", no_wrap=True),
                                    ft.Row(
                                        [ft.ProgressBar(value=pct/100, height=4, expand=True, color=bar_color),
                                         ft.Text(f"{pct}%", size=14, color=bar_color, no_wrap=True)],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    *( [timer_area] if timer_area is not None else [] ),
                                    ft.ResponsiveRow(
                                        controls=[
                                            ft.Container(products_col, col={"xs": 12, "md": 8}),
                                            ft.Container(metrics_col,  col={"xs": 12, "md": 4}),
                                        ],
                                        spacing=8, run_spacing=6,
                                    ),
                                ],
                                spacing=10, tight=True,
                            ),
                        ),
                    ],
                ),
            )
        )

    return cards or _placeholder(req)
