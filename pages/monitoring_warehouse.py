# pages/monitoring_warehouse.py
from __future__ import annotations

from datetime import datetime, timedelta, date
import re
import csv
import io
import flet as ft
from database.db_manager import db_fetch


# ─────────────────── helpers: безпечна робота з № заявки ───────────────────

def _norm_rn(v) -> str | None:
    """Повернути нормалізований номер заявки як РЯДОК або None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _safe_union_sorted_keys(*dicts) -> list[str]:
    """
    Об'єднати ключі словників, прибрати None, відсортувати за рядком у зворотному порядку.
    Уніфіковано, щоб не падати на порівнянні str ↔ NoneType.
    """
    keys = set()
    for d in dicts:
        try:
            keys |= set(d.keys())
        except Exception:
            pass
    clean = [k for k in keys if _norm_rn(k) is not None]
    return sorted((str(k) for k in clean), key=str, reverse=True)


# ─────────────────── інші утиліти ───────────────────

def _fmt_int(x):
    try:
        return f"{int(x):,}".replace(",", " ")
    except Exception:
        return str(x or 0)


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _extract_rn_from_query(q: str) -> str | None:
    """
    Якщо в рядку є № заявки — повертаємо номер (рядком).
    Підтримує '102', '#102', '№102', 'rn:102', 'request 102' тощо.
    Беремо першу групу з послідовністю цифр довжиною 1..8.
    """
    if not q:
        return None
    m = re.search(r"(?:^|[^0-9])([0-9]{1,8})(?:[^0-9]|$)", q.strip())
    return m.group(1) if m else None


def _fmt_when(v) -> str:
    """Безпечне форматування часу руху у вигляді 'дд.мм.рррр гг:хх'."""
    if not v:
        return "—"
    try:
        if isinstance(v, datetime):
            dt = v
        else:
            s = str(v)
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    dt = None
            if dt is None:
                return s  # показати як є
        # УВАГА: тут саме латинська m → "%m"
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(v)


# ─────────────────── ГОЛОВНИЙ В'Ю ───────────────────

def warehouse_view(page: ft.Page) -> ft.Row:
    today = datetime.now().date()

    selected_request: str | None = None
    last_articles_csv: list[list] = []
    last_moves_csv: list[list] = []

    # ── Фільтри
    tf_from = ft.TextField(label="Від", value=str(today - timedelta(days=30)), width=140)
    tf_to   = ft.TextField(label="До",  value=str(today), width=140)
    tf_search = ft.TextField(
        label="Пошук (№ заявки / артикул / назва)",
        prefix_icon=ft.icons.SEARCH,
        width=300,
        on_submit=lambda e: _apply_filters(),
    )
    cb_only_need = ft.Checkbox(label="Лише із потребою", value=False, on_change=lambda e: _apply_filters())

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
        _apply_filters()

    quick_buttons = ft.Row(
        controls=[
            ft.ElevatedButton("Сьогодні",  on_click=lambda e: _set_range("today")),
            ft.ElevatedButton("7 днів",     on_click=lambda e: _set_range("week")),
            ft.ElevatedButton("30 днів",    on_click=lambda e: _set_range("month")),
            ft.ElevatedButton("Цей місяць", on_click=lambda e: _set_range("this_month")),
        ],
        spacing=6, wrap=True,
    )

    btn_apply = ft.ElevatedButton("Застосувати", icon=ft.icons.FILTER_ALT, on_click=lambda e: _apply_filters())
    btn_clear = ft.OutlinedButton(
        "Очистити", icon=ft.icons.CLEAR_ALL,
        on_click=lambda e: (_reset_filters(), _apply_filters())
    )

    filters_inner = ft.Column(
        controls=[
            ft.Row([tf_from, tf_to], spacing=8),
            quick_buttons,
            tf_search,
            cb_only_need,
            ft.Row([btn_apply, btn_clear], spacing=8),
        ],
        spacing=8, tight=True,
    )
    filters_container = ft.Container(content=filters_inner, padding=10, bgcolor="#0b1220",
                                     border_radius=10, visible=False)

    def _toggle_filters(e=None):
        filters_container.visible = not filters_container.visible
        toggle_btn.icon = ft.icons.KEYBOARD_ARROW_UP if filters_container.visible else ft.icons.KEYBOARD_ARROW_DOWN
        page.update()

    toggle_btn = ft.IconButton(icon=ft.icons.KEYBOARD_ARROW_DOWN, on_click=_toggle_filters,
                               tooltip="Показати/сховати фільтри")
    filters_header = ft.Row(
        controls=[ft.Text("Фільтри", size=16, weight="bold"), toggle_btn],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    # ── Ліва колонка: список заявок
    requests_count = ft.Text("0 заявок", color="#94a3b8")
    left_title = ft.Row(
        controls=[ft.Text("Заявки", size=16, weight="bold"), requests_count],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    list_requests = ft.ListView(expand=True, spacing=8, auto_scroll=False, padding=0)

    left_column = ft.Column(
        controls=[filters_header, filters_container, ft.Divider(), left_title, list_requests],
        expand=False, width=380, spacing=8,
    )

    # ── Права колонка: деталі
    details_title = ft.Text("Деталі заявки", size=16, weight="bold")
    summary_row   = ft.Row(spacing=16)

    tbl_by_article = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Найменування")),
            ft.DataColumn(ft.Text("План")),
            ft.DataColumn(ft.Text("Передано")),
            ft.DataColumn(ft.Text("Потреба")),
            ft.DataColumn(ft.Text("Прогрес")),
        ],
        rows=[], expand=True,
    )
    tbl_moves = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Час")),
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Найменування")),
            ft.DataColumn(ft.Text("К-сть")),
            ft.DataColumn(ft.Text("ПІБ Робітника")),
            ft.DataColumn(ft.Text("Коментар")),
        ],
        rows=[], expand=True,
    )

    # Експорт
    file_saver = ft.FilePicker()
    page.overlay.append(file_saver)

    def _export_csv(filename: str, header: list[str], rows: list[list]):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
        content = buf.getvalue().encode("utf-8-sig")

        def _on_res(e: ft.FilePickerResultEvent):
            if e.path:
                with open(e.path, "wb") as f:
                    f.write(content)

        file_saver.on_result = _on_res
        file_saver.save_file(file_name=filename)

    btn_export_articles = ft.OutlinedButton("Експорт (Артикул)",
                                            icon=ft.icons.DOWNLOAD,
                                            on_click=lambda e: _export_articles())
    btn_export_moves = ft.OutlinedButton("Експорт (Рухи)",
                                         icon=ft.icons.DOWNLOAD_FOR_OFFLINE,
                                         on_click=lambda e: _export_moves())

    right_column = ft.Column(
        controls=[
            details_title,
            summary_row,
            ft.Row([btn_export_articles, btn_export_moves], spacing=8),
            tbl_by_article,
            ft.Divider(),
            ft.Text("Останні рухи"),
            tbl_moves,
        ],
        expand=True, spacing=8,
    )

    # ─────────────────── core helpers ───────────────────

    def _reset_filters():
        tf_from.value = str(today - timedelta(days=30))
        tf_to.value   = str(today)
        tf_search.value = ""
        cb_only_need.value = False
        page.update()

    def _where_recv_and_params():
        """
        Повертає: where_sql, params, request_only
        Якщо у пошуку впізнано № заявки — request_only = '102' і
        SQL для warehouse_moves отримає фільтр "AND request_number = %s" (а не LIKE).
        """
        f = _parse_date(tf_from.value)
        t = _parse_date(tf_to.value)
        q = (tf_search.value or "").strip()
        request_only = _extract_rn_from_query(q)

        params = []
        where = "WHERE qty > 0"
        if f:
            where += " AND move_time >= %s"; params.append(datetime.combine(f, datetime.min.time()))
        if t:
            where += " AND move_time <= %s"; params.append(datetime.combine(t, datetime.max.time()))

        if request_only:
            where += " AND request_number = %s"; params.append(request_only)
        elif q:
            like = f"%{q}%"
            where += " AND (request_number LIKE %s OR article_code LIKE %s OR product_name LIKE %s)"
            params.extend([like, like, like])

        return where, tuple(params), request_only

    # ── побудова списку заявок
    def _load_master():
        nonlocal selected_request

        where_recv, params, request_only = _where_recv_and_params()

        # План по заявках (нормалізуємо ключі)
        if request_only:
            plan_rows = db_fetch(
                "SELECT request_number, SUM(quantity) AS plan_qty "
                "FROM casting_requests WHERE request_number = %s GROUP BY request_number",
                (request_only,)
            )
        else:
            plan_rows = db_fetch(
                "SELECT request_number, SUM(quantity) AS plan_qty "
                "FROM casting_requests GROUP BY request_number"
            )
        plan: dict[str, int] = {}
        for r in plan_rows:
            k = _norm_rn(r.get("request_number"))
            if k is not None:
                plan[k] = r.get("plan_qty") or 0

        # Передано по заявках (з урахуванням фільтрів; ключі нормалізуємо)
        recv_rows = db_fetch(
            f"SELECT request_number, SUM(qty) AS recv_qty "
            f"FROM warehouse_moves {where_recv} GROUP BY request_number",
            params
        )
        recv: dict[str, int] = {}
        for r in recv_rows:
            k = _norm_rn(r.get("request_number"))
            if k is not None:
                recv[k] = r.get("recv_qty") or 0

        # Перелік заявок: безпечне об'єднання/сортування
        all_rn = _safe_union_sorted_keys(plan, recv)

        # Якщо ввели конкретну заявку — показуємо лише її (якщо є в плані або рухах)
        if request_only:
            ro = _norm_rn(request_only)
            all_rn = [ro] if (ro in plan or ro in recv) else []

        list_requests.controls.clear()
        shown = 0
        for rn in all_rn:
            p, r = plan.get(rn, 0), recv.get(rn, 0)
            need = max(0, p - r)  # Потреба не менше 0
            if cb_only_need.value and need <= 0:
                continue
            pct = 0 if p == 0 else min(100, round(100 * r / p))

            row = ft.Container(
                bgcolor="#0b1220",
                border_radius=10,
                padding=10,
                border=ft.border.all(2, "#3b82f6") if rn == selected_request else ft.border.all(1, "#1f2937"),
                on_click=lambda e, req=rn: _load_details(req),
                content=ft.Column(
                    tight=True, spacing=6,
                    controls=[
                        ft.Text(f"Заявка №{rn}", size=16, weight="bold", color="#ffffff"),
                        ft.Row([ft.Text(f"{pct}%", color="#22d3ee")],
                               alignment=ft.MainAxisAlignment.END),
                        ft.ProgressBar(value=pct / 100 if p else 0),
                        ft.Row(
                            [
                                ft.Text(f"План: {_fmt_int(p)}", color="#94a3b8"),
                                ft.Text(f"Передано: {_fmt_int(r)}", color="#94a3b8"),
                                ft.Text(f"Потреба: {_fmt_int(need)}", color="#94a3b8"),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                ),
            )
            list_requests.controls.append(row)
            shown += 1

        requests_count.value = f"{shown} заявок"
        page.update()

    # ── завантаження деталей заявки
    def _load_details(request_number: str):
        nonlocal selected_request, last_articles_csv, last_moves_csv
        selected_request = request_number
        details_title.value = f"Деталі заявки №{request_number}"

        where_recv, params_base, _ = _where_recv_and_params()
        where_recv_req = where_recv + " AND request_number = %s"
        params = params_base + (request_number,)

        # План по артикулах
        rows_plan = db_fetch(
            """
            SELECT cr.article_code,
                   SUM(cr.quantity) AS plan_qty,
                   COALESCE(pb.name,'') AS product_name
            FROM casting_requests cr
            LEFT JOIN product_base pb ON pb.article_code = cr.article_code
            WHERE cr.request_number = %s
            GROUP BY cr.article_code, pb.name
            """,
            (request_number,),
        )
        plan_by_art = {r["article_code"]: {"plan_qty": r["plan_qty"] or 0, "name": r["product_name"]} for r in rows_plan}

        # Передано по артикулах
        rows_recv = db_fetch(
            f"""
            SELECT article_code, SUM(qty) AS recv_qty, MAX(product_name) AS product_name
            FROM warehouse_moves
            {where_recv_req}
            GROUP BY article_code
            ORDER BY article_code
            """,
            params,
        )
        recv_by_art = {r["article_code"]: {"recv_qty": r["recv_qty"] or 0, "name": r["product_name"]} for r in rows_recv}

        # Таблиця по артикулах
        all_art = sorted(set(plan_by_art.keys()) | set(recv_by_art.keys()))
        tbl_by_article.rows.clear()
        last_articles_csv = []
        tot_plan = tot_recv = 0
        for art in all_art:
            plan_q = (plan_by_art.get(art) or {}).get("plan_qty", 0)
            name   = (plan_by_art.get(art) or recv_by_art.get(art) or {}).get("name", "")
            recv_q = (recv_by_art.get(art) or {}).get("recv_qty", 0)
            need_q = max(0, plan_q - recv_q)  # Потреба >= 0
            pi = 0 if plan_q == 0 else min(100, round(100 * recv_q / plan_q))
            tbl_by_article.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(art)),
                    ft.DataCell(ft.Text(name)),
                    ft.DataCell(ft.Text(_fmt_int(plan_q))),
                    ft.DataCell(ft.Text(_fmt_int(recv_q))),
                    ft.DataCell(ft.Text(_fmt_int(need_q), color="#22c55e" if need_q == 0 else "#f59e0b")),
                    ft.DataCell(ft.Container(ft.ProgressBar(value=pi/100, width=160), tooltip=f"{pi}%")),
                ])
            )
            last_articles_csv.append([art, name, plan_q, recv_q, need_q, pi])
            tot_plan += plan_q
            tot_recv += recv_q

        tot_need = max(0, tot_plan - tot_recv)
        summary_row.controls = [
            ft.Text(f"План: {_fmt_int(tot_plan)}", color="#94a3b8"),
            ft.Text(f"Передано: {_fmt_int(tot_recv)}", color="#94a3b8"),
            ft.Text(f"Потреба: {_fmt_int(tot_need)}", color="#f59e0b" if tot_need > 0 else "#22c55e"),
        ]

        # Останні рухи (без location, з ПІБ Робітника)
        rows_moves = db_fetch(
            f"""
            SELECT move_time, article_code, product_name, qty,
                   operator_name, reason
            FROM warehouse_moves
            {where_recv_req}
            ORDER BY move_time DESC
            LIMIT 300
            """,
            params,
        )
        tbl_moves.rows.clear()
        last_moves_csv = []
        for r in rows_moves:
            when = _fmt_when(r["move_time"])
            tbl_moves.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(when)),
                    ft.DataCell(ft.Text(r["article_code"])),
                    ft.DataCell(ft.Text(r["product_name"])),
                    ft.DataCell(ft.Text(_fmt_int(r["qty"]))),
                    ft.DataCell(ft.Text(r.get("operator_name") or "—")),
                    ft.DataCell(ft.Text(r.get("reason") or "—")),
                ])
            )
            last_moves_csv.append([
                when, r["article_code"], r["product_name"], r["qty"],
                r.get("operator_name") or "", r.get("reason") or ""
            ])

        _load_master()  # підсвітити вибрану
        page.update()

    # ── Експорт
    def _export_articles():
        if last_articles_csv and selected_request:
            _export_csv(f"Заявка_{selected_request}_артикули.csv",
                        ["Артикул", "Найменування", "План", "Передано", "Потреба", "Прогрес,%"],
                        last_articles_csv)

    def _export_moves():
        if last_moves_csv and selected_request:
            _export_csv(f"Заявка_{selected_request}_рухи.csv",
                        ["Час", "Артикул", "Найменування", "К-сть", "ПІБ Робітника", "Коментар"],
                        last_moves_csv)

    # ── Застосування фільтрів
    def _apply_filters():
        _load_master()
        if selected_request:
            _load_details(selected_request)

    # первинне завантаження
    _load_master()

    return ft.Row(
        controls=[
            ft.Container(left_column, padding=10),
            ft.VerticalDivider(width=1),
            ft.Container(right_column, expand=True, padding=10),
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
