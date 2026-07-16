# pages/final_quality.py
# – перевіряємо кожну партію окремо,
#   штовхаємо повідомлення та автоматично
#   закриваємо заявку, коли всі вироби готові.

import math
import flet as ft
from database.db_manager import connect_db
from utils.notifications import push, request_closed   # ← повідомлення
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

# ────────── ensure extra columns ──────────
for col in (
    "drying_id INT NULL",
    "trimming_id INT NULL",
    "cutting_id INT NULL",
    "cleaning_id INT NULL",
):
    try:
        db_exec(f"ALTER TABLE final_quality ADD COLUMN {col}")
    except Exception:
        pass

# ────────── qty helpers ──────────
def need_sample(total: int) -> int:
    return max(1, math.ceil(total * 0.10))

def part_qty(src: str, pid: int) -> int:
    """Повертає добру кількість у партії (після дефектів на попередніх стадіях)."""
    if src == "DR":
        r = db_fetch("SELECT qty FROM drying WHERE id=%s", (pid,))
        return r[0]["qty"] if r else 0
    if src == "TR":
        r = db_fetch(
            "SELECT processed_quantity, defect_quantity FROM trimming WHERE id=%s",
            (pid,),
        )
        return (r[0]["processed_quantity"] - (r[0]["defect_quantity"] or 0)) if r else 0
    if src == "CU":
        r = db_fetch(
            "SELECT processed_quantity, defect_quantity FROM cutting WHERE id=%s",
            (pid,),
        )
        return (r[0]["processed_quantity"] - (r[0]["defect_quantity"] or 0)) if r else 0
    if src == "CL":
        r = db_fetch(
            "SELECT processed_quantity, defect_quantity FROM cleaning WHERE id=%s",
            (pid,),
        )
        return (r[0]["processed_quantity"] - (r[0]["defect_quantity"] or 0)) if r else 0
    return 0

def already_checked(src: str, pid: int) -> int:
    col = {"DR": "drying_id", "TR": "trimming_id", "CU": "cutting_id", "CL": "cleaning_id"}[src]
    r = db_fetch(
        f"SELECT COALESCE(SUM(checked_quantity),0) c FROM final_quality WHERE {col}=%s",
        (pid,),
    )
    return r[0]["c"] if r else 0

# ────────── джерело для ФКЯ за прапорцями виробу ──────────
def _detect_fq_source(article_code: str) -> tuple[str, str, str]:
    """
    Повертає (table, fk_column, prefix) для джерела партій ФКЯ
    згідно прапорців у product_base.
    """
    row = db_fetch(
        "SELECT trimming_needed, cutting_needed, cleaning_needed FROM product_base WHERE article_code=%s",
        (article_code,),
    )
    t = row[0] if row else {"trimming_needed": 0, "cutting_needed": 0, "cleaning_needed": 0}

    if int(t.get("cleaning_needed") or 0) == 1:
        return ("cleaning", "cleaning_id", "CL")
    if int(t.get("cutting_needed") or 0) == 1:
        return ("cutting", "cutting_id", "CU")
    if int(t.get("trimming_needed") or 0) == 1:
        return ("trimming", "trimming_id", "TR")
    return ("drying", "drying_id", "DR")

def _ready_sum_for_article(req_no: str, article_code: str) -> int:
    """Сумарна «готова» кількість для статті згідно її джерела."""
    table, fk_col, prefix = _detect_fq_source(article_code)
    if table == "drying":
        sql = "SELECT COALESCE(SUM(qty),0) v FROM drying WHERE request_number=%s AND article_code=%s AND end_time IS NOT NULL"
    else:
        sql = f"SELECT COALESCE(SUM(processed_quantity-IFNULL(defect_quantity,0)),0) v FROM {table} WHERE request_number=%s AND article_code=%s"
    return db_fetch(sql, (req_no, article_code,))[0]["v"]

# ────────── перевірка «заявка закрита» ──────────
def check_request_closed(req_number: str):
    """
    Якщо accepted по кожному артикулу заявки >= сумарної «готової» к-сті з відповідної стадії
    (визначеної за прапорцями), заявка вважається закритою.
    """
    rows = db_fetch(
        "SELECT DISTINCT article_code FROM casting_requests WHERE request_number=%s",
        (req_number,),
    )
    for r in rows:
        code = r["article_code"]
        ready = _ready_sum_for_article(req_number, code)
        final = db_fetch(
            "SELECT COALESCE(SUM(accepted_quantity),0) f FROM final_quality WHERE request_number=%s AND article_code=%s",
            (req_number, code),
        )[0]["f"]
        if final < ready:
            return
    request_closed(req_number)

