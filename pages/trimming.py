# pages/trimming.py
import flet as ft
from datetime import datetime
from database.db_manager import connect_db
import compat

# ────────── DB helpers ──────────
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

# перевірка наявності created_at у таблиці trimming
with connect_db() as _cn:
    _c = _cn.cursor()
    _c.execute("SHOW COLUMNS FROM trimming LIKE 'created_at'")
    HAS_CREATED_AT = _c.fetchone() is not None

# ────────── допоміжні функції ──────────
def get_product_name(code: str) -> str:
    row = db_fetch("SELECT name FROM product_base WHERE article_code=%s LIMIT 1", (code,))
    return row[0]["name"] if row else "-"

def accepted_after_quality(req: str, code: str) -> int:
    """Скільки прийнято після контролю якості лиття."""
    row = db_fetch(
        """
        SELECT COALESCE(SUM(accepted_quantity),0) AS a
          FROM casting_quality
         WHERE request_number=%s
           AND article_code=%s
        """,
        (req, code),
    )
    return int(row[0]["a"]) if row else 0

def already_trimmed(req: str, code: str) -> int:
    """Скільки вже обрізано."""
    row = db_fetch(
        """
        SELECT COALESCE(SUM(processed_quantity),0) AS s
          FROM trimming
         WHERE request_number=%s
           AND article_code=%s
        """,
        (req, code),
    )
    return int(row[0]["s"]) if row else 0

