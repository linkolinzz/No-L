# pages/monitoring_warehouse_moves.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta

import flet as ft
from database.db_manager import db_exec, db_fetch

# опціональний лог
try:
    from utils.logger import log
except Exception:  # noqa: E722
    def log(msg, tag="moves"):  # type: ignore
        print(f"[{tag}] {msg}")


# ───────────── helpers ─────────────

def _fmt_dt(val) -> str:
    if not val:
        return ""
    if isinstance(val, (datetime, date)):
        try:
            return val.strftime("%d.%m.%Y %H:%M")
        except Exception:  # noqa: E722
            return val.strftime("%d.%m.%Y")
    try:
        s = str(val).replace("Z", "").split(".")[0]
        return datetime.fromisoformat(s).strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: E722
        return str(val)


def _fmt_int(x) -> str:
    try:
        return f"{int(x):,}".replace(",", " ")
    except Exception:  # noqa: E722
        return str(x or 0)


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:  # noqa: E722
        return None


def _extract_rn_from_query(q: str) -> str | None:
    if not q:
        return None
    m = re.search(r"(?:^|[^0-9])([0-9]{1,8})(?:[^0-9]|$)", q.strip())
    return m.group(1) if m else None


def _where_out_and_params(d_from: str, d_to: str, q_text: str):
    """
    WHERE лише для ВІДВАНТАЖЕННЯ (qty<0) без undo.
    Пошук q_text одночасно по: article_code, product_name, operator_name, reason;
    якщо з рядка витягнувся номер заявки — додаємо точне співпадіння по request_number.
    """
    where = [
        "w.qty < 0",
        "NOT EXISTS (SELECT 1 FROM warehouse_moves u "
        "             WHERE u.source_table='undo_out' AND u.source_id = w.id)"
    ]
    params: list = []

    f = _parse_date(d_from)
    t = _parse_date(d_to)
    if f:
        where.append("w.move_time >= %s")
        params.append(datetime.combine(f, datetime.min.time()))
    if t:
        where.append("w.move_time <= %s")
        params.append(datetime.combine(t, datetime.max.time()))

    q = (q_text or "").strip()
    if q:
        like = f"%{q}%"
        # група з OR
        where.append("(" + " OR ".join([
            "w.article_code LIKE %s",
            "w.product_name LIKE %s",
            "w.operator_name LIKE %s",
            "w.reason LIKE %s",
        ]) + ")")
        params.extend([like, like, like, like])

        rn = _extract_rn_from_query(q)
        if rn:
            where.append("w.request_number = %s")
            params.append(rn)

    return " AND ".join(where), tuple(params)


# ───────────── main view ─────────────

