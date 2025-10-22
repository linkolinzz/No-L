# pages/cutting.py
import flet as ft
from database.db_manager import connect_db
import compat

# ────────── Flet 0.28 compatibility ──────────
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons  # type: ignore
if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
    ft.colors = ft.Colors  # type: ignore

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

# ────────── ensure columns ──────────
def ensure_columns():
    try:
        db_exec("ALTER TABLE cutting ADD COLUMN casting_id INT NULL")
    except Exception:
        pass
    try:
        db_exec("ALTER TABLE cutting ADD COLUMN created_at DATETIME NULL DEFAULT NOW()")
    except Exception:
        pass

ensure_columns()

# ────────── helpers for batch calculations ──────────
def qc_defects_row(cast_id: int) -> int:
    row = db_fetch(
        "SELECT COALESCE(SUM(checked_quantity - accepted_quantity),0) AS bad "
        "FROM casting_quality WHERE casting_id=%s",
        (cast_id,),
    )
    return int(row[0]["bad"]) if row else 0

def good_after_qc_row(cast_id: int) -> int:
    cast = db_fetch(
        "SELECT quantity, COALESCE(defect_quantity,0) AS d "
        "FROM casting WHERE id=%s LIMIT 1",
        (cast_id,),
    )
    if not cast:
        return 0
    base_good = cast[0]["quantity"] - cast[0]["d"]
    return max(0, base_good - qc_defects_row(cast_id))

def already_cut_row(cast_id: int) -> int:
    row = db_fetch(
        "SELECT COALESCE(SUM(processed_quantity),0) AS q FROM cutting WHERE casting_id=%s",
        (cast_id,),
    )
    return int(row[0]["q"]) if row else 0

def get_product_info(cast_id: int):
    row = db_fetch(
        """
        SELECT c.article_code, pb.name AS product_name
          FROM casting c
          JOIN product_base pb ON pb.article_code = c.article_code
         WHERE c.id=%s LIMIT 1
        """,
        (cast_id,),
    )
    return row[0] if row else {"article_code": "?", "product_name": "?"}

