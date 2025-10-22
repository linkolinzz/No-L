import flet as ft
from database.db_manager import db_fetch
from utils.logger import log

GREEN = "#10B981"
RED   = "#EF4444"

def show_trimming_details(page: ft.Page, request_number: str) -> None:
    log(f"[trimming_details] Open details for {request_number}")

    rows_db = db_fetch(
        """
        SELECT article_code,
               product_name,
               processed_quantity,
               COALESCE(defect_quantity,0) AS defect,
               operator_name
        FROM trimming
        WHERE request_number = %s
        ORDER BY id
        """,
        (request_number,),
    )

    header = ft.Row(
        [
            ft.Text("Артикул", weight="bold", expand=2),
            ft.Text("Найменування", weight="bold", expand=3),
            ft.Text("К-сть", weight="bold", expand=1),
            ft.Text("Брак", weight="bold", expand=1),
            ft.Text("% Браку", weight="bold", expand=1),
            ft.Text("Хороші", weight="bold", expand=1),
            ft.Text("Робітник", weight="bold", expand=2),
            ft.Text("Станок", weight="bold", expand=1),
        ],
        spacing=12,
    )

    items: list[ft.Control] = []
    for r in rows_db:
        qty = int(r["processed_quantity"] or 0)
        defect = int(r["defect"] or 0)
        good = max(qty - defect, 0)
        pct = round(defect / qty * 100) if qty else 0
        items.append(
            ft.Row(
                [
                    ft.Text(r["article_code"], expand=2),
                    ft.Text(r["product_name"], expand=3),
                    ft.Text(str(qty), expand=1),
                    ft.Text(str(defect), expand=1, color=RED),
                    ft.Text(f"{pct} %", expand=1, color=RED),
                    ft.Text(str(good), expand=1, color=GREEN),
                    ft.Text(r.get("operator_name", "—"), expand=2),
                    ft.Text("—", expand=1),
                ],
                spacing=12,
            )
        )

    if not items:
        items = [ft.Text("Немає даних")]

    _open_dialog(page, request_number, "Обрізка", [header, *items])

def _open_dialog(page: ft.Page, req: str, stage: str, rows: list[ft.Control]) -> None:
    table = ft.Column(rows, tight=True, scroll=ft.ScrollMode.AUTO)
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"{stage} — Деталі заявки №{req}"),
        content=ft.Container(table, width=850, height=520, padding=16),
        actions=[ft.TextButton("Закрити", on_click=lambda e: _close(page, dlg))],
        actions_alignment="end",
    )
    page.dialog = dlg
    if dlg not in page.overlay:
        page.overlay.append(dlg)
    dlg.open = True
    page.update()

def _close(page: ft.Page, dlg: ft.AlertDialog) -> None:
    dlg.open = False
    page.update()
