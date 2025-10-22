import flet as ft

def analytics_view(page: ft.Page):
    return ft.Column(
        [
            ft.Text("📈 Аналітика — модуль завантажено", color="#10b981", size=18),
            ft.Divider(),
        ],
        expand=True,
    )
