# pages/drying.py
# test comment inserted here
import flet as ft
import datetime, asyncio, threading, concurrent.futures
from database.db_manager import connect_db
import compat

IMER_MINUTES = 1010  # 16 год 50 хв

# ── сумісність із Flet 0.28 ──
if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
    ft.icons = ft.Icons
if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
    ft.colors = ft.Colors

# ─────────────────── GLOBAL ASYNC LOOP ───────────────────
ASYNC_LOOP: asyncio.AbstractEventLoop | None = None
def ensure_async_loop():
    global ASYNC_LOOP
    if ASYNC_LOOP and ASYNC_LOOP.is_running():
        return ASYNC_LOOP
    ASYNC_LOOP = asyncio.new_event_loop()
    threading.Thread(target=ASYNC_LOOP.run_forever, daemon=True).start()
    return ASYNC_LOOP
ensure_async_loop()

# ─────────────────── DB helpers ───────────────────
def db_fetch(sql, p=None):
    with connect_db() as cn:
        cu = cn.cursor(dictionary=True)
+       cu.execute(sql, p or ())
+        return cu.fetchall()
+
+def db_exec(sql, p=None):
+    with connect_db() as cn:
+        cu = cn.cursor()
+        cu.execute(sql, p or ())
+        cn.commit()
+
+# ─────────────────── ensure columns / indexes ───────────────────
+def ensure_cols():
+    cols = {
+        "casting_id": "INT NULL",
+        "start_time": "DATETIME NULL",
+        "end_time":   "DATETIME NULL",
+        "created_at": "DATETIME NULL DEFAULT CURRENT_TIMESTAMP",
+    }
+    tables = ("drying", "drying_no_request")
+    for tbl in tables:
+        for c, t in cols.items():
+            try:
+                db_exec(f"ALTER TABLE {tbl} ADD COLUMN {c} {t}")
+            except Exception:
+                pass
+    # унікальність по casting_id, щоб ON DUPLICATE працював
+    try:
+        db_exec("ALTER TABLE drying ADD UNIQUE KEY uq_drying_casting (casting_id)")
+    except Exception:
+        pass
+ensure_cols()
+
+# ─────────────────── helpers ───────────────────
+def casts_without_drying(req_number: str):
+    return db_fetch(
+        """
+        SELECT c.id,
+               c.request_number,
+               c.article_code,
+               IFNULL(c.product_name, pb.name) AS pname,
+               (c.quantity - IFNULL(c.defect_quantity,0)) AS good
+          FROM casting c
+          JOIN product_base pb
+            ON pb.article_code = c.article_code AND pb.drying_needed = 1
+         WHERE c.request_number = %s
+           AND NOT EXISTS (SELECT 1 FROM drying d WHERE d.casting_id = c.id)
+        """,
+        (req_number,),
+    )
+
+def min_remaining_minutes():
+    """
+    Обчислити мінімальну кількість хвилин до завершення сушіння
+    (для всіх сушінь, у т.ч. без заявки).
+    Повертає None, якщо запущених сушінь немає.
+    """
+    m1 = None
+    row1 = db_fetch(
+        "SELECT MIN(TIMESTAMPDIFF(MINUTE,NOW(),end_time)) AS m "
+        "FROM drying WHERE end_time IS NOT NULL AND NOW() < end_time"
+    )
+    if row1 and row1[0]["m"] is not None:
+        m1 = row1[0]["m"]
+    m2 = None
+    row2 = db_fetch(
+        "SELECT MIN(TIMESTAMPDIFF(MINUTE,NOW(),end_time)) AS m "
+        "FROM drying_no_request WHERE end_time IS NOT NULL AND NOW() < end_time"
+    )
+    if row2 and row2[0]["m"] is not None:
+        m2 = row2[0]["m"]
+    if m1 is not None and m2 is not None:
+        return m1 if m1 < m2 else m2
+    return m1 if m2 is None else m2
+
+def fmt_left(mins: int | None) -> str:
+    if mins is None or mins <= 0:
+        return "—"
+    h = mins // 60
+    m = mins % 60
+    return f"Залишилось: {h} год {m:02d} хв"
+
+# ─────────────────── VIEW ───────────────────
+def view(page: ft.Page, request_no: str = ""):
+    page.scroll = ft.ScrollMode.AUTO
+
+    # --- режим роботи: за заявкою або без заявки ---
+    # mode['value'] може бути 'req' (сушка за заявкою) або 'no_req' (без заявки).
+    mode = {"value": "req"}
+    dd_mode = ft.Dropdown(
+        label="Тип сушіння",
+        width=200,
+        options=[
+            ft.dropdown.Option("Сушка по заявці"),
+            ft.dropdown.Option("Сушка без заявки"),
+        ],
+        value="Сушка по заявці",
+    )
+
+    def casts_no_req_without_drying():
+        """
+        Повертає перелік записів із casting_no_request, які ще не мають запису
+        у drying_no_request. Використовується для режиму без заявки.
+        """
+        return db_fetch(
+            """
+            SELECT cnr.id,
+                   cnr.article_code,
+                   IFNULL(cnr.product_name,pb.name) AS pname,
+                   (cnr.quantity - IFNULL(cnr.defect_quantity,0)) AS good
+              FROM casting_no_request cnr
+              JOIN product_base pb ON pb.article_code = cnr.article_code
+             WHERE pb.drying_needed = 1
+               AND NOT EXISTS (
+                    SELECT 1 FROM drying_no_request dnr WHERE dnr.casting_id = cnr.id
+                )
+            ORDER BY cnr.id
+            """
+        )
+
+    # ---------- навігація назад до головного меню ----------
+    def go_back(e):
+        while len(page.views) > 2:
+            page.views.pop()
+        page.update()
+
+    # ---------- UI controls ----------
+    back_btn  = ft.ElevatedButton("← Назад", on_click=go_back)
+    title_txt = ft.Text("Сушка", size=24, weight="bold", expand=True)
+
+    dd_req     = ft.Dropdown(label="Номер заявки", width=150)
+    dd_art     = ft.Dropdown(label="Партія (артикул / id лиття)", width=420, disabled=True)
+    timer_lbl  = ft.Text("—", size=20, weight="bold", color=ft.colors.ORANGE_ACCENT)
+    start_btn  = ft.ElevatedButton("Старт", icon=ft.icons.TIMER,
+                    style=ft.ButtonStyle(bgcolor=ft.colors.GREEN, color=ft.colors.WHITE),
+                    disabled=True)
+    tf_need    = ft.TextField(label="Добра к-сть", width=140, read_only=True, text_align=ft.TextAlign.CENTER)
+    tf_worker  = ft.TextField(label="ПІБ робітника", width=260)
+    save_btn   = ft.ElevatedButton("Зберегти", disabled=True)
+
+    tbl = ft.DataTable(
+        expand=True,
+        columns=[ft.DataColumn(ft.Text(h)) for h in (
+            "ID", "Заявка", "ID лиття", "Артикул", "Найменування", "К-сть",
+            "Робітник", "Старт", "Кінець", "Дії"
+        )],
+        rows=[],
+    )
+
+    selected_cast_id: int | None = None
+    countdown_future: concurrent.futures.Future | None = None
+
+    # ---------- countdown logic ----------
+    async def global_countdown():
+        while True:
+            mm = min_remaining_minutes()
+            timer_lbl.value = fmt_left(mm)
+            page.update()
+            if mm is None or mm <= 0:
+                return
+            await asyncio.sleep(60)
+
+    def restart_timer():
+        nonlocal countdown_future
+        loop = ensure_async_loop()
+        if countdown_future and not countdown_future.done():
+            countdown_future.cancel()
+        timer_lbl.value = fmt_left(min_remaining_minutes())
+        page.update()
+        mm = min_remaining_minutes()
+        if mm and mm > 0:
+            countdown_future = asyncio.run_coroutine_threadsafe(global_countdown(), loop)
+
+    # ---------- form helpers ----------
+    def reset_form():
+        nonlocal selected_cast_id
+        selected_cast_id = None
+        tf_need.value = ""
+        tf_worker.value = ""
+        save_btn.disabled = True
+        dd_art.value = None
+        dd_art.disabled = True
+        page.update()
+
+    def reload_batches():
+        """Оновити список партій для сушіння залежно від режиму"""
+        dd_art.options = []
+        # режим за заявкою
+        if mode["value"] == "req":
+            if not dd_req.value:
+                page.update()
+                return
+            opts = [
+                ft.dropdown.Option(f"#{r['id']}  {r['article_code']} ({r['pname']})")
+                for r in casts_without_drying(dd_req.value)
+            ]
+        else:
+            # без заявки: використовуємо casting_no_request
+            opts = [
+                ft.dropdown.Option(f"#{r['id']}  {r['article_code']} ({r['pname']})")
+                for r in casts_no_req_without_drying()
+            ]
+        dd_art.options = opts
+        dd_art.disabled = not bool(opts)
+        page.update()
+
+    def refresh_table():
+        tbl.rows.clear()
+        # вибираємо таблицю залежно від режиму
+        rows = []
+        if mode["value"] == "req":
+            rows = db_fetch("SELECT * FROM drying ORDER BY id DESC")
+        else:
+            rows = db_fetch("SELECT * FROM drying_no_request ORDER BY id DESC")
+        for r in rows:
+            req_num = r.get("request_number") or "—"
+            tbl.rows.append(
+                ft.DataRow(cells=[
+                    ft.DataCell(ft.Text(r["id"])),
+                    ft.DataCell(ft.Text(req_num)),
+                    ft.DataCell(ft.Text(r.get("casting_id") or "—")),
+                    ft.DataCell(ft.Text(r["article_code"])),
+                    ft.DataCell(ft.Text(r.get("product_name") or "—")),
+                    ft.DataCell(ft.Text(str(r.get("qty")))),
+                    ft.DataCell(ft.Text(r.get("operator_name") or "—")),
+                    ft.DataCell(ft.Text(r["start_time"].strftime("%d.%m %H:%M") if r.get("start_time") else "—")),
+                    ft.DataCell(ft.Text(r["end_time"].strftime("%d.%m %H:%M") if r.get("end_time") else "—")),
+                    ft.DataCell(
+                        ft.IconButton(ft.icons.DELETE, icon_color=ft.colors.RED,
+                                      on_click=lambda e, rid=r["id"]: ask_delete(rid))
+                    ),
+                ])
+            )
+        page.update()
+
+    def update_start_btn():
+        """Оновити доступність кнопки "Старт" залежно від режиму"""
+        if mode["value"] == "req":
+            # Старт доступний тільки якщо є відливки без сушіння або незапущені сушіння
+            if not dd_req.value:
+                start_btn.disabled = True
+            else:
+                need_insert = bool(casts_without_drying(dd_req.value))
+                has_unstarted = bool(db_fetch(
+                    "SELECT 1 FROM drying WHERE request_number=%s AND start_time IS NULL LIMIT 1",
+                    (dd_req.value,),
+                ))
+                start_btn.disabled = not (need_insert or has_unstarted)
+        else:
+            # без заявки: перевіряємо наявність відливок без сушіння та незапущених сушінь
+            need_insert = bool(casts_no_req_without_drying())
+            has_unstarted = bool(db_fetch(
+                "SELECT 1 FROM drying_no_request WHERE start_time IS NULL LIMIT 1"
+            ))
+            start_btn.disabled = not (need_insert or has_unstarted)
+        page.update()
+
+    # ---------- events ----------
+    dd_req.on_change = lambda e: (reset_form(), reload_batches(), update_start_btn())
+
+    # --- зміна режиму сушіння ---
+    def on_mode_change(e):
+        sel = dd_mode.value
+        if sel == "Сушка по заявці":
+            mode["value"] = "req"
+            dd_req.visible = True
+            dd_req.disabled = False
+            # завантажити список заявок з таблиці casting
+            rows = db_fetch(
+                "SELECT DISTINCT request_number FROM casting ORDER BY request_number DESC"
+            )
+            dd_req.options = [ft.dropdown.Option(r["request_number"]) for r in rows]
+            dd_req.value = None
+        else:
+            mode["value"] = "no_req"
+            dd_req.visible = False
+            dd_req.disabled = True
+            dd_req.value = None
+        # скинути форму та оновити дані
+        reset_form()
+        reload_batches()
+        refresh_table()
+        update_start_btn()
+        page.update()
+
+    # призначити обробник зміни режиму
+    dd_mode.on_change = on_mode_change
+
+    def on_art_change(e):
+        nonlocal selected_cast_id
+        if not dd_art.value:
+            reset_form()
+            return
+        selected_cast_id = int(dd_art.value.split()[0][1:])
+        # обчислюємо кількість по-іншому залежно від режиму
+        if mode["value"] == "req":
+            qty = db_fetch(
+                "SELECT quantity - IFNULL(defect_quantity,0) AS q FROM casting WHERE id=%s",
+                (selected_cast_id,),
+            )[0]["q"]
+        else:
+            # для записів без заявки отримуємо з casting_no_request
+            row = db_fetch(
+                "SELECT quantity, COALESCE(defect_quantity,0) AS d FROM casting_no_request WHERE id=%s",
+                (selected_cast_id,),
+            )
+            qty = 0
+            if row:
+                qty = (row[0]["quantity"] or 0) - (row[0].get("d") or 0)
+        tf_need.value = str(qty)
+        save_btn.disabled = False
+        page.update()
+
+    dd_art.on_change = on_art_change
+
+    def save_record(e):
+        if not selected_cast_id or not tf_worker.value.strip():
+            page.snack_bar = ft.SnackBar(ft.Text("Заповніть усі поля"), open=True)
+            page.update()
+            return
+        if mode["value"] == "req":
+            # для заявок беремо дані з таблиці casting
+            cast = db_fetch(
+                """
+                SELECT c.request_number, c.article_code,
+                       IFNULL(c.product_name,pb.name) AS pname,
+                       (c.quantity - IFNULL(c.defect_quantity,0)) AS good
+                  FROM casting c
+                  JOIN product_base pb ON pb.article_code = c.article_code
+                 WHERE c.id=%s
+                """,
+                (selected_cast_id,),
+            )[0]
+            db_exec(
+                """
+                INSERT INTO drying
+                  (request_number, article_code, product_name,
+                   qty, operator_name, casting_id)
+                VALUES (%s,%s,%s,%s,%s,%s)
+                ON DUPLICATE KEY UPDATE
+                    operator_name = VALUES(operator_name),
+                    qty = VALUES(qty)
+                """,
+                (
+                    cast["request_number"],
+                    cast["article_code"],
+                    cast["pname"],
+                    cast["good"],
+                    tf_worker.value.strip(),
+                    selected_cast_id,
+                ),
+            )
+        else:
+            # без заявки: беремо дані з casting_no_request
+            row = db_fetch(
+                """
+                SELECT article_code, product_name, quantity, COALESCE(defect_quantity,0) AS d
+                  FROM casting_no_request
+                 WHERE id=%s
+                """,
+                (selected_cast_id,),
+            )
+            if row:
+                art = row[0]["article_code"]
+                name = row[0]["product_name"] or ""
+                good = (row[0]["quantity"] or 0) - (row[0].get("d") or 0)
+                db_exec(
+                    """
+                    INSERT INTO drying_no_request
+                      (casting_id, article_code, product_name,
+                       qty, operator_name)
+                    VALUES (%s,%s,%s,%s,%s)
+                    ON DUPLICATE KEY UPDATE
+                        operator_name = VALUES(operator_name),
+                        qty = VALUES(qty)
+                    """,
+                    (
+                        selected_cast_id,
+                        art,
+                        name,
+                        good,
+                        tf_worker.value.strip(),
+                    ),
+                )
+        page.snack_bar = ft.SnackBar(ft.Text("Збережено"), open=True)
+        refresh_table()
+        reload_batches()
+        update_start_btn()
+
+    save_btn.on_click = save_record
+
+    def start_all(e):
+        # запуск сушіння залежно від режиму
+        if start_btn.disabled:
+            return
+        now = datetime.datetime.now()
+        end = now + datetime.timedelta(minutes=TIMER_MINUTES)
+        if mode["value"] == "req":
+            # необхідна заявка для запуску
+            if not dd_req.value:
+                return
+            # 1) вставити всі відсутні drying для цієї заявки
+            for r in casts_without_drying(dd_req.value):
+                db_exec(
+                    """
+                    INSERT INTO drying
+                      (request_number, article_code, product_name,
+                       qty, operator_name, start_time, end_time, casting_id)
+                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
+                    """,
+                    (
+                        r["request_number"],
+                        r["article_code"],
+                        r["pname"],
+                        r["good"],
+                        tf_worker.value.strip() or "—",
+                        now, end,
+                        r["id"],
+                    ),
+                )
+            # 2) запустити незапущені drying у межах ВИБРАНОЇ заявки
+            db_exec(
+                "UPDATE drying SET start_time=%s, end_time=%s "
+                "WHERE request_number=%s AND start_time IS NULL",
+                (now, end, dd_req.value),
+            )
+        else:
+            # без заявки: вставити усі відсутні drying_no_request
+            for r in casts_no_req_without_drying():
+                db_exec(
+                    """
+                    INSERT INTO drying_no_request
+                      (casting_id, article_code, product_name,
+                       qty, operator_name, start_time, end_time)
+                    VALUES (%s,%s,%s,%s,%s,%s,%s)
+                    """,
+                    (
+                        r["id"],
+                        r["article_code"],
+                        r["pname"],
+                        r["good"],
+                        tf_worker.value.strip() or "—",
+                        now, end,
+                    ),
+                )
+            # 2) запустити незапущені сушіння без заявки
+            db_exec(
+                "UPDATE drying_no_request SET start_time=%s, end_time=%s WHERE start_time IS NULL",
+                (now, end),
+            )
+        page.snack_bar = ft.SnackBar(ft.Text("Сушку запущено"), open=True)
+        refresh_table()
+        reload_batches()
+        update_start_btn()
+        restart_timer()
+
+    start_btn.on_click = start_all
+
+    # видалення
+    confirm = ft.AlertDialog(modal=True)
+    def ask_delete(rid: int):
+        confirm.title   = ft.Text("Видалити запис?")
+        confirm.content = ft.Text(f"ID {rid}")
+        confirm.actions = [
+            ft.TextButton("Ні", on_click=lambda ev: close(False)),
+            ft.TextButton("Так", style=ft.ButtonStyle(color=ft.colors.RED),
+                          on_click=lambda ev: close(True, rid)),
+        ]
+        if confirm not in page.overlay:
+            page.overlay.append(confirm)
+        confirm.open = True
+        page.update()
+
+    def close(ok: bool, rid: int | None = None):
+        confirm.open = False
+        page.update()
+        if ok and rid is not None:
+            # видаляємо запис з відповідної таблиці залежно від режиму
+            if mode["value"] == "req":
+                db_exec("DELETE FROM drying WHERE id=%s", (rid,))
+            else:
+                db_exec("DELETE FROM drying_no_request WHERE id=%s", (rid,))
+            refresh_table()
+            reload_batches()
+            update_start_btn()
+
+    # ---------- init ----------
+    dd_req.options = [
+        ft.dropdown.Option(r["request_number"])
+        for r in db_fetch("SELECT DISTINCT request_number FROM casting ORDER BY request_number DESC")
+    ]
+    if request_no and any(o.value == request_no for o in dd_req.options):
+        dd_req.value = request_no
+        reload_batches()
+        update_start_btn()
+        restart_timer()
+
+    refresh_table()
+    update_start_btn()
+    restart_timer()
+
+    # встановлюємо початковий режим відповідно до значення dd_mode
+    on_mode_change(None)
+
+    # ---------- layout ----------
+    return ft.View(
+        f"/drying/{request_no}",
+        # Do not duplicate the back button and page title here; the launcher appbar handles it.
+        controls=[
+            # режим сушіння, номер заявки (для режиму за заявкою) та партія
+            ft.Row([dd_mode, dd_req, dd_art], spacing=12),
+            ft.Row([timer_lbl, start_btn], alignment=ft.MainAxisAlignment.END, spacing=12),
+            ft.Divider(),
+            ft.Row([tf_need, tf_worker, save_btn], spacing=10),
+            ft.Divider(thickness=2),
+            ft.Text("Записи сушіння", style="titleMedium"),
+            ft.Row([tbl], expand=True),
+        ],
+        scroll=ft.ScrollMode.AUTO,
+    )
