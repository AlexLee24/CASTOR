import flet as ft
from constant import Design


class RightPanel(ft.Container):
    """
    右側即時結果面板。不接按鈕——由 AppState.recalculate() 算出來的結果
    透過 render() 灌進來，成功就畫指標卡片，失敗就顯示錯誤訊息（不會讓
    整個 GUI 崩掉）。
    """

    def __init__(self):
        super().__init__()
        self.expand = 12

        # 套用共用的玻璃卡樣式（見 constant.Design.GLASS_CARD）
        for key, value in Design.GLASS_CARD.items():
            setattr(self, key, value)

        card_side = ft.BorderSide(1, Design.BORDER_COLOR)
        self._card_border = ft.Border(top=card_side, right=card_side, bottom=card_side, left=card_side)

        self.hero_label = ft.Text("Primary Result", color=Design.TEXT_MUTED, size=14, weight=ft.FontWeight.BOLD)
        self.hero_value = ft.Text("--", color=Design.PRIMARY, size=56, weight=ft.FontWeight.BOLD)
        self.hero_desc = ft.Text("等待輸入…", color=Design.TEXT_MUTED, size=12)

        self.error_text = ft.Text("", color=Design.ERROR, size=12, selectable=True)
        self.error_box = ft.Container(
            content=self.error_text,
            bgcolor=Design.ERROR_BG,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            width=480,  # 長訊息用換行撐高度，不要用拉寬去容納
            visible=False,
        )

        self.warning_text = ft.Text("", color=Design.WARNING, size=12)
        self.warning_box = ft.Container(
            content=self.warning_text,
            bgcolor=Design.WARNING_BG,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            width=480,
            visible=False,
        )

        self.budget_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)
        self.diagnostics_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)
        self.limits_grid = ft.Row(wrap=True, spacing=Design.GAP_CARD, run_spacing=Design.GAP_CARD)

        self.content = ft.Column(
            controls=[
                ft.Column(
                    [self.hero_label, self.hero_value, self.hero_desc],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                # 用一層 Row 包住，讓這兩個小提示框照自己內容的寬度顯示，
                # 不要被外層 Column 的 STRETCH 拉成一條跟卡片一樣寬的扁長條。
                ft.Row([self.error_box], alignment=ft.MainAxisAlignment.START),
                ft.Row([self.warning_box], alignment=ft.MainAxisAlignment.START),
                self._section_title("Signal & Noise Budget"),
                self.budget_grid,
                self._section_title("Physical Diagnostics"),
                self.diagnostics_grid,
                self._section_title("Observation Limits"),
                self.limits_grid,
            ],
            spacing=Design.GAP_GROUP,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    # ==========================================
    # 共用小工具
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

    # ==========================================
    # 主要入口：AppState.recalculate() 的結果灌進來
    # ==========================================
    def render(self, response, error: str | None) -> None:
        if error is not None:
            self.error_text.value = error
            self.error_box.visible = True
            self.warning_box.visible = False
            self.hero_label.value = "Primary Result"
            self.hero_value.value = "--"
            self.hero_desc.value = "輸入不合法，請檢查左側欄位"
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
        if warn_lines:
            self.warning_text.value = "\n".join(warn_lines)
            self.warning_box.visible = True
        else:
            self.warning_box.visible = False

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
