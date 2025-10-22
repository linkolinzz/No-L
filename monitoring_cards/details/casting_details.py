import flet as ft
from database.db_manager import db_fetch
from utils.logger import log

def show_casting_details(page: ft.Page, request_number: str):
    log(f"[casting_details] Open details for {request_number}")

    rows = db_fetch(
        """
        SELECT article_code,
               product_name,
               quantity,
               COALESCE(defect_quantity,0)      AS defect,
               operator_name,
               machine_number
        FROM casting
        WHERE request_number = %s
        """,
        (request_number,)
    )

    header = ft.Row([
        ft.Text("Артикул", weight="bold", expand=2),
        ft.Text("Найменування", weight="bold", expand=3),
        ft.Text("К-сть", weight="bold", expand=1),
        ft.Text("Брак", weight="bold", expand=1),
        ft.Text("% Браку", weight="bold", expand=1),
        ft.Text("Хороші", weight="bold", expand=1),
        ft.Text("Робітник", weight="bold", expand=2),
        ft.Text("Станок", weight="bold", expand=1),
    ], spacing=12)

    items = []
    for r in rows:
        qty = r["quantity"] or 0
        defect = r["defect"] or 0
        good = qty - defect
        pct_defect = int(defect / qty * 100) if qty else 0
        items.append(ft.Row([
            ft.Text(r["article_code"], expand=2),
            ft.Text(r["product_name"], expand=3),
            ft.Text(str(qty), expand=1),
            ft.Text(str(defect), expand=1, color="#EF4444"),
            ft.Text(f"{pct_defect}%", expand=1, color="#EF4444"),
            ft.Text(str(good), expand=1, color="#10B981"),
            ft.Text(r.get("operator_name", "-"), expand=2),
            ft.Text(r.get("machine_number", "-"), expand=1),
        ], spacing=12))

    content = ft.Column([header] + (items or [ft.Text("Немає даних")]),
                        scroll=ft.ScrollMode.AUTO, tight=True)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Лиття — Деталі заявки №{request_number}"),
        content=ft.Container(content, width=800, height=500, padding=16),
        actions=[ft.TextButton("Закрити", on_click=lambda e: close_dialog(page, dlg))]
    )
    page.dialog = dlg
    if dlg not in page.overlay:
        page.overlay.append(dlg)
    dlg.open = True
    page.update()


def close_dialog(page: ft.Page, dlg: ft.AlertDialog):
    dlg.open = False
    page.update()
