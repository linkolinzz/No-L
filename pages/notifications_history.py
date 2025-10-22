# pages/notifications_history.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import flet as ft
from utils import notifications as notif


def view(page: ft.Page, user_key: str) -> ft.View:
    title = ft.Text("Історія повідомлень", size=28, weight="bold", color="#22d3ee")
    search = ft.TextField(label="Пошук по тексту", width=380, on_submit=lambda e: load(reset=True))
    list_col = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=8, expand=True)
    status_lbl = ft.Text("", size=12, color="#94a3b8")
    page_size_dd = ft.Dropdown(
        label="К-сть на сторінку",
        options=[ft.dropdown.Option(v) for v in (50, 100, 200)],
        value=100,
        on_change=lambda e: load(reset=True),
        width=180,
    )

    mark_all_btn = ft.TextButton("Позначити видимі як прочитані", icon=ft.icons.DONE_ALL)
    back_btn = ft.TextButton("Назад", icon=ft.icons.ARROW_BACK, on_click=lambda e: (page.views.pop(), page.update()))
    more_btn = ft.FilledButton("Показати ще", on_click=lambda e: load(reset=False))

    footer = ft.Row([back_btn, ft.Container(expand=True), more_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    offset = 0
    last_batch_ids: list[int] = []

    def _row_color(level: str | None, is_read: int) -> str:
        if not is_read:
            return "#e2e8f0"  # світліше для непрочитаних
        lvl = (level or "").lower()
        if lvl == "success":
            return "#86efac"
        if lvl == "warning":
            return "#fcd34d"
        if lvl == "error":
            return "#fca5a5"
        return "#94a3b8"

    def render_rows(rows):
        items = []
        for r in rows:
            msg = r.get("msg") or ""
            dt = r.get("dt")
            dt_txt = ""
            try:
                dt_txt = dt.strftime("%d.%m.%Y %H:%M") if dt else ""
            except Exception:
                dt_txt = str(dt or "")
            src = r.get("src") or ""
            level = r.get("level")
            is_read = int(r.get("is_read") or 0)
            color = _row_color(level, is_read)
            items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(dt_txt, size=12, color="#94a3b8"),
                                    ft.Container(width=10),
                                    ft.Text(f"[{src or 'app'}]", size=12, color="#94a3b8"),
                                    ft.Container(width=10),
                                    ft.Text(f"{level or 'info'}", size=12, color="#94a3b8"),
                                ],
                                spacing=6,
                            ),
                            ft.Text(msg, size=15, color=color, selectable=True),
                        ],
                        spacing=4,
                    ),
                    padding=12,
                    border_radius=10,
                    bgcolor="#0e0e24",
                )
            )
        return items

    def load(reset: bool):
        nonlocal offset, last_batch_ids
        if reset:
            offset = 0
            list_col.controls.clear()

        q = (search.value or "").strip() or None
        limit = int(page_size_dd.value or 100)
        rows = notif.history(user_key, q=q, limit=limit, offset=offset)
        last_batch_ids = [int(r["id"]) for r in rows] if rows else []
        list_col.controls.extend(render_rows(rows))
        offset += len(rows)
        status_lbl.value = f"Показано {offset} записів" if offset else "Немає записів"
        page.update()

    def _mark_visible(_):
        if not last_batch_ids:
            return
        notif.mark_read_by_user(last_batch_ids, user_key)
        # Оновлюємо поточні кольори без повторної вибірки
        load(reset=True)

    mark_all_btn.on_click = _mark_visible

    # початкове завантаження
    load(reset=True)

    return ft.View(
        "/notifications",
        controls=[
            ft.Container(
                ft.Row(
                    [title, ft.Container(expand=True), search, page_size_dd, mark_all_btn],
                    vertical_alignment="center",
                    spacing=12,
                ),
                padding=20,
            ),
            ft.Container(list_col, padding=ft.padding.only(left=20, right=20, bottom=10), expand=True),
            ft.Container(ft.Row([status_lbl], alignment=ft.MainAxisAlignment.END), padding=ft.padding.only(right=20)),
            ft.Container(footer, padding=20),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
