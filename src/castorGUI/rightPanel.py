import flet as ft
from constant import Design
from chart import render_batch_chart, CHART_ASPECT_RATIO


class RightPanel(ft.Container):
    """
    Right-side live results panel. No buttons here — results computed by
    AppState.recalculate() are pushed in via render(); on success it draws
    metric cards, on failure it shows an error message (without crashing
    the whole GUI).

    The batch/time-series chart is not a separate view: when AppState.batch_enabled
    is on, app.py additionally calls render_batch(), which shows one more section
    ("Observing Window") after Observation Limits — same section-title style as
    everything else, not a competing layout. See docs/gui_architecture.md.
    """

    def __init__(self):
        super().__init__()
        self.expand = 12

        # Apply the shared glass card style (see constant.Design.GLASS_CARD)
        for key, value in Design.GLASS_CARD.items():
            setattr(self, key, value)

        card_side = ft.BorderSide(Design.BORDER_WIDTH, Design.BORDER_COLOR)
        self._card_border = ft.Border(top=card_side, right=card_side, bottom=card_side, left=card_side)

        self.hero_label = ft.Text("Primary Result", color=Design.TEXT_MUTED, size=14, weight=ft.FontWeight.BOLD)
        self.hero_value = ft.Text("--", color=Design.PRIMARY, size=56, weight=ft.FontWeight.BOLD)
        self.hero_desc = ft.Text("Waiting for input…", color=Design.TEXT_MUTED, size=12)

        self.error_text = ft.Text("", color=Design.ERROR, size=12, selectable=True)
        self.error_box = ft.Container(
            content=self.error_text,
            bgcolor=Design.ERROR_BG,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            visible=False,
        )

        self.warning_text = ft.Text("", color=Design.WARNING, size=12)
        self.warning_box = ft.Container(
            content=self.warning_text,
            bgcolor=Design.WARNING_BG,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            visible=False,
        )
        # Single-point and batch results land in the same warning_box (there's only one
        # on screen) but come from two independent recalculations that can each update at
        # different times — tracked separately and re-merged by _refresh_warning_box() so
        # one finishing doesn't clobber whatever the other already put there.
        self._single_warn_lines: list[str] = []
        self._batch_warn_lines: list[str] = []

        self.budget_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)
        self.diagnostics_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)
        self.limits_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)

        # Batch/time-series chart section — hidden until AppState.batch_enabled is on
        # (see show_batch_loading()/hide_batch_section()/render_batch(), driven by
        # app.py). Fixed aspect ratio, scaled to fit the card on resize rather than
        # regenerated — see chart.py's module docstring on why.
        self.chart_image = ft.RawImage(fit=ft.BoxFit.CONTAIN, expand=True)
        self.chart_placeholder = ft.Text("", color=Design.TEXT_MUTED, size=12)
        self.observing_window_section = ft.Column(
            controls=[
                self._section_title("Observing Window"),
                ft.Container(content=self.chart_image, aspect_ratio=CHART_ASPECT_RATIO),
                self.chart_placeholder,
            ],
            spacing=Design.GAP_GROUP,
            visible=False,
        )

        self.content = ft.Column(
            controls=[
                ft.Column(
                    [self.hero_label, self.hero_value, self.hero_desc],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                # Stretched to the panel's full width (the outer Column's STRETCH
                # alignment), same as the section titles and grids below — a fixed
                # narrow width here read as a stray leftover box once the content
                # became multi-line (single + batch warnings can both land in one box).
                self.error_box,
                self.warning_box,
                self._section_title("Signal & Noise Budget"),
                self.budget_grid,
                self._section_title("Physical Diagnostics"),
                self.diagnostics_grid,
                self._section_title("Observation Limits"),
                self.limits_grid,
                self.observing_window_section,
            ],
            spacing=Design.GAP_GROUP,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    # ==========================================
    # Shared helpers
    # ==========================================
    def _section_title(self, text: str) -> ft.Text:
        return ft.Text(text, color=Design.PRIMARY, size=Design.SECTION_TITLE_SIZE, weight=ft.FontWeight.BOLD)

    def _metric_card(self, label: str, value: str, unit: str = "") -> ft.Container:
        value_row = [ft.Text(value, color=Design.TEXT_MAIN, size=18, weight=ft.FontWeight.BOLD)]
        if unit:
            value_row.append(ft.Text(unit, color=Design.TEXT_MUTED, size=11))
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(label, color=Design.TEXT_MUTED, size=11),
                    ft.Row(value_row, spacing=4, vertical_alignment=ft.CrossAxisAlignment.END),
                ],
                spacing=4,
            ),
            border=self._card_border,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            width=160,
        )

    def _safe_update(self) -> None:
        try:
            mounted = self.page is not None
        except RuntimeError:
            mounted = False
        if mounted:
            self.update()

    def _refresh_warning_box(self) -> None:
        lines = self._single_warn_lines + self._batch_warn_lines
        if lines:
            self.warning_text.value = "\n".join(lines)
            self.warning_box.visible = True
        else:
            self.warning_box.visible = False

    # ==========================================
    # Main entry point: results from AppState.recalculate() flow in here. Always runs,
    # independent of batch_enabled — the hero + three grids are the app's primary view.
    # ==========================================
    def render(self, response, error: str | None) -> None:
        if error is not None:
            self.error_text.value = error
            self.error_box.visible = True
            self._single_warn_lines = []
            self._refresh_warning_box()
            self.hero_label.value = "Primary Result"
            self.hero_value.value = "--"
            self.hero_desc.value = "Invalid input, please check the fields on the left"
            self.budget_grid.controls = []
            self.diagnostics_grid.controls = []
            self.limits_grid.controls = []
            self._safe_update()
            return

        self.error_box.visible = False

        core = response.core
        budget = response.budget
        diag = response.diagnostics
        flags = response.flags

        if core.required_exposures is None:
            self.hero_label.value = "Signal-to-Noise Ratio (SNR)"
            self.hero_value.value = f"{core.total_snr:.2f}"
            self.hero_desc.value = "Calculated based on the given exposure time."
        else:
            self.hero_label.value = "Required Exposures"
            self.hero_value.value = f"{core.required_exposures} frames"
            self.hero_desc.value = f"Target SNR achieved: {core.total_snr:.2f}"

        warn_lines = list(flags.warnings)
        if flags.is_saturated:
            warn_lines.insert(0, "⚠️ Single exposure time exceeds the saturation limit (Full Well Capacity reached).")
        self._single_warn_lines = warn_lines
        self._refresh_warning_box()

        self.budget_grid.controls = [
            self._metric_card("Source Rate", f"{budget.source_count_rate:.2f}", "e-/s"),
            self._metric_card("Sky Background", f"{budget.sky_count_rate:.2f}", "e-/s/pix"),
            self._metric_card("Peak Pixel Rate", f"{budget.peak_pixel_rate:.2f}", "e-/s/pix"),
            self._metric_card("Single Exp. SNR", f"{core.single_snr:.2f}"),
        ]

        self.diagnostics_grid.controls = [
            self._metric_card("Total FWHM", f"{diag.total_fwhm:.2f}", "arcsec"),
            self._metric_card("Pixel Scale", f"{diag.pixel_scale:.3f}", '"/pix'),
            self._metric_card("Effective Area", f"{diag.effective_area:.3f}", "m²"),
            self._metric_card("System Throughput", f"{diag.total_throughput * 100:.1f}", "%"),
            self._metric_card("Enclosed Flux", f"{diag.enclosed_flux_fraction * 100:.1f}", "%"),
            self._metric_card("Aperture Pixels", f"{diag.num_pixels_aperture:.1f}", "px"),
        ]

        self.limits_grid.controls = [
            self._metric_card("Saturation Time Limit", f"{core.saturation_time_limit:.2f}", "s"),
            self._metric_card("Optimal Exposure Time", f"{core.optimal_exposure_time:.2f}", "s"),
        ]

        self._safe_update()

    # ==========================================
    # Observing Window section: results from AppState.recalculate_batch() flow in here,
    # only ever called while AppState.batch_enabled is on (see app.py's debounced
    # dispatch). async because pushing pixels into ft.RawImage (render_encoded) is
    # itself awaitable.
    # ==========================================
    def show_batch_loading(self) -> None:
        """Called immediately when the batch switch is turned on (before the debounced
        recalculation finishes) so the section's appearance itself is the feedback that
        the switch did something — instead of a silent ~0.4s gap with nothing visible."""
        self.observing_window_section.visible = True
        self.chart_image.visible = False
        self.chart_placeholder.value = "Calculating…"
        self.chart_placeholder.visible = True
        self._safe_update()

    def hide_batch_section(self) -> None:
        """Called when the batch switch is turned off — removes the section outright
        rather than leaving a stale chart around."""
        self.observing_window_section.visible = False
        self._batch_warn_lines = []
        self._refresh_warning_box()
        self._safe_update()

    async def render_batch(self, response, error: str | None, single_exp_time: float) -> None:
        self.observing_window_section.visible = True

        if error is not None:
            self.chart_placeholder.value = error
            self.chart_placeholder.visible = True
            self.chart_image.visible = False
            self._batch_warn_lines = []
            self._refresh_warning_box()
            self._safe_update()
            return

        # Same warning_box the single-point result uses (see _refresh_warning_box) — the
        # chart image itself carries no title/warning text of its own, see chart.py.
        warn_lines = list(response.flags.warnings)
        if response.flags.is_saturated:
            warn_lines.insert(0, "⚠️ At least one point in the time series exceeds the saturation limit — see the shaded window(s) below.")
        self._batch_warn_lines = warn_lines
        self._refresh_warning_box()

        self.chart_placeholder.visible = False
        self.chart_image.visible = True
        self._safe_update()

        # Nothing upstream of this point catches chart-rendering failures — without this,
        # a matplotlib exception would just be swallowed by Flet's background-task
        # handler (see app.py's debounced dispatch), leaving the section silently stuck
        # rather than telling the user anything broke.
        try:
            png_bytes = render_batch_chart(response, single_exp_time)
            await self.chart_image.render_encoded(png_bytes)
        except Exception as ex:  # noqa: BLE001 - showing an error beats a silently stuck panel
            self.chart_image.visible = False
            self.chart_placeholder.value = f"Chart rendering failed: {ex}"
            self.chart_placeholder.visible = True
            self._safe_update()