def warehouse_moves_view(page: ft.Page) -> ft.Row:
    log("[monitoring_moves] open", tag="monitoring")
    today = datetime.now().date()

    last_moves_csv: list[list] = []

    # ── Фільтри (ліва панель, компакт як на скрінах)
    tf_from = ft.TextField(
        label="Від",
        value=str(today - timedelta(days=30)),
        width=140,
        dense=True,
        autofocus=False,
        filled=True,
        bgcolor="#0b1220",
        border_radius=8,
    )
    tf_to = ft.TextField(
        label="До",
        value=str(today),
        width=140,
        dense=True,
        filled=True,
        bgcolor="#0b1220",
        border_radius=8,
    )
    tf_limit = ft.TextField(
        label="Ліміт",
        value="300",
        width=90,
        dense=True,
        filled=True,
        bgcolor="#0b1220",
        border_radius=8,
        input_filter=ft.InputFilter(regex_string=r"[0-9]", allow=True),
    )

    tf_query = ft.TextField(
        label="Пошук (№ заявки / артикул / назва / ПІБ / коментар)",
        hint_text="Напр., 102 або ЖБ-001 або Іваненко",
        dense=True,
        filled=True,
        bgcolor="#0b1220",
        border_radius=8,
        prefix_icon=ft.icons.SEARCH,
        width=300,
        on_submit=lambda e: _apply(),  # Enter одразу застосовує
    )

    # кнопки швидких діапазонів
    def _set_range(mode: str):
        d_to = today
        if mode == "today":
            d_from = d_to
        elif mode == "week":
            d_from = d_to - timedelta(days=7)
        elif mode == "month":
            d_from = d_to - timedelta(days=30)
        elif mode == "this_month":
            d_from = today.replace(day=1)
        else:
            return
        tf_from.value, tf_to.value = str(d_from), str(d_to)
        page.update()
        _apply()

    quick_buttons = ft.Row(
        controls=[
            ft.TextButton("Сьогодні", on_click=lambda e: _set_range("today")),
            ft.TextButton("7 днів", on_click=lambda e: _set_range("week")),
            ft.TextButton("30 днів", on_click=lambda e: _set_range("month")),
            ft.TextButton("Цей місяць", on_click=lambda e: _set_range("this_month")),
        ],
        spacing=6,
        wrap=True,
    )

    btn_apply = ft.ElevatedButton(
        "Застосувати", icon=ft.icons.SEARCH, on_click=lambda e: _apply(),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
    )
    btn_clear = ft.OutlinedButton(
        "Очистити", icon=ft.icons.CLEAR_ALL,
        on_click=lambda e: _reset_filters(),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))
    )

    # Заголовок фільтрів з розгортанням
    filters_open = True

    chevron = ft.Icon(ft.icons.EXPAND_LESS, size=18, color="#9ca3af")
    def _toggle_filters(_=None):
        nonlocal filters_open
        filters_open = not filters_open
        chevron.name = ft.icons.EXPAND_LESS if filters_open else ft.icons.EXPAND_MORE
        filters_body.visible = filters_open
        filters_title.tooltip = "Згорнути" if filters_open else "Розгорнути"
        page.update()

    filters_title = ft.Row(
        [
            ft.Icon(ft.icons.TUNE, color="#93c5fd"),
            ft.Text("Фільтри", size=16, weight="bold"),
            ft.Container(expand=True),
            ft.IconButton(icon=chevron.name, tooltip="Згорнути", on_click=_toggle_filters, icon_color="#9ca3af", icon_size=20),
        ],
        vertical_alignment="center",
    )

    # Тіло фільтрів
    filters_body = ft.Column(
        controls=[
            ft.Row([tf_from, tf_to, tf_limit], spacing=8),
            quick_buttons,
            tf_query,
            ft.Row([btn_apply, btn_clear], spacing=8),
        ],
        spacing=8,
        tight=True,
        visible=filters_open,
    )

    filters_card = ft.Container(
        content=ft.Column([filters_title, ft.Divider(opacity=0.2), filters_body], spacing=6, tight=True),
        padding=12,
        bgcolor="#0b0f1a",
        border=ft.border.all(1, "#111827"),
        border_radius=12,
        width=360,
    )

    # ── Права панель: заголовок + лічильник + експорт + таблиця
    count_text = ft.Text("", color="#94a3b8")
    error_box = ft.Text("", color="#f87171")

    tbl_moves = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Час")),
            ft.DataColumn(ft.Text("Заявка")),
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Найменування")),
            ft.DataColumn(ft.Text("К-сть")),
            ft.DataColumn(ft.Text("ПІБ Робітника")),
            ft.DataColumn(ft.Text("Коментар")),
            ft.DataColumn(ft.Text("Дія")),
        ],
        rows=[],
        expand=True,
        heading_row_height=44,
        data_row_max_height=56,
        column_spacing=16,
    )

    # Експорт CSV
    file_saver = ft.FilePicker()
    if file_saver not in page.overlay:
        page.overlay.append(file_saver)

    def _export_moves():
        if not last_moves_csv:
            return
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Час", "Заявка", "Артикул", "Найменування", "К-сть", "ПІБ Робітника", "Коментар"])
        for r in last_moves_csv:
            w.writerow(r)
        content = buf.getvalue().encode("utf-8-sig")

        def _on_res(e: ft.FilePickerResultEvent):
            if e.path:
                with open(e.path, "wb") as f:
                    f.write(content)

        file_saver.on_result = _on_res
        file_saver.save_file(file_name="Відвантаження_зі_складу.csv")

    btn_export = ft.OutlinedButton(
        "Експорт (Рухи)",
        icon=ft.icons.DOWNLOAD_FOR_OFFLINE,
        on_click=lambda e: _export_moves()
    )

    header = ft.Row(
        controls=[
            ft.Text("Переміщення складу — Відвантаження", size=18, weight="bold"),
            ft.Row([count_text, btn_export], spacing=12),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    right_column = ft.Column(
        controls=[header, error_box, tbl_moves],
        expand=True,
        spacing=8,
    )

    # ───────────── core actions ─────────────

    def _undo(rec_id: int):
        def _do():
            already = db_fetch(
                "SELECT 1 FROM warehouse_moves WHERE source_table='undo_out' AND source_id=%s LIMIT 1",
                (rec_id,),
            )
            if already:
                page.snack_bar = ft.SnackBar(ft.Text("Відвантаження вже скасовано"), open=True)
                page.update()
                return

            rows = db_fetch("SELECT * FROM warehouse_moves WHERE id=%s", (rec_id,))
            if not rows:
                return
            r = rows[0]
            if (r.get("qty") or 0) < 0:
                db_exec(
                    """
                    INSERT INTO warehouse_moves
                        (request_number, article_code, product_name, qty, reason, operator_name,
                         source_table, source_id)
                    VALUES (%s,%s,%s,%s,%s,%s,'undo_out',%s)
                    """,
                    (
                        r.get("request_number"),
                        r["article_code"],
                        r["product_name"],
                        abs(int(r["qty"] or 0)),
                        f"Скасування відвантаження (undo) id={rec_id}",
                        r.get("operator_name"),
                        rec_id,
                    ),
                )
            _apply()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Підтвердження"),
            content=ft.Text(f"Скасувати відвантаження ID {rec_id}?"),
            actions=[
                ft.TextButton("Ні", on_click=lambda e: _close(False)),
                ft.TextButton("Так", style=ft.ButtonStyle(color=ft.colors.RED),
                              on_click=lambda e: _close(True)),
            ],
        )

        def _close(ok: bool):
            dlg.open = False
            page.update()
            if ok:
                _do()

        page.dialog = dlg
        if dlg not in page.overlay:
            page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def _apply():
        error_box.value = ""
        try:
            try:
                lim = int((tf_limit.value or "300").strip())
            except ValueError:
                lim = 300
                tf_limit.value = "300"

            where_sql, params = _where_out_and_params(
                tf_from.value, tf_to.value, tf_query.value
            )

            rows = db_fetch(
                f"""
                SELECT w.id, w.move_time, w.request_number, w.article_code, w.product_name,
                       ABS(w.qty) AS qty_abs, w.operator_name, w.reason
                  FROM warehouse_moves w
                 WHERE {where_sql}
                 ORDER BY w.move_time DESC, w.id DESC
                 LIMIT %s
                """,
                params + (lim,),
            )

            tbl_moves.rows.clear()
            last_moves_csv.clear()

            for r in rows:
                when = _fmt_dt(r.get("move_time"))
                rn   = r.get("request_number") or ""
                art  = r.get("article_code") or ""
                name = r.get("product_name") or ""
                qty  = r.get("qty_abs") or 0
                oper = r.get("operator_name") or ""
                reas = r.get("reason") or ""

                tbl_moves.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(when)),
                            ft.DataCell(ft.Text(rn or "—")),
                            ft.DataCell(ft.Text(art)),
                            ft.DataCell(ft.Text(name)),
                            ft.DataCell(ft.Text(_fmt_int(qty), color="#ef4444")),
                            ft.DataCell(ft.Text(oper or "—")),
                            ft.DataCell(ft.Text(reas or "—")),
                            ft.DataCell(
                                ft.IconButton(
                                    icon=ft.icons.REPLAY,
                                    tooltip="Скасувати (undo)",
                                    on_click=lambda e, rid=r["id"]: _undo(rid),
                                )
                            ),
                        ]
                    )
                )
                last_moves_csv.append([when, rn, art, name, qty, oper, reas])

            count_text.value = f"Записів: {len(rows)}"
        except Exception as ex:  # noqa: E722
            error_box.value = f"Помилка завантаження: {ex}"
            log(f"moves load error: {ex}", tag="monitoring")

        page.update()

    def _reset_filters():
        tf_from.value = str(today - timedelta(days=30))
        tf_to.value = str(today)
        tf_query.value = ""
        tf_limit.value = "300"
        count_text.value = ""
        error_box.value = ""
        tbl_moves.rows.clear()
        page.update()

    # первинне завантаження
    _apply()

    # повертаємо так само, як у pages/monitoring_warehouse.py
    return ft.Row(
        controls=[
            ft.Container(filters_card, padding=10, width=380),
            ft.VerticalDivider(width=1),
            ft.Container(right_column, expand=True, padding=10),
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
