# pages/casting_request.py
import flet as ft
from datetime import date
from database.db_manager import connect_db

# ------------------------------ styles ------------------------------
CARD_GRADIENT = ft.LinearGradient(
    begin=ft.alignment.top_left,
    end=ft.alignment.bottom_right,
    colors=["#1e1e2f", "#1a1a40", "#0f0c29"],
)
CARD_RADIUS = 15

# --------------------------- DB helpers ---------------------------
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

def get_name(code):
    r = db_fetch("SELECT name FROM product_base WHERE article_code=%s", (code,))
    return r[0]["name"] if r else "—"

def fact_qty(req, code):
    r = db_fetch(
        "SELECT COALESCE(SUM(quantity),0) q FROM casting "
        "WHERE request_number=%s AND article_code=%s",
        (req, code),
    )
    return r[0]["q"]

# --------------------------- VIEW ---------------------------
def view(page: ft.Page):
    # Note: The original view included a single list of requests.  This has been
    # refactored into two tabs: active requests and a history of closed
    # requests.  A request can be closed via the new "Закрити заявку" button,
    # which sets the is_closed flag.  Closed requests are accessible in the
    # history tab and can be filtered by request number via a search field.

    # form controls
    tf_req    = ft.TextField(label="Номер заявки", expand=True)
    tf_date   = ft.TextField(label="Дата заявки", value=str(date.today()), expand=True)
    tf_code   = ft.TextField(label="Артикул виробу", expand=True)
    tf_name   = ft.TextField(label="Назва виробу", read_only=True, expand=True)
    tf_qty    = ft.TextField(label="Потрібність (шт.)", keyboard_type="number", expand=True)
    tf_client = ft.TextField(label="Клієнт", hint_text="(необов’язково)", expand=True)
    tf_reason = ft.TextField(label="Підстава", hint_text="(необов’язково)", expand=True)

    tf_code.on_change = lambda e: (
        setattr(tf_name, "value", get_name(tf_code.value.strip())),
        page.update(),
    )

    # track which pair (req, code) is being edited
    edit_mode = {"req": None, "code": None}

    def save(e):
        req = (tf_req.value or "").strip()
        code = (tf_code.value or "").strip()
        qty_str = (tf_qty.value or "").strip()
        if not (req and code and qty_str.isdigit()):
            page.snack_bar = ft.SnackBar(
                ft.Text("Заповніть обов'язкові поля (та коректну кількість)"),
                open=True,
            )
            return
        qty = int(qty_str)
        client = (tf_client.value or "-").strip()
        reason = (tf_reason.value or "-").strip()
        rdate  = (tf_date.value or str(date.today())).strip()
        if edit_mode["req"]:
            db_exec(
                """
                UPDATE casting_requests
                   SET quantity=%s, client=%s, reason=%s
                 WHERE request_number=%s AND article_code=%s
                """,
                (qty, client, reason, edit_mode["req"], edit_mode["code"]),
            )
        else:
            db_exec(
                """
                INSERT INTO casting_requests
                    (request_number, article_code, quantity, stage, request_date, client, reason)
                VALUES (%s,%s,%s,'Лиття',%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    quantity=VALUES(quantity),
                    client=VALUES(client),
                    reason=VALUES(reason),
                    request_date=VALUES(request_date)
                """,
                (req, code, qty, rdate, client, reason),
            )
        # reset fields
        for f in (tf_code, tf_qty, tf_name):
            f.value = ""
        edit_mode["req"] = None
        load_active()
        load_history()

    btn_save = ft.ElevatedButton("Зберегти", on_click=save)

    # columns for active and history
    active_cards  = ft.Column(spacing=12)
    history_cards = ft.Column(spacing=12)
    # search input for history
    tf_search_hist = ft.TextField(
        label="Пошук заявки", hint_text="Введіть номер заявки", expand=True
    )

    def load_active():
        active_cards.controls.clear()
        grid = ft.ResponsiveRow(run_spacing=12, spacing=12)
        for rec in db_fetch(
            """
            SELECT request_number, MAX(client) c, MAX(reason) r, MAX(id) mid
              FROM casting_requests
             WHERE is_closed=0
          GROUP BY request_number
          ORDER BY mid DESC
            """
        ):
            req_num = rec["request_number"]
            items = db_fetch(
                "SELECT article_code, quantity FROM casting_requests WHERE request_number=%s",
                (req_num,),
            )
            preview = [
                ft.Row(
                    [
                        ft.Text(i["article_code"], expand=1),
                        ft.Text(get_name(i["article_code"]), expand=2),
                        ft.Text(i["quantity"], expand=1),
                    ]
                )
                for i in items[:2]
            ]
            def open_modal(e=None, num=req_num):
                rows = db_fetch(
                    "SELECT * FROM casting_requests WHERE request_number=%s", (num,)
                )
                if not rows:
                    return
                tbl = [
                    ft.Row(
                        [
                            ft.Text("Артикул", weight="bold", expand=1),
                            ft.Text("Назва", weight="bold", expand=2),
                            ft.Text("К-сть", weight="bold", width=70),
                            ft.Text("Факт", weight="bold", width=70),
                            ft.Text("Дії", weight="bold", width=90),
                        ]
                    )
                ]
                dlg = ft.AlertDialog(modal=True)
                def close():
                    dlg.open = False
                    page.update()
                def edit_row(c, q):
                    close()
                    tf_req.value, tf_code.value, tf_name.value, tf_qty.value = num, c, get_name(c), q
                    tf_client.value, tf_reason.value = rec["c"] or "-", rec["r"] or "-"
                    edit_mode["req"], edit_mode["code"] = num, c
                    page.update()
                def del_row(c):
                    db_exec(
                        "DELETE FROM casting_requests WHERE request_number=%s AND article_code=%s",
                        (num, c),
                    )
                    close()
                    load_active()
                    load_history()
                for r in rows:
                    code_i, qty_i = r["article_code"], r["quantity"]
                    tbl.append(
                        ft.Row(
                            [
                                ft.Text(code_i, expand=1),
                                ft.Text(get_name(code_i), expand=2),
                                ft.Text(qty_i, width=70),
                                ft.Text(fact_qty(num, code_i), width=70),
                                ft.Row(
                                    [
                                        ft.IconButton(
                                            ft.icons.EDIT,
                                            tooltip="Редагувати",
                                            on_click=lambda e, c=code_i, q=qty_i: edit_row(c, q),
                                        ),
                                        ft.IconButton(
                                            ft.icons.DELETE,
                                            icon_color=ft.colors.RED,
                                            tooltip="Видалити",
                                            on_click=lambda e, c=code_i: del_row(c),
                                        ),
                                    ],
                                    spacing=4,
                                    width=90,
                                    alignment="center",
                                ),
                            ],
                            spacing=8,
                        )
                    )
                dlg.title = ft.Text(f"Заявка № {num}")
                dlg.content = ft.Container(
                    ft.Column(
                        [
                            ft.Text(f"Клієнт:  {rec['c'] or '-'}"),
                            ft.Text(f"Підстава: {rec['r'] or '-'}"),
                            ft.Column(tbl, tight=True, scroll="always", height=300),
                        ],
                        spacing=6,
                    ),
                    width=650,
                )
                dlg.actions = [ft.TextButton("Закрити", on_click=lambda _: close())]
                dlg.actions_alignment = "end"
                page.dialog = dlg
                if dlg not in page.overlay:
                    page.overlay.append(dlg)
                dlg.open = True
                page.update()
            def delete_req(e=None, num=req_num):
                db_exec(
                    "DELETE FROM casting_requests WHERE request_number=%s",
                    (num,),
                )
                load_active()
                load_history()
            def close_req(e=None, num=req_num):
                db_exec(
                    "UPDATE casting_requests SET is_closed=1 WHERE request_number=%s",
                    (num,),
                )
                load_active()
                load_history()
            card_content = ft.Column(
                [
                    ft.Text(f"Заявка № {req_num}", size=18, weight="bold"),
                    ft.Text(f"Клієнт: {rec['c'] or '-'}"),
                    ft.Text(f"Підстава: {rec['r'] or '-'}"),
                    ft.Row(
                        [
                            ft.Text("Артикул", weight="bold", expand=1),
                            ft.Text("Назва", weight="bold", expand=2),
                            ft.Text("К-сть", weight="bold", expand=1),
                        ]
                    ),
                    *preview,
                    ft.Row(
                        [
                            ft.IconButton(
                                ft.icons.DELETE,
                                icon_color=ft.colors.RED,
                                tooltip="Видалити",
                                on_click=delete_req,
                            ),
                            ft.IconButton(
                                ft.icons.LOCK,
                                icon_color=ft.colors.GREEN,
                                tooltip="Закрити заявку",
                                on_click=close_req,
                            ),
                            ft.ElevatedButton(
                                content=ft.Row(
                                    [ft.Icon(ft.icons.INFO_OUTLINE), ft.Text("Детальніше")],
                                    spacing=4,
                                ),
                                on_click=open_modal,
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=6,
            )
            card = ft.Container(
                card_content,
                gradient=CARD_GRADIENT,
                border_radius=CARD_RADIUS,
                padding=18,
                ink=True,
            )
            card.on_hover = (
                lambda ev, c=card: (
                    setattr(c, "scale", 1.03 if ev.data == "true" else 1.0),
                    c.update(),
                )
            )
            grid.controls.append(ft.Container(card, col={"xs": 12, "md": 4}))
        active_cards.controls = [grid]
        page.update()

    def load_history():
        history_cards.controls.clear()
        search_val = (tf_search_hist.value or "").strip()
        params = []
        query = [
            "SELECT request_number, MAX(client) c, MAX(reason) r, MAX(id) mid",
            "  FROM casting_requests",
            " WHERE is_closed=1",
        ]
        if search_val:
            query.append("   AND request_number LIKE %s")
            params.append(f"%{search_val}%")
        query.append(" GROUP BY request_number ORDER BY mid DESC")
        rows = db_fetch("\n".join(query), params if params else None)
        grid = ft.ResponsiveRow(run_spacing=12, spacing=12)
        for rec in rows:
            req_num = rec["request_number"]
            items = db_fetch(
                "SELECT article_code, quantity FROM casting_requests WHERE request_number=%s",
                (req_num,),
            )
            preview = [
                ft.Row(
                    [
                        ft.Text(i["article_code"], expand=1),
                        ft.Text(get_name(i["article_code"]), expand=2),
                        ft.Text(i["quantity"], expand=1),
                    ]
                )
                for i in items[:2]
            ]
            def open_modal_closed(e=None, num=req_num):
                rows2 = db_fetch(
                    "SELECT * FROM casting_requests WHERE request_number=%s",
                    (num,)
                )
                if not rows2:
                    return
                tbl2 = [
                    ft.Row(
                        [
                            ft.Text("Артикул", weight="bold", expand=1),
                            ft.Text("Назва", weight="bold", expand=2),
                            ft.Text("К-сть", weight="bold", width=70),
                            ft.Text("Факт", weight="bold", width=70),
                        ]
                    )
                ]
                for r in rows2:
                    code_i, qty_i = r["article_code"], r["quantity"]
                    tbl2.append(
                        ft.Row(
                            [
                                ft.Text(code_i, expand=1),
                                ft.Text(get_name(code_i), expand=2),
                                ft.Text(qty_i, width=70),
                                ft.Text(fact_qty(num, code_i), width=70),
                            ],
                            spacing=8,
                        )
                    )
                dlg2 = ft.AlertDialog(modal=True)
                def close2():
                    dlg2.open = False
                    page.update()
                dlg2.title = ft.Text(f"Заявка № {num}")
                dlg2.content = ft.Container(
                    ft.Column(
                        [
                            ft.Text(f"Клієнт:  {rec['c'] or '-'}"),
                            ft.Text(f"Підстава: {rec['r'] or '-'}"),
                            ft.Column(tbl2, tight=True, scroll="always", height=300),
                        ],
                        spacing=6,
                    ),
                    width=650,
                )
                dlg2.actions = [ft.TextButton("Закрити", on_click=lambda _: close2())]
                dlg2.actions_alignment = "end"
                page.dialog = dlg2
                if dlg2 not in page.overlay:
                    page.overlay.append(dlg2)
                dlg2.open = True
                page.update()
            card_content = ft.Column(
                [
                    ft.Text(f"Заявка № {req_num}", size=18, weight="bold"),
                    ft.Text(f"Клієнт: {rec['c'] or '-'}"),
                    ft.Text(f"Підстава: {rec['r'] or '-'}"),
                    ft.Row(
                        [
                            ft.Text("Артикул", weight="bold", expand=1),
                            ft.Text("Назва", weight="bold", expand=2),
                            ft.Text("К-сть", weight="bold", expand=1),
                        ]
                    ),
                    *preview,
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                content=ft.Row(
                                    [ft.Icon(ft.icons.INFO_OUTLINE), ft.Text("Детальніше")],
                                    spacing=4,
                                ),
                                on_click=open_modal_closed,
                            ),
                        ],
                        spacing=6,
                    ),
                ],
                spacing=6,
            )
            card = ft.Container(
                card_content,
                gradient=CARD_GRADIENT,
                border_radius=CARD_RADIUS,
                padding=18,
                ink=True,
            )
            card.on_hover = (
                lambda ev, c=card: (
                    setattr(c, "scale", 1.03 if ev.data == "true" else 1.0),
                    c.update(),
                )
            )
            grid.controls.append(ft.Container(card, col={"xs": 12, "md": 4}))
        history_cards.controls = [grid]
        page.update()

    tf_search_hist.on_change = lambda e: load_history()

    load_active()
    load_history()

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(
                text="Поточні заявки",
                content=ft.Column([active_cards], tight=True),
            ),
            ft.Tab(
                text="Історія заяв",
                content=ft.Column([
                    ft.Row([tf_search_hist], alignment="start"),
                    ft.Divider(thickness=1),
                    history_cards,
                ], tight=True),
            ),
        ],
        expand=1,
    )

    return ft.View(
        "/casting_request",
        controls=[
            ft.Row([tf_req, tf_date], spacing=10),
            ft.Row([tf_code, tf_name], spacing=10),
            ft.Row([tf_qty], spacing=10),
            ft.Row([tf_client, tf_reason], spacing=10),
            btn_save,
            ft.Divider(thickness=2),
            tabs,
        ],
        scroll=ft.ScrollMode.AUTO,
    )
