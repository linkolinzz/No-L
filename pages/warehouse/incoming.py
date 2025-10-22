import flet as ft

def incoming_view(page: ft.Page):
    return ft.Column(
        [
            ft.Text("📦 Надходження — модуль завантажено", color="#10b981", size=18),
            ft.Divider(),
        ],
        expand=True,
    )
