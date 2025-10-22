# pages/casting_quality.py
import math
import flet as ft
from database.db_manager import connect_db
import compat

# ── Flet 0.28 сумісність ───────────────────────────────────
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons
if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
    ft.colors = ft.Colors

# ── DB helpers ─────────────────────────────────────────────
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

# ── ensure needed columns ──────────────────────────────────
for col in ("drying_id INT NULL", "casting_id INT NULL"):
    try:
        db_exec(f"ALTER TABLE casting_quality ADD COLUMN {col}")
    except Exception:
        pass

# ── helpers ────────────────────────────────────────────────
def produced_cast(cid: int) -> int:
    r = db_fetch(
        "SELECT quantity, COALESCE(defect_quantity,0) AS d FROM casting WHERE id=%s",
        (cid,),
    )
    if not r:
        return 0
    return max(0, r[0]["quantity"] - r[0]["d"])

def produced_dry(did: int) -> int:
    r = db_fetch("SELECT qty FROM drying WHERE id=%s", (did,))
    return r[0]["qty"] if r else 0

def checked_qty(rid: int, is_dry: bool) -> int:
    col = "drying_id" if is_dry else "casting_id"
    r = db_fetch(
        f"SELECT COALESCE(SUM(checked_quantity),0) AS q FROM casting_quality WHERE {col}=%s",
        (rid,),
    )
    return r[0]["q"] if r else 0

def need_sample(total: int) -> int:
    """Не менше 1 шт або 10% від загального обсягу."""
    return max(1, math.ceil(total * 0.10))

