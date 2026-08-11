import flet as ft
from leftPanel import LeftPanel
from rightPanel import RightPanel
from state import AppState
from constant import Design


def main(page: ft.Page):
    page.title = "CASTOR GUI"
    page.padding = Design.GAP_MAIN
    page.theme_mode = ft.ThemeMode.DARK

    page.bgcolor = Design.BG_DARK

    state = AppState()
    right_panel = RightPanel()

    def recalculate_and_render() -> None:
        response, error = state.recalculate()
        right_panel.render(response, error)

    left_panel = LeftPanel(state, on_change=recalculate_and_render)

    main_layout = ft.Row([left_panel, right_panel], expand=True, spacing=Design.GAP_MAIN)
    page.add(main_layout)

    # Run one calculation up front so the right side isn't empty while waiting for the user's first move
    recalculate_and_render()

ft.run(main=main)
