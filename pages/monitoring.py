# -*- coding: utf-8 -*-

import flet as ft
from database.db_manager import db_fetch
from utils.logger import log
import monitoring_cards.stage_cards as stage_cards
# Removed warehouse-related imports and constants since the "Склад" module is deprecated.


def monitoring_view(page: ft.Page) -> ft.View:
    log("[monitoring] Opening monitoring_view", tag="monitoring")

    # Яку верхню вкладку вибрати:
    #   0 — «Моніторинг»
    #   1 — «Передано на склад»
    #   2 — «Переміщення складу»
    # Always select the first tab since warehouse-related tabs are removed
    selected_top_tab = 0

    # Внутрішні вкладки: Активні та завершені заявки + активні етапи без заявки
    inner_tabs = [
        ft.Tab(text="Активні заявки",   content=_requests_view(page, active=True)),
        ft.Tab(text="Завершені заявки", content=_requests_view(page, active=False)),
        ft.Tab(text="Активні етапи",    content=_no_request_active_view(page)),
    ]

    tabs = ft.Tabs(
        selected_index=0,
        expand=1,
        tabs=[
            ft.Tab(
                text="Моніторинг",
                content=ft.Tabs(
                    selected_index=0,
                    expand=1,
                    tabs=inner_tabs,
                ),
            ),
        ],
    )

    return ft.View(
        route="/monitoring",
        controls=[
            ft.AppBar(
                leading=ft.IconButton(
                    icon=ft.icons.ARROW_BACK,
                    on_click=lambda e: _go_back_to_home(page)   # ← до головного меню
                ),
                title=ft.Text("Моніторинг заявок"),
                bgcolor="#1e40af",
            ),
            tabs,
        ],
        scroll=ft.ScrollMode.AUTO,
    )


# ─── helpers для попереднього вибору вкладки ──────────────────────────────────

def _resolve_preselected_tab(page: ft.Page) -> int:
    """Always return 0 as only the main monitoring tab is available."""
    return 0


# ─── back helpers ─────────────────────────────────────────────────────

def _go_back_one(page: ft.Page):
    """Повернутися на один екран назад (для деталей заявки)."""
    if len(page.views) > 1:
        page.views.pop()
        page.update()

def _go_back_to_home(page: ft.Page):
    """Очистити стек до головного меню (залишити root + home)."""
    while len(page.views) > 2:
        page.views.pop()
    page.update()


# ─── моніторингові списки ─────────────────────────────────────────────
# Фільтрація за фактичним % із calculate_progress():
#   active=True  -> показуємо лише ті, де pct < 100
#   active=False -> показуємо лише ті, де pct >= 100

def _requests_view(page: ft.Page, active: bool) -> ft.Column:
    # Беремо всі унікальні заявки (без фільтра по stage)
    rows = db_fetch(
        "SELECT DISTINCT request_number FROM casting_requests ORDER BY request_number DESC"
    )

    cards = []
    for r in rows:
        rn = r["request_number"]
        pct = stage_cards.calculate_progress(rn)  # фактичний % по final_quality
        # Фільтр за вкладкою
        if active and pct >= 100:
            continue
        if not active and pct < 100:
            continue

        stages = stage_cards.get_active_stages(rn)
        cards.append(_build_request_card(page, rn, stages, pct))

    if not cards:
        cards = [ft.Text("Немає заявок", color="#e2e8f0")]

    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.ResponsiveRow(
                controls=cards,
                spacing=12,
                run_spacing=12,
                expand=1,
            )
        ],
    )


def _build_request_card(page: ft.Page, rn: str, stages: list[str], pct: int) -> ft.Container:
    return ft.Container(
        bgcolor="#161634",
        border_radius=12,
        padding=16,
        margin=8,
        expand=True,
        col={"xs": 12, "sm": 12, "md": 6, "lg": 4},
        content=ft.Column(
            [
                ft.Text(f"Заявка №{rn}", size=18, weight="bold", color="#ffffff"),
                ft.Text("Етапи: " + ", ".join(stages), size=12, color="#a0a0b0"),
                ft.ProgressBar(value=pct / 100 if pct is not None else 0, width=200),
                ft.Text(f"{pct}% виконано", size=12, color="#22d3ee"),
                ft.ElevatedButton(
                    "Детальніше",
                    on_click=lambda e, req=rn: open_details(page, req),
                ),
            ],
            tight=True,
        ),
        ink=True,
    )


