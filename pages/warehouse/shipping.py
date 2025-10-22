import flet as ft

def shipping_view(page: ft.Page):
    return ft.Column(
        [
            ft.Text("🚚 Відвантаження — модуль завантажено", color="#10b981", size=18),
            ft.Divider(),
        ],
        expand=True,
    )