# ───────────────────────── View ─────────────────────────
def view(page: ft.Page, request_no: str = ""):
    page.scroll = ft.ScrollMode.AUTO
    editing = {"id": None, "src": None, "pid": None}

    # поточна «К-сть партії» для обраної партії
    current_total = 0

    # ─── навігація назад до головного меню ───
    def go_back(e):
        while len(page.views) > 2:
            page.views.pop()
        page.update()

    # ---------- UI ----------
    back_btn = ft.ElevatedButton("← Назад", on_click=go_back)
    title = ft.Text("Фінальний контроль якості", size=24, weight="bold", expand=True)

    dd_req = ft.Dropdown(label="Номер заявки", width=240)
    dd_part = ft.Dropdown(label="Партія (Артикул/Найм.)", width=520, disabled=True)

    tf_insp = ft.TextField(label="ПІБ інспектора", width=280, disabled=True)
    tf_chk  = ft.TextField(label="Перевірено (шт.)", width=160, keyboard_type="number", disabled=True)

    # НОВЕ: Брак (шт.) – ручне поле
    tf_def  = ft.TextField(label="Брак (шт.)", width=160, keyboard_type="number", disabled=True)

    # Прийнято (шт.) – тільки для читання, автопідстановка
    tf_acc  = ft.TextField(label="Прийнято (шт.)", width=160, read_only=True, disabled=True,
                           tooltip="Авто: К-сть партії − Брак")

    btn_save = ft.ElevatedButton("Зберегти", disabled=True)
    btn_cancel = ft.ElevatedButton("Скасувати", visible=False)

    total_lbl, left_lbl = ft.Text(), ft.Text()

    # ---------- helpers ----------
    def show_snack(msg: str):
        page.snack_bar = ft.SnackBar(ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    def _as_int(v) -> int:
        try:
            return max(0, int(str(v).strip()))
        except Exception:
            return 0

    def recalc_accept(_=None):
        """Перерахунок Прийнято = current_total − Брак."""
        defect = _as_int(tf_def.value)
        acc = current_total - defect
        if acc < 0:
            acc = 0
        if acc > current_total:
            acc = current_total
        tf_acc.value = str(acc)
        page.update()

    def reset(full: bool = True):
        editing.update(id=None, src=None, pid=None)
        for t in (tf_insp, tf_chk, tf_def, tf_acc):
            t.value = ""
            t.disabled = True
        btn_save.disabled = True
        btn_cancel.visible = False
        if full:
            dd_part.value = None
            dd_part.disabled = True
            total_lbl.value = ""
            left_lbl.value = ""
        page.update()

    # ---------- load requests ----------
    dd_req.options = [
        ft.dropdown.Option(r["request_number"])
        for r in db_fetch("SELECT DISTINCT request_number FROM casting_requests ORDER BY request_number")
    ]
    dd_req.on_change = lambda e: (reset(), reload_parts())
    page.update()

    # авто-вибір із Моніторингу
    if request_no and any(o.value == request_no for o in dd_req.options):
        dd_req.value = request_no

    # ---------- load parts (з урахуванням прапорців Б/В) ----------
    def reload_parts():
        dd_part.options.clear()
        if not dd_req.value:
            page.update()
            return
        req = dd_req.value

        # по кожному артикулу заявки визначаємо джерело
        articles = db_fetch(
            "SELECT DISTINCT cr.article_code, IFNULL(pb.name,'') name "
            "FROM casting_requests cr LEFT JOIN product_base pb ON pb.article_code=cr.article_code "
            "WHERE cr.request_number=%s",
            (req,),
        )

        for a in articles:
            art = a["article_code"]
            name = a["name"]
            table, fk_col, prefix = _detect_fq_source(art)

            # беремо партії з потрібної стадії
            if table == "drying":
                rows = db_fetch(
                    "SELECT id, article_code, product_name FROM drying "
                    "WHERE request_number=%s AND article_code=%s AND end_time IS NOT NULL "
                    "ORDER BY id DESC",
                    (req, art),
                )
            else:
                rows = db_fetch(
                    f"SELECT id, article_code, product_name, processed_quantity, defect_quantity "
                    f"FROM {table} WHERE request_number=%s AND article_code=%s ORDER BY id DESC",
                    (req, art),
                )

            for r in rows:
                pid = r["id"]
                tot = part_qty(prefix, pid)
                done = already_checked(prefix, pid)
                # якщо вже виконали норму перевірки — пропускаємо
                if done >= need_sample(tot):
                    continue
                left = max(0, need_sample(tot) - done)
                dd_part.options.append(
                    ft.dropdown.Option(
                        f"#{prefix}{pid}  {r['article_code']} ({r['product_name']}) | "
                        f"Готово {tot - done} шт. | ▶ {left} шт."
                    )
                )

        dd_part.disabled = not bool(dd_part.options)
        page.update()

    # ---------- part chosen ----------
    def on_part_change(e):
        nonlocal current_total
        reset(full=False)
        if not dd_part.value:
            return
        tag = dd_part.value.split()[0]  # "#CU17"
        editing.update(src=tag[1:3], pid=int(tag[3:]))

        current_total = part_qty(editing["src"], editing["pid"])
        done = already_checked(editing["src"], editing["pid"])
        total_lbl.value = f"Загальна к-сть партії: {current_total} шт."
        left_lbl.value = f"Ще потрібно перевірити: {max(0, need_sample(current_total) - done)} шт."

        for t in (tf_insp, tf_chk, tf_def, tf_acc):
            t.disabled = False
        tf_acc.read_only = True  # авто
        if not tf_def.value:
            tf_def.value = "0"
        recalc_accept()
        btn_save.disabled = False
        page.update()

    dd_part.on_change = on_part_change

    # ---------- SAVE / UPDATE ----------
    def save_record(e):
        nonlocal current_total
        try:
            chk = _as_int(tf_chk.value)
            defect = _as_int(tf_def.value)
            if defect > current_total:
                raise ValueError("defect>total")
            acc = max(0, current_total - defect)
        except Exception:
            show_snack("Некоректні кількості")
            return

        if editing["id"] is not None:  # UPDATE
            db_exec(
                """
                UPDATE final_quality
                   SET inspector_name=%s,
                       checked_quantity=%s,
                       accepted_quantity=%s
                 WHERE id=%s
                """,
                (tf_insp.value, chk, acc, editing["id"]),
            )
            art = db_fetch("SELECT article_code FROM final_quality WHERE id=%s", (editing["id"],))[0]["article_code"]
            src, pid = editing["src"], editing["pid"]
        else:  # INSERT
            src, pid = editing["src"], editing["pid"]
            # витягуємо артикул та найменування з відповідної таблиці
            art, name = db_fetch(
                {
                    "DR": "SELECT article_code, product_name FROM drying   WHERE id=%s",
                    "TR": "SELECT article_code, product_name FROM trimming WHERE id=%s",
                    "CU": "SELECT article_code, product_name FROM cutting  WHERE id=%s",
                    "CL": "SELECT article_code, product_name FROM cleaning WHERE id=%s",
                }[src],
                (pid,),
            )[0].values()
            ids = {"drying_id": None, "trimming_id": None, "cutting_id": None, "cleaning_id": None}
            ids[{"DR": "drying_id", "TR": "trimming_id", "CU": "cutting_id", "CL": "cleaning_id"}[src]] = pid
            db_exec(
                """
                INSERT INTO final_quality
                (request_number,article_code,product_name,
                 inspector_name,checked_quantity,accepted_quantity,
                 drying_id,trimming_id,cutting_id,cleaning_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    dd_req.value,
                    art,
                    name,
                    tf_insp.value,
                    chk,
                    acc,  # прийнято = total - defect
                    ids["drying_id"],
                    ids["trimming_id"],
                    ids["cutting_id"],
                    ids["cleaning_id"],
                ),
            )

        # ---------- push notification ----------
        tot = part_qty(src, pid)
        done = already_checked(src, pid)
        if done >= need_sample(tot):
            push(f"Партія {pid} ({art}) заявки №{dd_req.value} пройшла ФКЯ та готова до передачі на склад")

        # ---------- check close ----------
        check_request_closed(dd_req.value)

        reset()
        refresh_table()
        reload_parts()

    btn_save.on_click = save_record
    btn_cancel.on_click = lambda e: reset(full=False)

    # ─── таблиця ──────────────────────────────────────────
    table = ft.DataTable(
        expand=True,
        columns=[ft.DataColumn(ft.Text(h)) for h in ("ID", "Заявка", "Артикул", "Найменування", "Перевірено", "Прийнято", "Брак", "Інспектор", "Дії")],
        rows=[],
    )

    def _row_src_pid(rec) -> tuple[str, int]:
        if rec.get("drying_id"):
            return "DR", rec["drying_id"]
        if rec.get("trimming_id"):
            return "TR", rec["trimming_id"]
        if rec.get("cutting_id"):
            return "CU", rec["cutting_id"]
        return "CL", rec["cleaning_id"]

    def refresh_table():
        table.rows.clear()
        # фільтруємо по вибраній заявці для зручності (як у trimming)
        rows = (
            db_fetch("SELECT * FROM final_quality WHERE request_number=%s ORDER BY id DESC", (dd_req.value,))
            if dd_req.value
            else db_fetch("SELECT * FROM final_quality ORDER BY id DESC LIMIT 60")
        )
        for r in rows:
            # обчислюємо К-сть партії за джерелом запису і виводимо Брак як total - accepted
            src, pid = _row_src_pid(r)
            tot = part_qty(src, pid)
            defect = max(0, int(tot) - int(r["accepted_quantity"] or 0))

            def make_edit_handler(rec):
                def _edit(_e):
                    nonlocal current_total
                    editing["id"] = rec["id"]
                    # визначаємо джерело для підрахунків
                    src2, pid2 = _row_src_pid(rec)
                    editing.update(src=src2, pid=pid2)

                    dd_req.value = rec["request_number"]
                    reload_parts()
                    dd_part.value = ""      # змінювати партію при редагуванні заборонено
                    dd_part.disabled = True

                    # заповнюємо поля
                    current_total = part_qty(src2, pid2)
                    tf_insp.disabled = tf_chk.disabled = tf_def.disabled = tf_acc.disabled = False
                    tf_insp.value = rec["inspector_name"] or ""
                    tf_chk.value = str(rec["checked_quantity"])
                    # дефект = total - accepted (клацання старих записів теж коректно заповнить)
                    tf_def.value = str(max(0, current_total - int(rec["accepted_quantity"] or 0)))
                    tf_acc.read_only = True
                    recalc_accept()

                    btn_save.disabled = False
                    btn_cancel.visible = True
                    total_lbl.value = ""
                    left_lbl.value = ""
                    page.update()
                return _edit

            table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(r["id"]))),
                        ft.DataCell(ft.Text(r["request_number"])),
                        ft.DataCell(ft.Text(r["article_code"])),
                        ft.DataCell(ft.Text(r["product_name"] or "—")),
                        ft.DataCell(ft.Text(str(r["checked_quantity"]))),
                        ft.DataCell(ft.Text(str(r["accepted_quantity"]))),
                        ft.DataCell(ft.Text(str(defect))),
                        ft.DataCell(ft.Text(r["inspector_name"] or "—")),
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
                    ]
                )
            )
        page.update()

    # ─── видалення (як у trimming.py) ─────────────────────
    confirm_dlg = ft.AlertDialog(modal=True)
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
            # якщо видаляємо поточний запис у режимі редагування — скинемо форму
            if editing["id"] == record_to_delete["id"]:
                reset(full=False)
            db_exec("DELETE FROM final_quality WHERE id=%s", (record_to_delete["id"],))
            refresh_table()
            reload_parts()
        record_to_delete["id"] = None

    # зміни полів, що впливають на автоперерахунок/доступність Зберегти
    tf_def.on_change = recalc_accept

    # ---------- init ----------
    refresh_table()

    return ft.View(
        f"/final_quality/{request_no}",
        # Omit the redundant back button and title; the appbar added by the launcher
        # supplies these.  Begin directly with the form and table sections.
        controls=[
            ft.Row([dd_req, dd_part], spacing=12),
            ft.Row([total_lbl, left_lbl]),
            ft.Row([tf_insp, tf_chk, tf_def, tf_acc, btn_save, btn_cancel], spacing=10),
            ft.Divider(thickness=2),
            ft.Text("Журнал фінального контролю", style="titleMedium"),
            ft.Row([table], expand=True),
        ],
        scroll=ft.ScrollMode.AUTO,
    )
