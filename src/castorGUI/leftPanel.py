import json
from typing import Callable, Optional

import flet as ft
from constant import Design
from state import AppState


class LeftPanel(ft.Container):
    def __init__(self, state: AppState, on_change: Optional[Callable[[], None]] = None):
        super().__init__()
        self.expand = 10  # 1fr
        self.state = state
        # 任何欄位變動後呼叫（觸發右側 live preview 重新計算）
        self.on_change = on_change

        # dotted-path -> Control，preset 套用時用來同步更新畫面上的值
        self.field_refs: dict[str, ft.TextField] = {}

        self.current_tab_index = 0
        self.tab_names = ["Instrument", "Target", "Environment", "Options"]

        # 引入常數
        self.border_side = ft.BorderSide(Design.BORDER_WIDTH, Design.BORDER_COLOR)
        self.panel_border = ft.Border(
            top=self.border_side,
            right=self.border_side,
            bottom=self.border_side,
            left=self.border_side
        )

        # 每次切分頁都會重建 top bar（見 build_top_bar），所以狀態文字用字串記，
        # 實際 Text control 每次重建都會重新生成，self.status_text 永遠指向「當前畫面上那個」
        self._status_message = ""
        self.status_text = ft.Text(self._status_message, color=Design.TEXT_MUTED, size=11)

        # 分頁內容（依序對應 tab_names）
        self.views = self._build_views()

        self.inner_content = ft.Container(
            content=self.views[self.current_tab_index],
            border=self.panel_border,
            border_radius=Design.RADIUS_BASE,
            padding=Design.PADDING_PANEL,
            expand=True
        )

        self.border = self.panel_border
        self.border_radius = Design.RADIUS_BASE
        self.padding = Design.PADDING_PANEL
        self.bgcolor = Design.PANEL_BG

        self.content = ft.Column([
            self.build_top_bar(),
            # 頂部列與內部框的間距
            ft.Container(height=Design.PADDING_TAB_H),
            self.inner_content
        ])

    def _build_views(self) -> list[ft.Column]:
        """建立四個分頁的內容。LOAD 之後會重新呼叫一次，讓所有欄位重新綁定到
        （被存檔內容覆蓋過的）最新 state 值。"""
        return [
            self.build_instrument_tab(),
            self.build_target_tab(),
            self.build_environment_tab(),
            self.build_options_tab(),
        ]

    # ==========================================
    # 頂部 Tab Bar（分頁切換 + LOAD / SAVE）
    # ==========================================
    def build_top_bar(self):
        tabs = []
        for i, name in enumerate(self.tab_names):
            is_active = (i == self.current_tab_index)

            text_color = Design.PRIMARY if is_active else Design.TEXT_MUTED

            # 永遠保留邊框佔位（只改顏色，不改寬度），避免切換分頁時版面跳動
            top_color = Design.PRIMARY if is_active else "transparent"
            right_color = Design.PRIMARY if is_active else "transparent"
            left_color = Design.PRIMARY if is_active else "transparent"
            bottom_color = Design.PRIMARY if is_active else Design.BORDER_COLOR

            tab_border = ft.Border(
                top=ft.BorderSide(Design.BORDER_WIDTH, top_color),
                right=ft.BorderSide(Design.BORDER_WIDTH, right_color),
                bottom=ft.BorderSide(Design.BORDER_WIDTH, bottom_color),
                left=ft.BorderSide(Design.BORDER_WIDTH, left_color),
            )

            radius = Design.RADIUS_BASE if is_active else 0

            tab = ft.Container(
                content=ft.Text(
                    name,
                    color=text_color,
                    size=Design.TAB_FONT_SIZE,
                    weight=ft.FontWeight.NORMAL
                ),
                border=tab_border,
                border_radius=radius,
                padding=ft.Padding(left=Design.PADDING_TAB_H, right=Design.PADDING_TAB_H, top=Design.PADDING_TAB_V, bottom=Design.PADDING_TAB_V),
                on_click=self.create_tab_click_handler(i),
                ink=True,
            )
            tabs.append(tab)

        tabs_row = ft.Row(
            tabs,
            spacing=0,
            expand=True,               # 撐滿整行寬度，把 LOAD/SAVE 推到最右邊
            scroll=ft.ScrollMode.AUTO  # 視窗太窄時允許橫向滑動
        )

        action_buttons = ft.Row([
            ft.Container(
                content=ft.Text("LOAD", size=11, color=Design.TEXT_MUTED, weight=ft.FontWeight.NORMAL),
                width=Design.BTN_ACTION_WIDTH,
                height=Design.BTN_ACTION_HEIGHT,
                border=self.panel_border,
                border_radius=Design.RADIUS_BASE,
                alignment=ft.Alignment(0, 0),
                ink=True,
                tooltip="匯入 JSON",
                on_click=self._on_load_click,
            ),
            ft.Container(
                content=ft.Text("SAVE", size=11, color=Design.TEXT_MUTED, weight=ft.FontWeight.NORMAL),
                width=Design.BTN_ACTION_WIDTH,
                height=Design.BTN_ACTION_HEIGHT,
                border=self.panel_border,
                border_radius=Design.RADIUS_BASE,
                alignment=ft.Alignment(0, 0),
                ink=True,
                tooltip="匯出 JSON",
                on_click=self._on_save_click,
            ),
        ], spacing=Design.GAP_ACTION_BTN)

        # 每次重建 top bar 都重新生成這個 Text（見 __init__ 註解），
        # self.status_text 永遠指向目前畫面上那一個，方便 LOAD/SAVE handler 直接改字。
        self.status_text = ft.Text(self._status_message, color=Design.TEXT_MUTED, size=11)

        # 分頁列（expand 撐滿）+ LOAD/SAVE + 狀態文字维持單行，SPACE_BETWEEN
        # 推到兩端；窄視窗時分頁列改靠橫向捲動（scroll=AUTO）而不是換行——
        # Flet 的 wrap=True 目前跟 expand=True 不相容，換行版本曾經整個面板
        # 空白，穩定性優先於自動響應式排版。
        return ft.Row(
            [tabs_row, action_buttons, self.status_text],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def create_tab_click_handler(self, index):
        def on_click(e):
            self.current_tab_index = index
            self.inner_content.content = self.views[index]
            self.content.controls[0] = self.build_top_bar()
            self.update()
        return on_click

    # ==========================================
    # LOAD / SAVE JSON
    # ==========================================
    def _set_status(self, message: str) -> None:
        self._status_message = message
        self.status_text.value = message
        self._safe_update(self.status_text)

    # LOAD/SAVE 刻意不用 ft.FilePicker：Flet 0.86.5 在 web 模式下有已知的
    # 上游問題（掛上 page.overlay 後回報「Unknown control: FilePicker」，
    # pick_files()/save_file() 的 1 小時 timeout 還會卡住整個 session）：
    # https://github.com/flet-dev/flet/issues/6040
    # 改用「貼上/複製 JSON 文字」的對話框，只依賴 AlertDialog + TextField。

    def _close_dialog(self) -> None:
        try:
            page = self.page
        except RuntimeError:
            return
        if page is not None:
            page.pop_dialog()

    def _themed_dialog(self, title: str, body: list[ft.Control], actions: list[ft.Control]) -> ft.AlertDialog:
        """LOAD/SAVE 對話框共用的樣式殼。AlertDialog 預設是 Material 的白底黑字，
        套用跟其他面板一致的深色卡片樣式，避免跟整個 App 的深色主題脫節。"""
        return ft.AlertDialog(
            modal=True,
            # 一定要比背景亮一階（Surface 2），不然浮在最上層的對話框跟
            # 底下的頁面背景同色，看起來就會很扁平/抽象。
            bgcolor=Design.SURFACE_2,
            shape=ft.RoundedRectangleBorder(
                radius=Design.RADIUS_CARD,
                side=ft.BorderSide(1, Design.BORDER_COLOR),
            ),
            title=ft.Text(title, color=Design.PRIMARY, size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(body, tight=True, width=480, spacing=Design.GAP_FIELD),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _dialog_hint(self, text: str) -> ft.Text:
        return ft.Text(text, size=12, color=Design.TEXT_MUTED)

    def _dialog_error_box(self) -> ft.Container:
        return ft.Container(
            content=ft.Text("", color=Design.ERROR, size=12, selectable=True),
            bgcolor=Design.ERROR_BG,
            border_radius=Design.RADIUS_BASE,
            padding=Design.GAP_FIELD,
            visible=False,
        )

    def _dialog_button(self, label: str, on_click, primary: bool = False) -> ft.TextButton:
        return ft.TextButton(
            label,
            on_click=on_click,
            style=ft.ButtonStyle(color=Design.PRIMARY if primary else Design.TEXT_MUTED),
        )

    async def _on_save_click(self, e) -> None:
        payload = self.state.get_api_payload()
        content = json.dumps(payload, indent=2, ensure_ascii=False)

        text_field = ft.TextField(
            value=content,
            multiline=True,
            read_only=True,
            min_lines=12,
            max_lines=18,
            text_size=12,
            color=Design.TEXT_MAIN,
            bgcolor=Design.PANEL_BG,
            border_color=Design.BORDER_COLOR,
            focused_border_color=Design.PRIMARY,
            border_radius=Design.RADIUS_INPUT,
        )

        async def copy_to_clipboard(_):
            try:
                await self.page.clipboard.set(content)
                self._set_status("已複製到剪貼簿")
            except Exception as ex:  # noqa: BLE001
                # Clipboard 失敗也沒關係，上面的 TextField 本身就是可以手動全選複製的備援。
                self._set_status(f"自動複製失敗，請手動選取複製（{ex}）")

        dialog = self._themed_dialog(
            title="匯出 CASTOR 設定",
            body=[
                self._dialog_hint("複製下面內容存成 .json 檔（或按「複製」）："),
                text_field,
            ],
            actions=[
                self._dialog_button("複製", copy_to_clipboard, primary=True),
                self._dialog_button("關閉", lambda _: self._close_dialog()),
            ],
        )

        try:
            page = self.page
        except RuntimeError:
            return
        page.show_dialog(dialog)

    async def _on_load_click(self, e) -> None:
        paste_field = ft.TextField(
            label="貼上 JSON 內容",
            multiline=True,
            min_lines=12,
            max_lines=18,
            text_size=12,
            color=Design.TEXT_MAIN,
            bgcolor=Design.PANEL_BG,
            label_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            border_color=Design.BORDER_COLOR,
            focused_border_color=Design.PRIMARY,
            border_radius=Design.RADIUS_INPUT,
        )
        error_box = self._dialog_error_box()

        def show_error(message: str) -> None:
            error_box.content.value = message
            error_box.visible = True
            self._safe_update(error_box)

        async def do_import(_):
            raw = paste_field.value or ""
            try:
                data = json.loads(raw)
            except Exception as ex:  # noqa: BLE001
                show_error(f"不是合法的 JSON：{ex}")
                return

            try:
                self.state.load_from_dict(data)
            except Exception as ex:  # noqa: BLE001
                show_error(f"匯入失敗：{ex}")
                return

            self._close_dialog()

            # 存檔可能改到任何分頁的欄位，最簡單可靠的做法就是整個重建左側表單，
            # 而不是逐一同步每個 TextField/Dropdown 的顯示值。
            self.field_refs.clear()
            self.views = self._build_views()
            self.inner_content.content = self.views[self.current_tab_index]
            self.content.controls[0] = self.build_top_bar()
            self._status_message = "已匯入 JSON"
            self.status_text.value = self._status_message
            self._safe_update(self)
            self._notify_change()

        dialog = self._themed_dialog(
            title="匯入 CASTOR 設定",
            body=[
                self._dialog_hint("把 SAVE 匯出的 JSON 內容貼在下面："),
                paste_field,
                error_box,
            ],
            actions=[
                self._dialog_button("匯入", do_import, primary=True),
                self._dialog_button("取消", lambda _: self._close_dialog()),
            ],
        )

        try:
            page = self.page
        except RuntimeError:
            return
        page.show_dialog(dialog)

    # ==========================================
    # 共用欄位小工具
    # ==========================================
    def _section_title(self, text: str) -> ft.Text:
        return ft.Text(text, color=Design.PRIMARY, size=Design.SECTION_TITLE_SIZE, weight=ft.FontWeight.BOLD)

    def _divider(self) -> ft.Divider:
        return ft.Divider(color=Design.BORDER_COLOR, height=1)

    def _safe_update(self, control) -> None:
        """在 Control 還沒被加進 page 前呼叫 .update() 會丟 RuntimeError（例如
        __init__ 階段建構分頁時），這裡統一吃掉，只在真的已經上畫面時才更新。"""
        try:
            mounted = control.page is not None
        except RuntimeError:
            mounted = False
        if mounted:
            control.update()

    def _notify_change(self) -> None:
        """欄位真的變動之後呼叫，觸發外部（右側 live preview）重新計算。
        故意用 try/except 包起來：這裡的例外多半是計算引擎丟出來的錯誤，
        不該讓輸入事件本身連帶炸掉整個表單。"""
        if self.on_change is None:
            return
        try:
            self.on_change()
        except Exception as ex:  # noqa: BLE001
            print(f"[LeftPanel] on_change callback failed: {ex}")

    def _num_field(self, path: str, label: str, unit: str = "", integer: bool = False, width=None) -> ft.TextField:
        current = self.state.get(path)
        tf = ft.TextField(
            label=label,
            value=str(current),
            suffix=unit or None,
            keyboard_type=ft.KeyboardType.NUMBER,
            text_size=13,
            color=Design.TEXT_MAIN,
            label_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            border_color=Design.BORDER_COLOR,
            focused_border_color=Design.PRIMARY,
            border_radius=Design.RADIUS_INPUT,
            content_padding=ft.Padding(left=12, right=12, top=10, bottom=10),
            width=width,
            expand=(width is None),
            on_change=self._make_num_handler(path, integer=integer),
        )
        self.field_refs[path] = tf
        return tf

    def _text_field(self, path: str, label: str, width=None) -> ft.TextField:
        current = self.state.get(path)
        tf = ft.TextField(
            label=label,
            value=str(current),
            text_size=13,
            color=Design.TEXT_MAIN,
            label_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            border_color=Design.BORDER_COLOR,
            focused_border_color=Design.PRIMARY,
            border_radius=Design.RADIUS_INPUT,
            content_padding=ft.Padding(left=12, right=12, top=10, bottom=10),
            width=width,
            expand=(width is None),
            on_change=self._make_text_handler(path),
        )
        self.field_refs[path] = tf
        return tf

    def _make_text_handler(self, path: str):
        def handler(e):
            self.state.set(path, e.control.value)
            self._notify_change()
        return handler

    def _make_num_handler(self, path: str, integer: bool = False):
        def handler(e):
            raw = e.control.value
            try:
                value = int(raw) if integer else float(raw)
            except (TypeError, ValueError):
                return  # 使用者還在輸入中途（例如 "1." 或 "-"），先不動 state
            self.state.set(path, value)
            self._notify_change()
        return handler

    def _dropdown(self, path: str, options: list[tuple[str, str]], on_change_extra=None, width=None) -> ft.Dropdown:
        current = self.state.get(path)
        dd = ft.Dropdown(
            value=current,
            options=[ft.dropdown.Option(key=k, text=label) for k, label in options],
            color=Design.TEXT_MAIN,
            border_color=Design.BORDER_COLOR,
            border_radius=Design.RADIUS_INPUT,
            width=width,
            expand=(width is None),
            on_select=self._make_select_handler(path, on_change_extra),
        )
        return dd

    def _make_select_handler(self, path: str, extra=None):
        def handler(e):
            value = e.control.value
            self.state.set(path, value)
            if extra:
                extra(value)
            self._notify_change()
        return handler

    def _preset_dropdown(self, category: str, label: str) -> ft.Dropdown:
        keys = list(self.state.presets.get(category, {}).keys())
        return ft.Dropdown(
            label=label,
            label_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            hint_text="套用預設值…",
            options=[ft.dropdown.Option(key=k, text=k.replace("_", " ")) for k in keys],
            color=Design.TEXT_MAIN,
            border_color=Design.BORDER_COLOR,
            border_radius=Design.RADIUS_INPUT,
            expand=True,
            on_select=self._make_preset_handler(category),
        )

    def _make_preset_handler(self, category: str):
        def handler(e):
            key = e.control.value
            changed_paths = self.state.apply_preset(category, key)
            for path in changed_paths:
                field = self.field_refs.get(path)
                if field is None:
                    continue
                field.value = str(self.state.get(path))
                if field.page:
                    field.update()
            self._notify_change()
        return handler

    # ==========================================
    # Tab 1: Instrument
    # ==========================================
    def build_instrument_tab(self) -> ft.Column:
        return ft.Column(
            controls=[
                self._section_title("Telescope"),
                self._preset_dropdown("telescopes", "Telescope Preset"),
                self._num_field("instrument.telescope.primary_mirror_diameter", "Primary Mirror Diameter", "m"),
                self._num_field("instrument.telescope.secondary_mirror_diameter", "Secondary Mirror Diameter", "m"),
                self._num_field("instrument.telescope.focal_length", "Focal Length", "m"),
                self._num_field("instrument.telescope.optical_throughput", "Optical Throughput", "0-1"),
                self._divider(),
                self._section_title("Camera / Detector"),
                self._preset_dropdown("cameras", "Camera Preset"),
                self._num_field("instrument.camera.pixel_pitch", "Pixel Pitch", "μm"),
                self._num_field("instrument.camera.quantum_efficiency", "Quantum Efficiency", "0-1"),
                self._num_field("instrument.camera.dark_current_rate", "Dark Current Rate", "e-/s/pix"),
                self._num_field("instrument.camera.readout_noise", "Readout Noise", "e-/pix"),
                self._num_field("instrument.camera.full_well_capacity", "Full Well Capacity", "e-"),
                self._divider(),
                self._section_title("Filter"),
                self._preset_dropdown("filters", "Filter Preset"),
                self._num_field("instrument.optic_filter.central_wavelength", "Central Wavelength", "nm"),
                self._num_field("instrument.optic_filter.filter_bandwidth", "Filter Bandwidth", "nm"),
                self._num_field("instrument.optic_filter.filter_transmission", "Filter Transmission", "0-1"),
                self._divider(),
                self._section_title("System"),
                self._num_field("instrument.throughput_correction", "Throughput Correction", "0-1"),
            ],
            spacing=Design.GAP_FIELD,
            scroll=ft.ScrollMode.AUTO,
        )

    # ==========================================
    # Tab 2: Target
    # ==========================================
    def build_target_tab(self) -> ft.Column:
        self.brightness_dynamic = ft.Column(spacing=Design.GAP_FIELD)
        self.sed_dynamic = ft.Column(spacing=Design.GAP_FIELD)
        self._refresh_brightness_fields(self.state.get("target.brightness.type"))
        self._refresh_sed_fields(self.state.get("target.sed.type"))

        return ft.Column(
            controls=[
                self._section_title("Coordinates (J2000, decimal degrees)"),
                self._num_field("target.ra", "Right Ascension", "deg"),
                self._num_field("target.dec", "Declination", "deg"),
                self._divider(),
                self._section_title("Morphology"),
                self._dropdown("target.morphology.type", [
                    ("point", "Point Source (e.g., Star)"),
                    ("extended", "Extended Source (e.g., Galaxy)"),
                ]),
                self._divider(),
                self._section_title("Brightness"),
                self._dropdown(
                    "target.brightness.type",
                    [
                        ("vega_mag", "Vega Magnitude"),
                        ("ab_mag", "AB Magnitude"),
                        ("jansky_flux", "Jansky Flux (Jy)"),
                        ("wavelength_flux", "Wavelength Flux (erg/s/cm²/Å)"),
                    ],
                    on_change_extra=self._refresh_brightness_fields,
                ),
                self.brightness_dynamic,
                self._divider(),
                self._section_title("Spectral Energy Distribution (SED)"),
                self._dropdown(
                    "target.sed.type",
                    [
                        ("flat", "Flat Spectrum"),
                        ("Temp", "Blackbody (Temperature)"),
                    ],
                    on_change_extra=self._refresh_sed_fields,
                ),
                self.sed_dynamic,
            ],
            spacing=Design.GAP_FIELD,
            scroll=ft.ScrollMode.AUTO,
        )

    def _refresh_brightness_fields(self, brightness_type: str):
        fields_by_type = {
            "vega_mag": [
                self._num_field("target.brightness.target_mag", "Apparent Magnitude", "mag"),
                self._num_field("target.brightness.zero_point_flux", "Zero Point Flux", "erg/s/cm²/Å"),
            ],
            "ab_mag": [
                self._num_field("target.brightness.target_mag", "Apparent Magnitude (AB)", "mag"),
            ],
            "jansky_flux": [
                self._num_field("target.brightness.flux_value", "Flux Density", "Jy"),
            ],
            "wavelength_flux": [
                self._num_field("target.brightness.flux_value", "Flux Density", "erg/s/cm²/Å"),
            ],
        }
        self.brightness_dynamic.controls = fields_by_type.get(brightness_type, [])
        self._safe_update(self.brightness_dynamic)

    def _refresh_sed_fields(self, sed_type: str):
        if sed_type == "Temp":
            self.sed_dynamic.controls = [
                self._num_field("target.sed.temperature_k", "Blackbody Temperature", "K"),
            ]
        else:
            self.sed_dynamic.controls = []
        self._safe_update(self.sed_dynamic)

    # ==========================================
    # Tab 3: Environment
    # ==========================================
    def build_environment_tab(self) -> ft.Column:
        # mu_dark 永遠是必填的基礎值，不會因為開關而被停用——auto_calc_background
        # 只決定要不要在這個基礎值上疊加即時月光/幾何貢獻。
        self.mu_dark_field = self._num_field("environment.mu_dark", "Dark Sky Brightness (mu_dark, baseline)", "mag/arcsec²")

        auto_switch = ft.Switch(
            label="Layer real-time moon/geometry contribution on top of mu_dark",
            label_text_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            value=self.state.get("environment.auto_calc_background"),
            active_color=Design.PRIMARY,
            on_change=self._on_auto_calc_toggle,
        )

        return ft.Column(
            controls=[
                self._section_title("Spatial Spreading (FWHM, arcsec)"),
                ft.Row([
                    self._num_field("environment.seeing_fwhm", "Seeing"),
                    self._num_field("environment.diffraction_fwhm", "Diffraction"),
                ], spacing=Design.GAP_FIELD),
                ft.Row([
                    self._num_field("environment.optical_fwhm", "Optical"),
                    self._num_field("environment.tracking_fwhm", "Tracking"),
                ], spacing=Design.GAP_FIELD),
                self._divider(),
                self._section_title("Atmosphere & Background"),
                auto_switch,
                self.mu_dark_field,
                self._num_field("environment.extinction_coeff", "Extinction Coefficient", "mag/airmass"),
                self._divider(),
                self._section_title("Spatiotemporal Context (Airmass & Moon)"),
                self._text_field("environment.observing_time_utc", "Observation Time (UTC, ISO 8601)"),
                self._num_field("environment.location.latitude_deg", "Latitude", "deg"),
                self._num_field("environment.location.longitude_deg", "Longitude", "deg"),
                self._num_field("environment.location.elevation_m", "Elevation", "m"),
            ],
            spacing=Design.GAP_FIELD,
            scroll=ft.ScrollMode.AUTO,
        )

    def _on_auto_calc_toggle(self, e):
        # mu_dark 不受這個開關影響，維持可編輯——這裡只單純寫回 state。
        self.state.set("environment.auto_calc_background", e.control.value)
        self._notify_change()

    # ==========================================
    # Tab 4: Options
    # ==========================================
    def build_options_tab(self) -> ft.Column:
        self.options_dynamic = ft.Column(spacing=Design.GAP_FIELD)
        self._refresh_options_fields(self.state.get("options.type"))

        return ft.Column(
            controls=[
                self._section_title("Base Configuration"),
                self._num_field("options.aperture_factor", "Aperture Factor (k_ap)"),
                self._num_field("options.single_exp_time", "Single Exposure Time", "s"),
                self._divider(),
                self._section_title("Observation Strategy"),
                self._dropdown(
                    "options.type",
                    [
                        ("solve_snr", "Solve for SNR (given exposures)"),
                        ("solve_time", "Solve for Exposures (given target SNR)"),
                    ],
                    on_change_extra=self._refresh_options_fields,
                ),
                self.options_dynamic,
            ],
            spacing=Design.GAP_FIELD,
            scroll=ft.ScrollMode.AUTO,
        )

    def _refresh_options_fields(self, options_type: str):
        if options_type == "solve_time":
            self.options_dynamic.controls = [
                self._num_field("options.target_snr", "Target SNR"),
            ]
        else:
            self.options_dynamic.controls = [
                self._num_field("options.num_exposures", "Number of Exposures", integer=True),
            ]
        self._safe_update(self.options_dynamic)