# ────────────────────────────── View ───────────────────────
def view(page: ft.Page, request_no: str = ""):
    page.scroll = ft.ScrollMode.AUTO
    editing_id = {"id": None}
    current    = {"row": None, "is_dry": False}

    # UI controls
    back_btn = ft.ElevatedButton("← Назад")
    title    = ft.Text("Контроль якості лиття", size=24, weight="bold", expand=True)

    dd_req  = ft.Dropdown(label="Номер заявки", width=220)
    dd_part = ft.Dropdown(label="Партія (Артикул/Найм.)", width=520, disabled=True)

    tf_ctrl = ft.TextField(label="Контролер", width=260)
    tf_chk  = ft.TextField(label="Перевірено", width=150, keyboard_type="number")
    tf_def  = ft.TextField(label="Брак", width=150, keyboard_type="number")
    tf_rs   = ft.TextField(label="Опис браку", multiline=True, min_lines=2, expand=True)

    btn_save   = ft.ElevatedButton("Зберегти", disabled=True)
    btn_cancel = ft.ElevatedButton("Скасувати", visible=False)

    total_lbl = ft.Text()

    # очищення форми
    def reset(full: bool = True):
        editing_id["id"] = None
        current.update(row=None, is_dry=False)
        for t in (tf_ctrl, tf_chk, tf_def, tf_rs):
            t.value = ""
        btn_save.disabled = True
        btn_cancel.visible = False
        dd_req.disabled = False
        if full:
            dd_part.value    = None
            dd_part.disabled = True
            total_lbl.value = ""
        page.update()

    # заявки
    dd_req.options = [
        ft.dropdown.Option(r["request_number"])
        for r in db_fetch("SELECT DISTINCT request_number FROM casting ORDER BY request_number DESC")
    ]

    # підвантажити партії
    def reload_parts():
        dd_part.options.clear()
        if not dd_req.value:
            page.update()
            return

        # ❶ З лиття БЕЗ сушки (ключовий фільтр)
        # У product_base більше немає колонки `drying`; замість цього
        # використовується прапорець `drying_needed` (1 — сушка потрібна,
        # 0 — сушка не потрібна). Вибираємо ті відливки, для яких сушіння
        # не потрібно (drying_needed = 0).
        for r in db_fetch(
            """
            SELECT c.id, c.article_code,
                   IFNULL(c.product_name,pb.name) AS n
              FROM casting c
              JOIN product_base pb ON pb.article_code = c.article_code
             WHERE c.request_number=%s
               AND pb.drying_needed = 0
            """,
            (dd_req.value,),
        ):
            rid   = r["id"]
            total = produced_cast(rid)
            done  = checked_qty(rid, False)
            need  = need_sample(total)
            if done < need:
                dd_part.options.append(
                    ft.dropdown.Option(
                        f"#C{rid}  {r['article_code']} ({r['n']}) | Перевірити ≥{need - done} шт."
                    )
                )

        # ❷ Після сушки — тільки завершені сушіння
        for r in db_fetch(
            """
            SELECT d.id, d.article_code, d.product_name AS n
              FROM drying d
             WHERE d.request_number=%s
               AND d.end_time IS NOT NULL
            """,
            (dd_req.value,),
        ):
            rid   = r["id"]
            total = produced_dry(rid)
            done  = checked_qty(rid, True)
            need  = need_sample(total)
            if done < need:
                dd_part.options.append(
                    ft.dropdown.Option(
                        f"#D{rid}  {r['article_code']} ({r['n']}) | Перевірити ≥{need - done} шт."
                    )
                )

        dd_part.disabled = not bool(dd_part.options)
        page.update()

    dd_req.on_change = lambda e: (reset(), reload_parts())

    # вибір партії
    def on_part(e):
        reset(full=False)
        if not dd_part.value:
            return
        tag    = dd_part.value.split()[0]
        is_dry = tag[1] == "D"
        rid    = int(tag[2:])
        current.update(row=rid, is_dry=is_dry)

        total = produced_dry(rid) if is_dry else produced_cast(rid)
        total_lbl.value = f"Загальна к-сть: {total} шт."
        btn_save.disabled = False
        page.update()

    dd_part.on_change = on_part

    # збереження запису
    def save(e):
        if current["row"] is None:
            return
        rid    = current["row"]
        is_dry = current["is_dry"]
        try:
            chk = int(tf_chk.value)
            dft = int(tf_def.value)
            if chk <= 0 or dft < 0 or dft > chk:
                raise ValueError
        except ValueError:
            page.snack_bar = ft.SnackBar(ft.Text("Некоректні значення"), open=True)
            page.update()
            return

        total    = produced_dry(rid) if is_dry else produced_cast(rid)
        accepted = max(0, total - dft)

        sql_sel = (
            "SELECT article_code, COALESCE(product_name,'') AS n FROM casting WHERE id=%s",
            "SELECT article_code, product_name AS n FROM drying WHERE id=%s",
        )[is_dry]
        artrec = db_fetch(sql_sel, (rid,))[0]
        art, name = artrec["article_code"], artrec["n"]

        if editing_id["id"]:
            db_exec(
                """UPDATE casting_quality
                   SET controller_name=%s,
                       checked_quantity=%s,
                       accepted_quantity=%s,
                       defect_quantity=%s,
                       reason=%s
                 WHERE id=%s""",
                (
                    tf_ctrl.value.strip(),
                    chk,
                    accepted,
                    dft,
                    tf_rs.value.strip(),
                    editing_id["id"],
                ),
            )
        else:
            db_exec(
                """INSERT INTO casting_quality
                      (request_number, article_code, product_name,
                       controller_name, checked_quantity,
                       accepted_quantity, defect_quantity,
                       reason, drying_id, casting_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    dd_req.value,
                    art,
                    name,
                    tf_ctrl.value.strip(),
                    chk,
                    accepted,
                    dft,
                    tf_rs.value.strip(),
                    rid if is_dry else None,
                    rid if not is_dry else None,
                ),
            )

        reset()
        refresh()
        reload_parts()

    btn_save.on_click   = save
    btn_cancel.on_click = lambda e: reset(full=False)

    # видалення запису
    confirm = ft.AlertDialog(modal=True)
    pend    = {"id": None}

    def ask_del(rid):
        pend["id"] = rid
        confirm.title   = ft.Text("Видалити запис?")
        confirm.content = ft.Text(f"ID {rid}")
        confirm.actions = [
            ft.TextButton("Ні", on_click=lambda ev: close(False)),
            ft.TextButton("Так", style=ft.ButtonStyle(color=ft.colors.RED),
                          on_click=lambda ev: close(True)),
        ]
        if confirm not in page.overlay:
            page.overlay.append(confirm)
        confirm.open = True
        page.update()

    def close(ok: bool):
        confirm.open = False
        page.update()
        if ok and pend["id"]:
            db_exec("DELETE FROM casting_quality WHERE id=%s", (pend["id"],))
            refresh()
            reload_parts()
        pend["id"] = None

    # історія контролю
    table = ft.DataTable(
        expand=True,
        columns=[ft.DataColumn(ft.Text(h)) for h in (
            "ID","Заявка","ID суш.","ID лит.","Артикул","Найменування",
            "Перевірено","Прийнято","Брак","Контролер","Дії"
        )],
        rows=[],
    )

    def refresh():
        table.rows.clear()
        for r in db_fetch("SELECT * FROM casting_quality ORDER BY id DESC LIMIT 60"):
            is_dry = bool(r["drying_id"])
            rid    = r["drying_id"] or r["casting_id"]
            defect = r["defect_quantity"] or 0

            def mk_edit(rec):
                def _e(ev):
                    editing_id["id"] = rec["id"]
                    dd_req.value    = rec["request_number"]; dd_req.disabled = True
                    tag = ("#D" if rec["drying_id"] else "#C") + str(rid)
                    dd_part.options = [ft.dropdown.Option(tag)]
                    dd_part.value   = tag; dd_part.disabled = True
                    current.update(row=rid, is_dry=is_dry)
                    tf_ctrl.value = rec["controller_name"] or ""
                    tf_chk.value  = str(rec["checked_quantity"])
                    tf_def.value  = str(rec["defect_quantity"])
                    tf_rs.value   = rec["reason"] or ""
                    total_lbl.value = ""
                    btn_save.disabled = False
                    btn_cancel.visible = True
                    page.update()
                return _e

            table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(r["id"]))),
                ft.DataCell(ft.Text(r["request_number"])),
                ft.DataCell(ft.Text(r["drying_id"] or "—")),
                ft.DataCell(ft.Text(r["casting_id"] or "—")),
                ft.DataCell(ft.Text(r["article_code"])),
                ft.DataCell(ft.Text(r["product_name"])),
                ft.DataCell(ft.Text(str(r["checked_quantity"]))),
                ft.DataCell(ft.Text(str(r["accepted_quantity"]))),
                ft.DataCell(ft.Text(str(defect))),
                ft.DataCell(ft.Text(r["controller_name"] or "—")),
                ft.DataCell(ft.Row([
                    ft.IconButton(ft.icons.EDIT, tooltip="Редагувати", on_click=mk_edit(r)),
                    ft.IconButton(ft.icons.DELETE, tooltip="Видалити", icon_color=ft.colors.RED,
                                  on_click=lambda ev, rid=r["id"]: ask_del(rid)),
                ], spacing=4)),
            ]))
        page.update()

    refresh()

    # авто-вибір заявки
    if request_no and any(o.value == request_no for o in dd_req.options):
        dd_req.value = request_no
        reload_parts()

    back_btn.on_click = lambda ev: (page.views.pop(), page.update())

    return ft.View(
        f"/casting_quality/{request_no}",
        # Omit duplicated header/back row; rely on the appbar for navigation and title.
        controls=[
            ft.Row([total_lbl]),
            ft.Row([dd_req, dd_part], spacing=15),
            ft.Row([tf_ctrl, tf_chk, tf_def, btn_save, btn_cancel], spacing=10),
            tf_rs,
            ft.Divider(thickness=2),
            ft.Text("Історія контролю", style="titleMedium"),
            ft.Row([table], expand=True),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
