# components/notif_banner.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import flet as ft
from utils import notifications as notif


def _bg_for_level(level: str | None) -> str:
    lvl = (level or "").lower()
    if lvl == "success":
        return "#064e3b"  # emerald-900
    if lvl == "warning":
        return "#78350f"  # amber-900
    if lvl == "error":
        return "#7f1d1d"  # red-900
    return "#0b1a2a"      # default (blueish dark)


def NotifBanner(page: ft.Page, *, user_key: str):
    """
    Банер системних повідомлень (src='banner'), що показується 1 раз для кожного користувача.
    Автоперевірка кожні 10 секунд.
    """
    banner = ft.Banner(
        bgcolor="#0b1a2a",
        content=ft.Text("", size=16, selectable=True),
        actions=[],
        leading=ft.Icon(ft.icons.CAMPAIGN, size=22),
    )
    page.banner = banner

    async def _poll():
        while True:
            rows = notif.unread_of_source(user_key, src_value="banner", limit=1)
            if rows:
                r = rows[0]
                msg = r.get("msg", "") or ""
                level = r.get("level")
                nid = int(r["id"])
                banner.bgcolor = _bg_for_level(level)
                banner.content = ft.Text(msg, size=16, selectable=True)
                # Кнопки дій
                def _close_and_mark(_):
                    notif.mark_read_by_user([nid], user_key)
                    banner.open = False
                    page.update()

                banner.actions = [
                    ft.TextButton("Закрити", on_click=_close_and_mark),
                ]
                banner.open = True
                page.update()
            await asyncio.sleep(10)

    page.run_task(_poll)
