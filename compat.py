# compat.py
import flet as ft

def _patch_dropdown_option_value():
    """
    У старому коді всюди використовується Option.value.
    У поточному Flet її нема – є key та text.
    Додаємо синонім .value → (key if key is not None else text)
    """
    if not hasattr(ft.dropdown.Option, "value"):
        ft.dropdown.Option.value = property(
            lambda self: self.key if self.key is not None else self.text
        )

_patch_dropdown_option_value()