# ────────── View ──────────
def view(page: ft.Page, request_no: str = ""):
    page.scroll = ft.ScrollMode.AUTO
    editing_id      = {"id": None}
    current_cast_id = {"id": None}

    # ─── navigation back to main menu ───
    def go_back(e):
        while len(page.views) > 2:
            page.views.pop()
        page.update()

    # ─── UI controls ─────────────────────
    back_btn    = ft.ElevatedButton("← Назад", on_click=go_back)
    title_txt   = ft.Text("Різка", size=24, weight="bold", expand=True)

    dd_request  = ft.Dropdown(label="Номер заявки", width=220)
    dd_batch    = ft.Dropdown(label="Партія (Артикул / Найменування)",
                              width=420, disabled=True)

    tf_operator = ft.TextField(label="ПІБ робітника", width=260, disabled=True)
    tf_qty      = ft.TextField(label="Оброблено (шт.)", width=150,
                              keyboard_type="number", disabled=True)
    tf_defect   = ft.TextField(label="Брак (шт.)", width=150,
                              keyboard_type="number", disabled=True)

    btn_save    = ft.ElevatedButton("Зберегти", disabled=True)
    btn_cancel  = ft.ElevatedButton("Скасувати", visible=False)

    qty_left_lbl = ft.Text()

    # ─── helpers ──────────────────────────
    def reset_form(full: bool = True):
        editing_id["id"]      = None
        current_cast_id["id"] = None
        for f in (tf_operator, tf_qty, tf_defect):
            f.value    = ""
            f.disabled = True
        btn_save.disabled   = True
        btn_cancel.visible  = False
        dd_request.disabled = False
        if full:
            dd_batch.value    = None
            dd_batch.disabled = True
            qty_left_lbl.value = ""
        page.update()

    def load_requests():
        rows = db_fetch(
            "SELECT DISTINCT request_number FROM casting ORDER BY request_number DESC"
        )
        dd_request.options = [ft.dropdown.Option(r["request_number"]) for r in rows]
        page.update()

    def on_request_change(e):
        reset_form()
        dd_batch.options.clear()
        if not dd_request.value:
            page.update()
            return

        rows = db_fetch(
            """
            SELECT c.id, c.article_code, pb.name
              FROM casting c
              JOIN product_base pb
                ON pb.article_code = c.article_code
             WHERE c.request_number=%s
               AND pb.cutting_needed = 1
             ORDER BY c.id
            """,
            (dd_request.value,),
        )

        for r in rows:
            cid   = r["id"]
            total = good_after_qc_row(cid)
            done  = already_cut_row(cid)
            if done < total:
                txt = (f"#{cid}  {r['article_code']} ({r['name']}) | "
                       f"лишилось: {total - done}")
                dd_batch.options.append(ft.dropdown.Option(txt))

        dd_batch.disabled = not bool(dd_batch.options)
        page.update()

    dd_request.on_change = on_request_change

    def on_batch_change(e):
        reset_form(full=False)
        if not dd_batch.value:
            return
        cid = int(dd_batch.value.split()[0][1:])
        current_cast_id["id"] = cid
        total = good_after_qc_row(cid)
        done  = already_cut_row(cid)
        qty_left_lbl.value = f"Залишилось: {total - done}"
        for f in (tf_operator, tf_qty, tf_defect):
            f.disabled = False
        btn_save.disabled = False
        page.update()

    dd_batch.on_change = on_batch_change

    def save_record(e):
        if not (dd_request.value and current_cast_id["id"]):
            return
        try:
            qty    = int(tf_qty.value or 0)
            defect = int(tf_defect.value or 0)
        except ValueError:
            page.snack_bar = ft.SnackBar(
                ft.Text("Числові поля заповнені неправильно"), open=True
            )
            page.update()
            return

        cid  = current_cast_id["id"]
        info = get_product_info(cid)

        if editing_id["id"]:
            db_exec(
                """
                UPDATE cutting
                   SET operator_name=%s,
                       processed_quantity=%s,
                       defect_quantity=%s
                 WHERE id=%s
                """,
                (tf_operator.value, qty, defect, editing_id["id"]),
            )
        else:
            db_exec(
                """
                INSERT INTO cutting
                   (request_number, article_code, product_name,
                    operator_name, processed_quantity, defect_quantity,
                    casting_id, created_at)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
                """,
                (
                    dd_request.value,
                    info["article_code"],
                    info["product_name"],
                    tf_operator.value,
                    qty,
                    defect,
                    cid,
                ),
            )

        reset_form()
        refresh_table()
        on_request_change(None)

    btn_save.on_click   = save_record
    btn_cancel.on_click = lambda e: reset_form(full=False)

    # ─── delete ─────────────────────────────
    confirm_dlg      = ft.AlertDialog(modal=True)
    record_to_delete = {"id": None}

    def confirm_delete(e, rid: int):
        record_to_delete["id"] = rid
        confirm_dlg.title   = ft.Text("Підтвердження видалення")
        confirm_dlg.content = ft.Text(f"Видалити запис ID {rid}?")
        confirm_dlg.actions = [
            ft.TextButton("Скасувати", on_click=lambda ev: close_confirm(False)),
            ft.TextButton("Видалити",
                          style=ft.ButtonStyle(color=ft.colors.RED),
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
            db_exec("DELETE FROM cutting WHERE id=%s", (record_to_delete["id"],))
            refresh_table()
            on_request_change(None)
        record_to_delete["id"] = None

    # ─── history table ────────────────────────
    table = ft.DataTable(
        expand=True,
        columns=[
            ft.DataColumn(ft.Text(h))
            for h in (
                "ID", "Заявка", "ID лиття", "Артикул", "Найменування",
                "Робітник", "Оброблено", "Брак", "% браку", "Дата", "Дії"
            )
        ],
        rows=[],
    )

    def refresh_table():
        table.rows.clear()
        for r in db_fetch("SELECT * FROM cutting ORDER BY id DESC LIMIT 50"):
            total  = r["processed_quantity"]
            defect = r["defect_quantity"] or 0
            perc   = f"{defect * 100 / total:.1f} %" if total else "0 %"
            date_s = (
                r["created_at"].strftime("%d.%m.%Y %H:%M")
                if r.get("created_at") else "—"
            )
            cast_id = r.get("casting_id") or "—"

            def mk_edit(rec):
                def _e(_ev):
                    editing_id["id"] = rec["id"]
                    current_cast_id["id"] = rec["casting_id"]

                    dd_request.value    = rec["request_number"]
                    dd_request.disabled = True

                    total = good_after_qc_row(rec["casting_id"])
                    done  = already_cut_row(rec["casting_id"])
                    disp  = (f"#{rec['casting_id']}  {rec['article_code']} | "
                             f"лишилось: {total - done}")
                    dd_batch.options  = [ft.dropdown.Option(disp)]
                    dd_batch.value    = disp
                    dd_batch.disabled = True

                    tf_operator.value = rec["operator_name"] or ""
                    tf_qty.value      = str(rec["processed_quantity"])
                    tf_defect.value   = str(rec["defect_quantity"] or 0)
                    for f in (tf_operator, tf_qty, tf_defect):
                        f.disabled = False
                    qty_left_lbl.value = ""
                    btn_save.disabled  = False
                    btn_cancel.visible = True
                    page.update()
                return _e

            table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(r["id"]))),
                    ft.DataCell(ft.Text(r["request_number"])),
                    ft.DataCell(ft.Text(str(cast_id))),
                    ft.DataCell(ft.Text(r["article_code"])),
                    ft.DataCell(ft.Text(r["product_name"])),
                    ft.DataCell(ft.Text(r["operator_name"] or "—")),
                    ft.DataCell(ft.Text(str(total))),
                    ft.DataCell(ft.Text(str(defect))),
                    ft.DataCell(ft.Text(perc)),
                    ft.DataCell(ft.Text(date_s)),
                    ft.DataCell(
                        ft.Row([
                            ft.IconButton(ft.icons.EDIT,
                                          tooltip="Редагувати",
                                          on_click=mk_edit(r)),
                            ft.IconButton(ft.icons.DELETE,
                                          tooltip="Видалити",
                                          icon_color=ft.colors.RED,
                                          on_click=lambda ev, rid=r["id"]: confirm_delete(ev, rid)),
                        ], spacing=4)
                    ),
                ])
            )
        page.update()

    # ─── init ─────────────────────────────────────
    load_requests()
    if request_no and any(o.value == request_no for o in dd_request.options):
        dd_request.value = request_no
        on_request_change(None)
    refresh_table()

    return ft.View(
        f"/cutting/{request_no}",
        # Do not include a duplicate header row; rely on the launcher appbar.  Begin
        # directly with the remaining controls.
        controls=[
            qty_left_lbl,
            ft.Row([dd_request, dd_batch], spacing=15),
            ft.Row([tf_operator, tf_qty, tf_defect, btn_save, btn_cancel], spacing=10),
            ft.Divider(thickness=2),
            ft.Text("Історія записів", style="titleMedium"),
            ft.Row([table], expand=True),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
