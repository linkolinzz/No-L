# pages/warehouse.py
import flet as ft
from pages.warehouse.incoming import incoming_view
from pages.warehouse.balances import balances_view
from pages.warehouse.shipping import shipping_view
from pages.warehouse.analytics import analytics_view

def warehouse_view(page: ft.Page):
    page.title = "Склад"
    page.bgcolor = "#0f0f17"

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        tabs=[
            ft.Tab(text="Надходження", content=incoming_view(page)),
            ft.Tab(text="Залишки", content=balances_view(page)),
            ft.Tab(text="Відвантаження", content=shipping_view(page)),
            ft.Tab(text="Аналітика", content=analytics_view(page)),
        ],
        expand=1,
    )

    return ft.View(
        "/warehouse",
        controls=[
            ft.Row([
                ft.Text("Склад", size=26, weight="bold", color="#10b981"),
            ], alignment=ft.MainAxisAlignment.START),
            ft.Divider(),
            tabs,
        ],
        scroll=ft.ScrollMode.AUTO,
    )