# ─── no-request monitoring ─────────────────────────────────────────────
def _no_request_active_view(page: ft.Page) -> ft.Column:
    """
    Повертає список активних етапів для виробів, відлитих без заявки.
    Активними вважаються ті, де потрібний етап не виконано (немає запису у відповідній таблиці).
    Виводимо картки з артикулом, назвою, переліком незавершених етапів та прогресом.
    """
    # зібрати всі артикули, що мають відливки без заявки
    article_rows = db_fetch(
        """
        SELECT co.article_code AS code, MAX(pb.name) AS name
          FROM casting_no_request co
          JOIN product_base pb ON pb.article_code = co.article_code
      GROUP BY co.article_code
      ORDER BY code
        """
    )
    cards: list[ft.Control] = []
    for ar in article_rows:
        code = ar["code"]
        name = ar.get("name") or ""
        # отримати прапорці необхідних етапів
        flags = db_fetch(
            "SELECT drying_needed, trimming_needed, cutting_needed, cleaning_needed FROM product_base WHERE article_code=%s",
            (code,),
        )
        if not flags:
            continue
        flag = flags[0]
        stages: list[str] = []
        # для кожного етапу перевірити наявність записів
        if flag.get("drying_needed"):
            cnt = db_fetch(
                "SELECT 1 FROM drying_no_request WHERE article_code=%s LIMIT 1",
                (code,),
            )
            if not cnt:
                stages.append("Сушка")
        if flag.get("trimming_needed"):
            cnt = db_fetch(
                "SELECT 1 FROM trimming_no_request WHERE article_code=%s LIMIT 1",
                (code,),
            )
            if not cnt:
                stages.append("Обрізка")
        if flag.get("cutting_needed"):
            cnt = db_fetch(
                "SELECT 1 FROM cutting_no_request WHERE article_code=%s LIMIT 1",
                (code,),
            )
            if not cnt:
                stages.append("Різка")
        if flag.get("cleaning_needed"):
            cnt = db_fetch(
                "SELECT 1 FROM cleaning_no_request WHERE article_code=%s LIMIT 1",
                (code,),
            )
            if not cnt:
                stages.append("Зачистка")
        # Фінальний КЯ завжди потрібен (для партій без заявки)
        cnt = db_fetch(
            "SELECT 1 FROM final_quality_no_request WHERE article_code=%s LIMIT 1",
            (code,),
        )
        if not cnt:
            stages.append("Фінальний К/Я")
        # якщо немає незавершених етапів — пропускаємо
        if not stages:
            continue
        # обчислити прогрес за accepted_quantity/final_quality
        good_total_row = db_fetch(
            "SELECT SUM(quantity - COALESCE(defect_quantity,0)) AS v FROM casting_no_request WHERE article_code=%s",
            (code,),
        )
        good_total = good_total_row[0].get("v") or 0
        accepted_row = db_fetch(
            "SELECT SUM(accepted_quantity) AS v FROM final_quality_no_request WHERE article_code=%s",
            (code,),
        )
        accepted = accepted_row[0].get("v") or 0
        pct = int(accepted / good_total * 100) if good_total else 0
        if pct > 100:
            pct = 100
        # побудувати картку
        cards.append(_build_no_request_card(page, code, name, stages, pct))
    if not cards:
        cards = [ft.Text("Немає активних етапів", color="#e2e8f0")]
    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.ResponsiveRow(
                controls=cards,
                spacing=12,
                run_spacing=12,
                expand=1,
            )
        ],
    )


def _build_no_request_card(page: ft.Page, code: str, name: str, stages: list[str], pct: int) -> ft.Container:
    """Побудувати картку для виробів без заявки."""
    return ft.Container(
        bgcolor="#161634",
        border_radius=12,
        padding=16,
        margin=8,
        expand=True,
        col={"xs": 12, "sm": 12, "md": 6, "lg": 4},
        content=ft.Column(
            [
                ft.Text(f"Без заявки: {code}", size=18, weight="bold", color="#ffffff"),
                ft.Text(name or "-", size=12, color="#a0a0b0"),
                ft.Text("Етапи: " + ", ".join(stages), size=12, color="#a0a0b0"),
                ft.ProgressBar(value=pct / 100 if pct else 0, width=200),
                ft.Text(f"{pct}% виконано", size=12, color="#22d3ee"),
            ],
            tight=True,
        ),
        ink=True,
    )


def open_details(page: ft.Page, request_number: str):
    log(f"[monitoring] Open details for {request_number}", tag="monitoring")
    cards = stage_cards.build_all_stage_cards(request_number, page)

    detail_view = ft.View(
        route=f"/monitoring/{request_number}",
        controls=[
            ft.AppBar(
                leading=ft.IconButton(
                    icon=ft.icons.ARROW_BACK,
                    on_click=lambda e: _go_back_one(page)   # ← назад до списку моніторингу
                ),
                title=ft.Text(f"Заявка №{request_number} — Етапи"),
                bgcolor="#1e40af",
            ),
            ft.Container(
                ft.Text("Моніторинг етапів", size=20, weight="bold"),
                padding=10,
            ),
            ft.ResponsiveRow(
                controls=cards,
                spacing=12,
                run_spacing=12,
                expand=1,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
    page.views.append(detail_view)
    page.update()