# ───────────────────── View ─────────────────────
def view(page: ft.Page, request_no: str = ""):
    page.scroll = ft.ScrollMode.AUTO
    editing_id = {"id": None}

    # ─── UI controls ───────────────────────────────
    back_btn    = ft.ElevatedButton("← Назад")
    title_txt   = ft.Text("Обрізка", size=24, weight="bold", expand=True)

    dd_request  = ft.Dropdown(label="Номер заявки", width=220)
    dd_article  = ft.Dropdown(label="Артикул (Найменування)", width=320, disabled=True)

    tf_operator = ft.TextField(label="ПІБ робітника", width=260, disabled=True)
    tf_qty      = ft.TextField(label="Оброблено (шт.)", width=150, keyboard_type="number", disabled=True)
    tf_defect   = ft.TextField(label="Брак (шт.)", width=150, keyboard_type="number", disabled=True)

    btn_save    = ft.ElevatedButton("Зберегти", disabled=True)
    btn_cancel  = ft.ElevatedButton("Скасувати", visible=False)

    qty_left_lbl = ft.Text("")

    # ─── навігація ────────────────────────────────
    def go_back(e):
        while len(page.views) > 2:
            page.views.pop()
        page.update()
    back_btn.on_click = go_back

    # ─── очистка форми ─────────────────────────────
    def reset_form(full: bool = True):
        editing_id["id"] = None
        for f in (tf_operator, tf_qty, tf_defect):
            f.value = ""
            f.disabled = True
        btn_save.disabled  = True
        btn_cancel.visible = False
        dd_request.disabled = False
        if full:
            dd_article.value    = None
            dd_article.disabled = True
            qty_left_lbl.value  = ""
        page.update()

    # ─── таблиця історії ───────────────────────────
    table = ft.DataTable(
        expand=True,
        columns=[
            ft.DataColumn(ft.Text("ID", size=11)),
            ft.DataColumn(ft.Text("Заявка")),
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Найменування", expand=True)),
            ft.DataColumn(ft.Text("Оброблено")),
            ft.DataColumn(ft.Text("Брак")),
            ft.DataColumn(ft.Text("% браку")),
            ft.DataColumn(ft.Text("Оператор")),
            ft.DataColumn(ft.Text("Дата")),
            ft.DataColumn(ft.Text("Дії")),
        ],
        rows=[],
    )

    def refresh_table():
        table.rows.clear()
        rows = (
            db_fetch(
                "SELECT * FROM trimming WHERE request_number=%s ORDER BY id DESC",
                (dd_request.value,),
            )
            if dd_request.value
            else []
        )
        for r in rows:
            total  = r["processed_quantity"]
            defect = r["defect_quantity"] or 0
            perc   = f"{defect * 100 / total:.1f} %" if total else "0 %"
            date_s = (
                r["created_at"].strftime("%d.%m.%Y %H:%M")
                if HAS_CREATED_AT and r.get("created_at")
                else "—"
            )

            def make_edit_handler(rec):
                def _edit(_e):
                    editing_id["id"] = rec["id"]
                    dd_request.value    = rec["request_number"]
                    dd_request.disabled = True
                    dd_article.options  = [
                        ft.dropdown.Option(f"{rec['article_code']} ({rec['product_name']})")
                    ]
                    dd_article.value    = dd_article.options[0].value
                    dd_article.disabled = True
                    tf_operator.value   = rec["operator_name"] or ""
                    tf_qty.value        = str(rec["processed_quantity"])
                    tf_defect.value     = str(rec["defect_quantity"] or 0)
                    for f in (tf_operator, tf_qty, tf_defect):
                        f.disabled = False
                    qty_left_lbl.value  = ""
                    btn_save.disabled   = False
                    btn_cancel.visible  = True
                    page.update()
                return _edit

            table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(r["id"]))),
                    ft.DataCell(ft.Text(r["request_number"])),
                    ft.DataCell(ft.Text(r["article_code"])),
                    ft.DataCell(ft.Text(r["product_name"] or "—")),
                    ft.DataCell(ft.Text(str(total))),
                    ft.DataCell(ft.Text(str(defect))),
                    ft.DataCell(ft.Text(perc)),
                    ft.DataCell(ft.Text(r["operator_name"] or "—")),
                    ft.DataCell(ft.Text(date_s)),
                    ft.DataCell(
                        ft.Row(
                            [
                                ft.IconButton(
                                    ft.icons.EDIT,
                                    tooltip="Редагувати",
                                    on_click=make_edit_handler(r),
                                ),
                                ft.IconButton(
                                    ft.icons.DELETE,
                                    tooltip="Видалити",
                                    icon_color=ft.colors.RED,
                                    on_click=lambda ev, rid=r["id"]: confirm_delete(ev, rid),
                                ),
                            ],
                            spacing=4,
                        )
                    ),
                ])
            )
        page.update()

    # ─── завантаження заявок ───────────────────────────
    def load_requests():
        dd_request.options = [
            ft.dropdown.Option(r["request_number"])
            for r in db_fetch(
                """
                SELECT DISTINCT cr.request_number
                  FROM casting_requests cr
                  JOIN product_base pb ON pb.article_code = cr.article_code
                 WHERE pb.trimming_needed = 1
                 ORDER BY cr.request_number DESC
                """
            )
        ]
        page.update()

    # ─── при зміні заявки ─────────────────────────────
    def on_request_change(e):
        reset_form()
        dd_article.options.clear()
        if not dd_request.value:
            refresh_table()
            page.update()
            return

        # доступно = accepted_after_quality − already_trimmed
        for r in db_fetch(
            """
            SELECT cr.article_code, pb.name
              FROM casting_requests cr
              JOIN product_base pb ON pb.article_code = cr.article_code
             WHERE cr.request_number=%s AND pb.trimming_needed=1
             GROUP BY cr.article_code
            """,
            (dd_request.value,),
        ):
            code       = r["article_code"]
            accepted   = accepted_after_quality(dd_request.value, code)
            done       = already_trimmed(dd_request.value, code)
            available  = accepted - done
            if available > 0:
                dd_article.options.append(ft.dropdown.Option(f"{code} ({r['name']})"))

        dd_article.disabled = not bool(dd_article.options)
        refresh_table()
        page.update()

    dd_request.on_change = on_request_change

    # ─── при зміні артикула ───────────────────────────
    def on_article_change(e):
        reset_form(full=False)
        if not dd_article.value:
            return
        code      = dd_article.value.split(" ", 1)[0]
        accepted  = accepted_after_quality(dd_request.value, code)
        done      = already_trimmed(dd_request.value, code)
        available = accepted - done
        qty_left_lbl.value = f"Залишилось: {max(0, available)}"
        for f in (tf_operator, tf_qty, tf_defect):
            f.disabled = False
        btn_save.disabled = False
        page.update()

    dd_article.on_change = on_article_change

    # ─── збереження/оновлення ─────────────────────────
    def save_record(e):
        if not (dd_request.value and dd_article.value):
            return
        code = dd_article.value.split(" ", 1)[0]
        try:
            qty    = int(tf_qty.value or 0)
            defect = int(tf_defect.value or 0)
        except ValueError:
            page.snack_bar = ft.SnackBar(ft.Text("Числові поля заповнені неправильно"), open=True)
            page.update()
            return

        if editing_id["id"]:
            db_exec(
                """
                UPDATE trimming
                   SET operator_name=%s,
                       processed_quantity=%s,
                       defect_quantity=%s
                 WHERE id=%s
                """,
                (tf_operator.value, qty, defect, editing_id["id"]),
            )
        else:
            cols   = "(request_number,article_code,product_name,operator_name,processed_quantity,defect_quantity"
            vals   = "%s,%s,%s,%s,%s,%s"
            params = [
                dd_request.value,
                code,
                get_product_name(code),
                tf_operator.value,
                qty,
                defect,
            ]
            if HAS_CREATED_AT:
                cols += ",created_at"
                vals += ",NOW()"
            cols += ")"
            db_exec(f"INSERT INTO trimming {cols} VALUES ({vals})", tuple(params))

        reset_form()
        on_request_change(None)

    btn_save.on_click   = save_record
    btn_cancel.on_click = lambda e: reset_form(full=False)

    # ─── видалення запису ─────────────────────────────
    confirm_dlg      = ft.AlertDialog(modal=True)
    record_to_delete = {"id": None}

    def confirm_delete(e, rid: int):
        record_to_delete["id"] = rid
        confirm_dlg.title   = ft.Text("Підтвердження видалення")
        confirm_dlg.content = ft.Text(f"Видалити запис ID {rid}?")
        confirm_dlg.actions = [
            ft.TextButton("Скасувати", on_click=lambda ev: close_confirm(False)),
            ft.TextButton("Видалити", style=ft.ButtonStyle(color=ft.colors.RED),
                          on_click=lambda ev: close_confirm(True)),
        ]
        page.dialog = confirm_dlg
        if confirm_dlg not in page.overlay:
            page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        page.update()

    def close_confirm(ok: bool):
        confirm_dlg.open = False
        page.update()
        if ok and record_to_delete["id"]:
            db_exec("DELETE FROM trimming WHERE id=%s", (record_to_delete["id"],))
            on_request_change(None)
        record_to_delete["id"] = None

    # ─── ініціалізація ─────────────────────────────────
    load_requests()
    if request_no and any(o.value == request_no for o in dd_request.options):
        dd_request.value = request_no
    on_request_change(None)

    return ft.View(
        f"/trimming/{request_no}",
        # Do not duplicate the back button and page title.  Start directly with the
        # main controls and table.
        controls=[
            qty_left_lbl,
            ft.Row([dd_request, dd_article], spacing=15),
            ft.Row([tf_operator, tf_qty, tf_defect, btn_save, btn_cancel], spacing=10),
            ft.Divider(thickness=2),
            ft.Text("Історія записів", style="titleMedium"),
            ft.Row([table], expand=True),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
