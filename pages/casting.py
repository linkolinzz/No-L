# pages/casting.py
import flet as ft
import datetime, sys
from database.db_manager import connect_db
import compat


def log(m):
    print(f"[casting {datetime.datetime.now().isoformat(' ','seconds')}] {m}", file=sys.stderr)


# ── Flet ≤0.28 сумісність ─────────────────────────
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons
if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
    ft.colors = ft.Colors


# ── DB helpers ─────────────────────────────────────
def db_fetch(sql, p=None):
    with connect_db() as cn:
        cu = cn.cursor(dictionary=True)
        cu.execute(sql, p or ())
        return cu.fetchall()


def db_exec(sql, seq):
    with connect_db() as cn:
        cu = cn.cursor()
        cu.executemany(sql, seq)
        cn.commit()


# ─────────────────────────── View ─────────────────
def view(page: ft.Page, request_no: str = ""):
    # ─── type selector and dropdowns
    # A new dropdown to choose between casting by request, test casting, or casting without a request.
    dd_type = ft.Dropdown(
        label="Тип лиття",
        width=200,
        # value holds the displayed text; we map it to an internal mode later.
        options=[
            ft.dropdown.Option("Лиття по заявці"),
            ft.dropdown.Option("Випробування лиття"),
            ft.dropdown.Option("Лиття без заявки"),
        ],
        value="Лиття по заявці",
    )
    # dropdown for request numbers (visible only when dd_type indicates casting by request)
    dd_req = ft.Dropdown(label="Номер заявки", width=220)
    # dropdown for article code / name.  For request mode it lists only articles with outstanding quantity.
    # For other modes it lists all products from product_base.
    dd_art = ft.Dropdown(label="Артикул (Найменування)", width=320, disabled=True)

    # track current mode: 'req', 'test', 'no_request'
    mode = {"value": "req"}

    # ─── inputs
    tf_worker = ft.TextField(label="ПІБ робітника", width=260, disabled=True)
    tf_machine = ft.TextField(label="№ станка", width=110, disabled=True)
    tf_need = ft.TextField(
        label="Необхідна к-сть (шт.)",
        width=180,
        read_only=True,
        disabled=True,
        text_align=ft.TextAlign.CENTER,
    )
    tf_cycles = ft.TextField(
        label="К-сть циклів (шт.)",
        width=140,
        keyboard_type="number",
        disabled=True,
    )
    tf_defect = ft.TextField(
        label="Брак (шт.)",
        width=110,
        keyboard_type="number",
        disabled=True,
    )
    btn_save = ft.ElevatedButton("Зберегти", disabled=True)

    editing_id = None
    # when editing, record which table to update ('casting','casting_test','casting_no_request')
    editing_table = {"value": "casting"}
    confirm_dlg = ft.AlertDialog(modal=True)

    # ---------- навігація ----------
    def go_back(e):
        # залишаємо у стеку лише головне меню
        while len(page.views) > 2:
            page.views.pop()
        page.update()

    # ─── завантаження списку заявок ───
    def load_requests():
        """
        Populate dd_req with distinct request numbers from casting_requests.  Only
        visible when mode is 'req'.
        """
        dd_req.options = [
            ft.dropdown.Option(r["request_number"])
            for r in db_fetch(
                "SELECT DISTINCT request_number FROM casting_requests WHERE is_closed=0 ORDER BY request_number DESC"
            )
        ]
        page.update()

    def load_products():
        """
        Populate dd_art with all products from product_base.  Used in test
        and no_request modes where there is no associated request.
        """
        dd_art.options = [
            ft.dropdown.Option(f"{r['article_code']} ({r['name']})")
            for r in db_fetch(
                "SELECT article_code, name FROM product_base ORDER BY article_code"
            )
        ]
        dd_art.disabled = not bool(dd_art.options)
        page.update()

    # ─── handle type change ─────────────────────────
    def on_type_change(e):
        """
        Adjust UI and data sources when the casting type changes.  In request
        mode we show the request dropdown and only enable the article dropdown
        after a request is selected.  In test or no_request modes we hide
        the request dropdown and fill the article dropdown with all products.
        """
        sel = dd_type.value
        if sel == "Лиття по заявці":
            mode["value"] = "req"
            # show and enable request selector
            dd_req.visible = True
            dd_req.disabled = False
            dd_req.value = None
            load_requests()
            # reset article dropdown and disable until request selected
            dd_art.options = []
            dd_art.value = None
            dd_art.disabled = True
            tf_need.value = ""
        else:
            mode["value"] = "test" if sel == "Випробування лиття" else "no_request"
            # hide and disable request selector
            dd_req.visible = False
            dd_req.disabled = True
            dd_req.value = None
            # load all products into article dropdown
            load_products()
            dd_art.value = None
            tf_need.value = "—"
        # reset form fields
        reset_form(full=True)
        # refresh table to show data for selected mode
        refresh_table()
        page.update()

    # ─── обробка зміни заявки ─────────────────────────
    def on_req_change(e):
        reset_form(full=True)
        if not dd_req.value:
            dd_art.options = []
            dd_art.disabled = True
            refresh_table()
            page.update()
            return

        rows = db_fetch(
            """
            SELECT cr.article_code,
                   IFNULL(pb.name,'') AS name,
                   cr.quantity AS need_qty,
                   COALESCE(
                     (SELECT SUM(quantity)
                        FROM casting c
                       WHERE c.request_number=cr.request_number
                         AND c.article_code=cr.article_code),
                     0
                   ) AS made
              FROM casting_requests cr
         LEFT JOIN product_base pb ON pb.article_code=cr.article_code
             WHERE cr.request_number=%s
         HAVING made < need_qty
            """,
            (dd_req.value,),
        )
        dd_art.options = [
            ft.dropdown.Option(f"{r['article_code']} ({r['name']})") for r in rows
        ]
        dd_art.disabled = not bool(rows)

        # відображаємо таблицю по вибраній заявці
        refresh_table()
        page.update()

    dd_req.on_change = on_req_change
    # attach type change handler
    dd_type.on_change = on_type_change

    # ─── вибір артикула ──────────────────────────────
    def on_art_change(e):
        reset_form(inputs_only=True)
        if not dd_art.value:
            page.update()
            return

        art = dd_art.value.split(" ", 1)[0]
        if mode["value"] == "req":
            # fetch remaining quantity for request-based casting
            info = db_fetch(
                """
                SELECT cr.quantity AS need_qty,
                       COALESCE((SELECT SUM(quantity) FROM casting
                                 WHERE request_number=%s AND article_code=%s),0) AS made
                FROM casting_requests cr
                WHERE cr.request_number=%s AND cr.article_code=%s
                LIMIT 1
                """,
                (dd_req.value, art, dd_req.value, art),
            )[0]
            tf_need.value = f"{info['need_qty']}  (вже виготовлено: {info['made']})"
        else:
            # in test/no_request modes there is no planned quantity
            tf_need.value = "—"
        for f in (tf_worker, tf_machine, tf_cycles, tf_defect):
            f.disabled = False
        btn_save.disabled = False
        editing_id = None
        editing_table["value"] = (
            "casting" if mode["value"] == "req" else (
                "casting_test" if mode["value"] == "test" else "casting_no_request"
            )
        )
        page.update()

    dd_art.on_change = on_art_change

    # ─── reset helper ────────────────────────────────
    def reset_form(full=False, inputs_only=False):
        nonlocal editing_id
        editing_id = None
        for f in (tf_worker, tf_machine, tf_cycles, tf_defect):
            f.value = ""
            f.disabled = True
        if not inputs_only:
            tf_need.value = ""
        if full:
            dd_art.value = None
        btn_save.disabled = True

    # ─── save record ────────────────────────────────
    def save_record(e):
        """
        Save a casting record.  Behaviour depends on the selected mode:
        - req: insert/update into the casting table using selected request number.
        - test: insert into casting_test.
        - no_request: insert into casting_no_request.
        """
        # validate article selection
        if not dd_art.value:
            return
        # in request mode ensure a request is chosen
        if mode["value"] == "req" and not dd_req.value:
            return
        # validate integer fields
        try:
            cycles = int(tf_cycles.value)
            defect = int(tf_defect.value or 0)
        except ValueError:
            page.snack_bar = ft.SnackBar(
                ft.Text("Цикли/Брак мають бути цілими числами"), open=True
            )
            return
        art = dd_art.value.split(" ", 1)[0]
        # Determine which table to write to based on mode
        target_table = (
            "casting"
            if mode["value"] == "req"
            else ("casting_test" if mode["value"] == "test" else "casting_no_request")
        )
        if editing_id and editing_table["value"] == target_table:
            # update existing record in appropriate table
            if target_table == "casting":
                db_exec(
                    """
                    UPDATE casting
                       SET operator_name=%s, machine_number=%s,
                           quantity=%s, defect_quantity=%s
                     WHERE id=%s
                    """,
                    [(tf_worker.value, tf_machine.value, cycles, defect, editing_id)],
                )
            else:
                # editing for test/no_request tables
                db_exec(
                    f"""
                    UPDATE {target_table}
                       SET operator_name=%s, machine_number=%s,
                           quantity=%s, defect_quantity=%s
                     WHERE id=%s
                    """,
                    [(tf_worker.value, tf_machine.value, cycles, defect, editing_id)],
                )
        else:
            # insert new record
            if target_table == "casting":
                db_exec(
                    """
                    INSERT INTO casting
                        (request_number, article_code, product_name,
                         quantity, defect_quantity, operator_name, machine_number)
                    VALUES (%s,%s,(SELECT name FROM product_base WHERE article_code=%s LIMIT 1),
                            %s,%s,%s,%s)
                    """,
                    [
                        (
                            dd_req.value,
                            art,
                            art,
                            cycles,
                            defect,
                            tf_worker.value,
                            tf_machine.value,
                        )
                    ],
                )
            else:
                # test or no_request: request_number is not stored
                db_exec(
                    f"""
                    INSERT INTO {target_table}
                        (article_code, product_name, quantity, defect_quantity, operator_name, machine_number)
                    VALUES (%s,(SELECT name FROM product_base WHERE article_code=%s LIMIT 1),%s,%s,%s,%s)
                    """,
                    [(
                        art,
                        art,
                        cycles,
                        defect,
                        tf_worker.value,
                        tf_machine.value,
                    )],
                )
        reset_form(full=True)
        # refresh dropdowns or tables
        if mode["value"] == "req":
            on_req_change(None)
        else:
            # reload article list for non-request modes
            load_products()
            refresh_table()
        page.snack_bar = ft.SnackBar(ft.Text("Збережено"), open=True)
        page.update()

    btn_save.on_click = save_record

    # ─── DataTable ───────────────────────────────────
    table = ft.DataTable(
        expand=True,
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Заявка")),
            ft.DataColumn(ft.Text("Артикул")),
            ft.DataColumn(ft.Text("Найменування", expand=True)),
            ft.DataColumn(ft.Text("Станок")),
            ft.DataColumn(ft.Text("Цикли")),
            ft.DataColumn(ft.Text("Брак")),
            ft.DataColumn(ft.Text("Добрі")),
            ft.DataColumn(ft.Text("% браку")),
            ft.DataColumn(ft.Text("Робітник")),
            ft.DataColumn(ft.Text("Дії")),
        ],
        rows=[],
    )

    def refresh_table():
        table.rows.clear()
        rows = []
        if mode["value"] == "req":
            # filter by request if provided, otherwise show latest 50
            if dd_req.value:
                rows = db_fetch(
                    "SELECT * FROM casting WHERE request_number=%s ORDER BY id DESC",
                    (dd_req.value,),
                )
            else:
                rows = db_fetch("SELECT * FROM casting ORDER BY id DESC LIMIT 50")
        elif mode["value"] == "test":
            rows = db_fetch(
                "SELECT *, NULL as request_number FROM casting_test ORDER BY id DESC LIMIT 50"
            )
        else:
            rows = db_fetch(
                "SELECT *, NULL as request_number FROM casting_no_request ORDER BY id DESC LIMIT 50"
            )
        for r in rows:
            good = r["quantity"] - (r.get("defect_quantity") or 0)
            perc = (
                f"{(r.get('defect_quantity') or 0) * 100 / r['quantity']:.1f} %"
                if r["quantity"]
                else "0 %"
            )
            table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(r["id"]))),
                        ft.DataCell(ft.Text(r.get("request_number", "—") or "—")),
                        ft.DataCell(ft.Text(r["article_code"])),
                        ft.DataCell(ft.Text(r.get("product_name", "—"))),
                        ft.DataCell(ft.Text(r.get("machine_number", "—"))),
                        ft.DataCell(ft.Text(str(r["quantity"]))),
                        ft.DataCell(ft.Text(str(r.get("defect_quantity") or 0))),
                        ft.DataCell(ft.Text(str(good))),
                        ft.DataCell(ft.Text(perc)),
                        ft.DataCell(ft.Text(r.get("operator_name", "—"))),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.IconButton(
                                        ft.icons.EDIT,
                                        tooltip="Редагувати",
                                        on_click=lambda e, rec=r: start_edit(rec),
                                    ),
                                    ft.IconButton(
                                        ft.icons.DELETE,
                                        tooltip="Видалити",
                                        on_click=lambda e, rid=r["id"]: ask_delete(rid),
                                    ),
                                ],
                                spacing=4,
                            )
                        ),
                    ]
                )
            )
        page.update()

    # ---- edit from table ----
    def start_edit(rec):
        nonlocal editing_id
        editing_id = rec["id"]
        # record which table the record comes from for update
        if mode["value"] == "req":
            editing_table["value"] = "casting"
        elif mode["value"] == "test":
            editing_table["value"] = "casting_test"
        else:
            editing_table["value"] = "casting_no_request"
        tf_worker.value = rec.get("operator_name", "")
        tf_machine.value = rec.get("machine_number", "")
        tf_cycles.value = str(rec["quantity"])
        tf_defect.value = str(rec["defect_quantity"] or 0)
        tf_need.value = "— редагування —"
        dd_req.value = rec["request_number"]
        # update article dropdown depending on mode
        if mode["value"] == "req":
            on_req_change(None)
            art_opt = f"{rec['article_code']} ({rec.get('product_name','')})"
            if not any(o.value == art_opt for o in dd_art.options):
                dd_art.options.append(ft.dropdown.Option(art_opt))
            dd_art.value = art_opt
        else:
            load_products()
            art_opt = f"{rec['article_code']} ({rec.get('product_name','')})"
            dd_art.value = art_opt
        for f in (tf_worker, tf_machine, tf_cycles, tf_defect):
            f.disabled = False
        btn_save.disabled = False
        page.update()

    # ---- delete row ----
    record_to_del = {"id": None}

    def ask_delete(rid):
        record_to_del["id"] = rid
        confirm_dlg.title = ft.Text("Підтвердити видалення")
        confirm_dlg.content = ft.Text(f"Видалити запис id {rid}?")
        confirm_dlg.actions = [
            ft.TextButton("Скасувати", on_click=lambda e: close_confirm(False)),
            ft.TextButton(
                "Видалити",
                style=ft.ButtonStyle(color=ft.colors.RED),
                on_click=lambda e: close_confirm(True),
            ),
        ]
        page.dialog = confirm_dlg
        if confirm_dlg not in page.overlay:
            page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        page.update()

    def close_confirm(ok):
        confirm_dlg.open = False
        page.update()
        if ok and record_to_del["id"]:
            rid = record_to_del["id"]
            # delete from appropriate table based on mode
            if mode["value"] == "req":
                db_exec("DELETE FROM casting WHERE id=%s", [(rid,)])
            elif mode["value"] == "test":
                db_exec("DELETE FROM casting_test WHERE id=%s", [(rid,)])
            else:
                db_exec("DELETE FROM casting_no_request WHERE id=%s", [(rid,)])
            record_to_del["id"] = None
            reset_form(full=True)
            if mode["value"] == "req":
                on_req_change(None)
            else:
                load_products()
            refresh_table()

    # ─── init ────────────────────────────────────────
    load_requests()
    refresh_table()  # показати останні записи одразу
    # set initial state based on type dropdown and optional request
    on_type_change(None)
    if mode["value"] == "req" and request_no and any(o.value == request_no for o in dd_req.options):
        dd_req.value = request_no
        on_req_change(None)

    return ft.View(
        f"/casting/{request_no}",
        # Do not include an internal header row; the launcher appbar provides a back
        # button and title for this view.  Begin with the main content column.
        controls=[
            ft.Column(
                [
            # include casting type selector before request and article selectors
            ft.Row([dd_type, dd_req, dd_art], spacing=16),
                    ft.Divider(),
                    ft.Row([tf_worker, tf_machine, tf_need, tf_cycles, tf_defect, btn_save], spacing=10),
                    ft.Divider(thickness=2),
                    ft.Text("Збережені записи лиття", style="titleMedium"),
                    ft.Row([table], expand=True),
                ],
                expand=True,
                spacing=8,
            ),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
