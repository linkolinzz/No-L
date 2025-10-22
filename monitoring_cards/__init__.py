# monitoring_cards/__init__.py

import flet as ft
from database.db_manager import db_fetch
from utils.logger import log

# ── Лиття
def build_casting_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching casting data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, quantity, defect_quantity, operator_name, machine_number
        FROM casting
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        qty = r["quantity"] or 0
        defect = r.get("defect_quantity") or 0
        good = qty - defect
        pct = (defect * 100 / qty) if qty else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(f"К-сть: {qty}  Брак: {defect} ({pct:.1f}%)"),
                    ft.Text(f"Гарні: {good}"),
                    ft.Text(f"Оператор: {r.get('operator_name','-')}  Станок: {r.get('machine_number','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Сушка
def build_drying_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching drying data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, qty, operator_name, start_time
        FROM drying
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        start = r.get("start_time")
        start_str = start.strftime("%H:%M") if start else "не стартовано"
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(f"К-сть: {r['qty']}"),
                    ft.Text(f"Оператор: {r.get('operator_name','-')}"),
                    ft.Text(f"Старт: {start_str}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Контроль якості лиття
def build_casting_quality_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching casting_quality data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, product_name, checked_quantity, accepted_quantity, controller_name
        FROM casting_quality
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        checked = r["checked_quantity"] or 0
        accepted = r["accepted_quantity"] or 0
        defect = checked - accepted
        pct = (defect * 100 / checked) if checked else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(r.get("product_name","")),
                    ft.Text(f"Перевірено: {checked}  Прийнято: {accepted}  Брак: {defect} ({pct:.1f}%)"),
                    ft.Text(f"Контролер: {r.get('controller_name','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Обрізка
def build_trimming_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching trimming data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, product_name, processed_quantity, defect_quantity, operator_name
        FROM trimming
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        proc = r["processed_quantity"] or 0
        defect = r["defect_quantity"] or 0
        good = proc - defect
        pct = (defect * 100 / proc) if proc else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(r.get("product_name","")),
                    ft.Text(f"Оброблено: {proc}  Брак: {defect} ({pct:.1f}%)  Гарні: {good}"),
                    ft.Text(f"Оператор: {r.get('operator_name','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Різка
def build_cutting_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching cutting data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, product_name, processed_quantity, defect_quantity, operator_name
        FROM cutting
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        proc = r["processed_quantity"] or 0
        defect = r["defect_quantity"] or 0
        good = proc - defect
        pct = (defect * 100 / proc) if proc else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(r.get("product_name","")),
                    ft.Text(f"Різка: {proc}  Брак: {defect} ({pct:.1f}%)  Гарні: {good}"),
                    ft.Text(f"Оператор: {r.get('operator_name','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Зачистка
def build_cleaning_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching cleaning data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, product_name, processed_quantity, defect_quantity, operator_name
        FROM cleaning
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        proc = r["processed_quantity"] or 0
        defect = r["defect_quantity"] or 0
        good = proc - defect
        pct = (defect * 100 / proc) if proc else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(r.get("product_name","")),
                    ft.Text(f"Зачистка: {proc}  Брак: {defect} ({pct:.1f}%)  Гарні: {good}"),
                    ft.Text(f"Оператор: {r.get('operator_name','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards

# ── Фінальний контроль якості
def build_final_quality_products(page: ft.Page, req: str) -> list[ft.Control]:
    log(f"Fetching final_quality data for {req}", tag="monitoring_cards")
    rows = db_fetch(
        """
        SELECT article_code, product_name, checked_quantity, accepted_quantity, inspector_name
        FROM final_quality
        WHERE request_number = %s
        """,
        (req,)
    )
    cards: list[ft.Control] = []
    for r in rows:
        checked = r["checked_quantity"] or 0
        accepted = r["accepted_quantity"] or 0
        defect = checked - accepted
        pct = (defect * 100 / checked) if checked else 0
        cards.append(
            ft.Container(
                content=ft.Column([
                    ft.Text(r["article_code"], weight="bold"),
                    ft.Text(r.get("product_name","")),
                    ft.Text(f"Перевірено: {checked}  Прийнято: {accepted}  Брак: {defect} ({pct:.1f}%)"),
                    ft.Text(f"Інспектор: {r.get('inspector_name','-')}"),
                ], tight=True),
                padding=10,
                margin=ft.margin.all(5),
                bgcolor="#1f1f2b",
                border_radius=6,
            )
        )
    return cards
