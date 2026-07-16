import flet as ft
import asyncio


class BotState:
    def __init__(self):
        self.is_running = False
        self.accounts = []
        self.logs = []


bot_state = BotState()


def add_log(msg: str, color="white"):
    bot_state.logs.append((msg, color))
    if len(bot_state.logs) > 50:
        bot_state.logs.pop(0)


def main(page: ft.Page):
    page.title = "Менеджер Бота (Auto-Play)"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 800
    page.window_height = 600
    page.padding = 20

    # UI Elements
    accounts_list = ft.ListView(expand=True, spacing=10)

    def refresh_accounts():
        accounts_list.controls.clear()
        for idx, acc in enumerate(bot_state.accounts):
            accounts_list.controls.append(
                ft.ListTile(
                    title=ft.Text(acc['login'], weight="bold"),
                    subtitle=ft.Text(f"Офлайн персонажі: {acc['heroes']}"),
                    trailing=ft.IconButton(
                        icon=ft.icons.DELETE,
                        on_click=lambda e, i=idx: remove_account(i)
                    )
                )
            )
        page.update()

    def remove_account(idx):
        if 0 <= idx < len(bot_state.accounts):
            removed = bot_state.accounts.pop(idx)
            add_log(f"Видалено акаунт: {removed['login']}", "orange")
            refresh_accounts()
            refresh_logs()

    def add_account(e):
        login = acc_name_input.value.strip()
        heroes = char_name_input.value.strip()
        if login and heroes:
            bot_state.accounts.append({'login': login, 'heroes': heroes})
            acc_name_input.value = ""
            char_name_input.value = ""
            add_log(f"Додано акаунт: {login}", "green")
            refresh_accounts()
            refresh_logs()

    acc_name_input = ft.TextField(label="Назва акаунту (або логін)", expand=1, border_color="blue")
    char_name_input = ft.TextField(label="Персонажі (через кому)", expand=2, border_color="blue")
    add_btn = ft.ElevatedButton("Додати", on_click=add_account, bgcolor="blue", color="white", height=50)

    add_row = ft.Row([acc_name_input, char_name_input, add_btn], spacing=10)

    log_view = ft.ListView(expand=True, spacing=5, auto_scroll=True)

    def refresh_logs():
        log_view.controls.clear()
        for msg, color in bot_state.logs:
            log_view.controls.append(ft.Text(msg, color=color))
        page.update()

    add_log("Система готова до запуску.", color="green")

    status_text = ft.Text("Статус: Зупинено", color="red", weight="bold", size=18)

    def toggle_bot(e):
        bot_state.is_running = not bot_state.is_running
        if bot_state.is_running:
            start_btn.text = "Зупинити Бота"
            start_btn.bgcolor = "red"
            status_text.value = "Статус: Працює (Очікування екрану...)"
            status_text.color = "green"
            add_log("[Система] Бот запущено.", "cyan")
        else:
            start_btn.text = "Старт Бота"
            start_btn.bgcolor = "green"
            status_text.value = "Статус: Зупинено"
            status_text.color = "red"
            add_log("[Система] Бота зупинено.", "orange")
        page.update()
        refresh_logs()

    start_btn = ft.ElevatedButton("Старт Бота", on_click=toggle_bot, bgcolor="green", color="white", height=60, width=200)

    # Background task to process bot logic
    async def bot_loop():
        while True:
            if bot_state.is_running:
                # Mock bot logic
                if not bot_state.accounts:
                    add_log("[Бот] Немає акаунтів для роботи. Очікування...", "yellow")
                    refresh_logs()
                    await asyncio.sleep(5)
                else:
                    for acc in bot_state.accounts:
                        if not bot_state.is_running:
                            break
                        add_log(f"[Бот] Вхід на акаунт: {acc['login']}...", "lightblue")
                        refresh_logs()
                        await asyncio.sleep(2)

                        add_log("[Бот] Розвиток кланових навичок...", "lightblue")
                        refresh_logs()
                        await asyncio.sleep(2)

                        heroes = [h.strip() for h in acc['heroes'].split(',')]
                        for hero in heroes:
                            if not bot_state.is_running:
                                break
                            add_log(f"[Бот] Налаштування {hero} в офлайн мод...", "lightgreen")
                            refresh_logs()
                            await asyncio.sleep(1)

                        add_log(f"[Бот] Завершено з акаунтом {acc['login']}.", "green")
                        refresh_logs()
                        await asyncio.sleep(1)
            else:
                await asyncio.sleep(1)

    page.run_task(bot_loop)

    # Initial render
    refresh_accounts()
    refresh_logs()

    # Layout
    page.add(
        ft.Text("Налаштування акаунтів", size=24, weight="bold"),
        add_row,
        ft.Container(
            content=accounts_list,
            height=200,
            bgcolor="#1e1e1e",
            border_radius=8,
            padding=10,
            border=ft.border.all(1, "grey")
        ),
        ft.Divider(height=20, color="transparent"),
        ft.Row([start_btn, status_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Divider(height=20, color="transparent"),
        ft.Text("Журнал дій (Логи)", size=24, weight="bold"),
        ft.Container(
            content=log_view,
            height=150,
            bgcolor="#1e1e1e",
            border_radius=8,
            padding=10,
            border=ft.border.all(1, "grey")
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
