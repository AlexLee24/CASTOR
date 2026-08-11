import asyncio

import flet as ft
from leftPanel import LeftPanel
from rightPanel import RightPanel
from state import AppState
from constant import Design

# Batch recalculation costs ~100-400ms (astropy ephemeris + matplotlib rendering),
# unlike single mode's near-instant recalculate() — debounced so adjusting the Options
# tab's start/end/step fields doesn't fire a recalculation on every keystroke.
BATCH_DEBOUNCE_SECONDS = 0.4


def main(page: ft.Page):
    page.title = "CASTOR GUI"
    page.padding = Design.GAP_MAIN
    page.theme_mode = ft.ThemeMode.DARK

    page.bgcolor = Design.BG_DARK

    state = AppState()
    right_panel = RightPanel()

    # Holds the in-flight debounce task (if any) so a new edit can cancel a stale one
    # instead of letting two batch recalculations race each other.
    pending_batch = {"future": None}

    def recalculate_and_render() -> None:
        # Single-point result is always computed and shown — batch is an addition on
        # top of it, not an alternate mode, so this half never gets gated behind
        # state.batch_enabled. See docs/gui_architecture.md.
        response, error = state.recalculate()
        right_panel.render(response, error)

        if pending_batch["future"] is not None:
            pending_batch["future"].cancel()
            pending_batch["future"] = None

        if not state.batch_enabled:
            right_panel.hide_batch_section()
            return

        # Reveal the section (with a loading placeholder) immediately, rather than
        # leaving a ~0.4s gap where nothing visible happened yet.
        right_panel.show_batch_loading()

        async def debounced_batch() -> None:
            await asyncio.sleep(BATCH_DEBOUNCE_SECONDS)
            response, error = state.recalculate_batch()
            await right_panel.render_batch(response, error, state.options["single_exp_time"])

        pending_batch["future"] = page.run_task(debounced_batch)

    left_panel = LeftPanel(state, on_change=recalculate_and_render)

    main_layout = ft.Row([left_panel, right_panel], expand=True, spacing=Design.GAP_MAIN)
    page.add(main_layout)

    # Run one calculation up front so the right side isn't empty while waiting for the user's first move
    recalculate_and_render()

# Guarded so other scripts (tests, a web-mode launcher, etc.) can import `main` without
# also triggering ft.run()'s default desktop window as a side effect of the import.
if __name__ == "__main__":
    ft.run(main=main)
