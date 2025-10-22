import flet as ft

def balances_view(page: ft.Page):
    return ft.Column(
        [
            ft.Text("📊 Залишки — модуль завантажено", color="#10b981", size=18),
            ft.Divider(),
        ],
        expand=True,
    )
