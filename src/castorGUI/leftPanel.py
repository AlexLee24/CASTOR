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
        # Called after any field changes (triggers the right-side live preview recalculation)
        self.on_change = on_change

        # dotted-path -> Control, used to sync displayed values when a preset is applied
        self.field_refs: dict[str, ft.TextField] = {}

        self.current_tab_index = 0
        self.tab_names = ["Instrument", "Target", "Environment", "Options"]

        # Pull in shared constants
        self.border_side = ft.BorderSide(Design.BORDER_WIDTH, Design.BORDER_COLOR)
        self.panel_border = ft.Border(
            top=self.border_side,
            right=self.border_side,
            bottom=self.border_side,
            left=self.border_side
        )

        # Tab contents (in the same order as tab_names)
        self.views = self._build_views()

        self.inner_content = ft.Container(
            content=self.views[self.current_tab_index],
            border=self.panel_border,
            border_radius=Design.RADIUS_BASE,
            padding=Design.PADDING_PANEL,
            expand=True
        )

        # Apply the shared glass card style (see constant.Design.GLASS_CARD) — the exact
        # same dict RightPanel applies to itself. They're sibling "big surfaces" and need
        # to read as the same kind of thing; hand-copying the individual properties here
        # (as a previous version of this file did) let them silently drift apart — it set
        # bgcolor/border/border_radius/padding but missed "blur", so this card rendered
        # with crisp edges while RightPanel's had a soft frosted-glass edge, and the two
        # cards' rounded corners read as different even once both were the same 16px value.
        for key, value in Design.GLASS_CARD.items():
            setattr(self, key, value)

        self.content = ft.Column([
            self.build_top_bar(),
            # Spacing between the top bar and the inner frame
            ft.Container(height=Design.PADDING_TAB_H),
            self.inner_content
        ])

    def _build_views(self) -> list[ft.Column]:
        """Builds the content for all four tabs. Called again after LOAD, so every field
        rebinds to the latest state values (which may have been overwritten by a loaded save)."""
        return [
            self.build_instrument_tab(),
            self.build_target_tab(),
            self.build_environment_tab(),
            self.build_options_tab(),
        ]

    # ==========================================
    # Top Tab Bar (tab switching + LOAD / SAVE)
    # ==========================================
    def build_top_bar(self):
        tabs = []
        for i, name in enumerate(self.tab_names):
            is_active = (i == self.current_tab_index)

            text_color = Design.PRIMARY if is_active else Design.TEXT_MUTED

            # Always reserve the border space (only color changes, not width), to avoid
            # layout jumping when switching tabs.
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
            expand=True,               # Fills the row width, pushing LOAD/SAVE to the far right
            scroll=ft.ScrollMode.AUTO  # Allows horizontal scrolling when the window is too narrow
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
                tooltip="Import JSON",
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
                tooltip="Export JSON",
                on_click=self._on_save_click,
            ),
        ], spacing=Design.GAP_ACTION_BTN)

        # Tabs row (expand-filled) + LOAD/SAVE kept on a single line via SPACE_BETWEEN,
        # pushed to both ends. On narrow windows the tabs row scrolls horizontally
        # (scroll=AUTO) instead of wrapping — Flet's wrap=True currently doesn't play well
        # with expand=True, and the wrapping version once left the whole panel blank, so
        # stability wins over automatic responsive layout here.
        #
        # There's deliberately no top-level Single/Batch switch living up here alongside
        # the tabs/LOAD/SAVE — batch is not a peer "mode" of this row's content-navigation
        # and one-off actions, it's an extra toggle scoped to the Options tab (see
        # build_options_tab), right next to the fields it reveals. See docs/gui_architecture.md.
        return ft.Row(
            [tabs_row, action_buttons],
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
    # LOAD/SAVE deliberately avoid ft.FilePicker: Flet 0.86.5 has a known upstream issue in
    # web mode (attaching to page.overlay reports "Unknown control: FilePicker", and the
    # 1-hour timeout on pick_files()/save_file() can hang the whole session):
    # https://github.com/flet-dev/flet/issues/6040
    # Using a "paste/copy JSON text" dialog instead, relying only on AlertDialog + TextField.

    def _close_dialog(self) -> None:
        try:
            page = self.page
        except RuntimeError:
            return
        if page is not None:
            page.pop_dialog()

    def _themed_dialog(self, title: str, body: list[ft.Control], actions: list[ft.Control]) -> ft.AlertDialog:
        """Shared styled shell for the LOAD/SAVE dialogs. AlertDialog defaults to Material's
        white background/black text; this applies the same dark card style as the rest of the
        panels so it doesn't clash with the app's dark theme."""
        return ft.AlertDialog(
            modal=True,
            # Must be one step brighter than the background (Surface 2), otherwise a dialog
            # floating on top would match the page background behind it and look flat/washed out.
            bgcolor=Design.SURFACE_2,
            shape=ft.RoundedRectangleBorder(
                radius=Design.RADIUS_CARD,
                side=ft.BorderSide(Design.BORDER_WIDTH, Design.BORDER_COLOR),
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
            border_radius=Design.RADIUS_BASE,
        )

        async def copy_to_clipboard(_):
            try:
                await self.page.clipboard.set(content)
            except Exception:  # noqa: BLE001
                # Clipboard failure is fine — the TextField above can still be selected and
                # copied manually as a fallback.
                pass

        dialog = self._themed_dialog(
            title="Export CASTOR Settings",
            body=[
                self._dialog_hint("Copy the content below into a .json file (or click \"Copy\"):"),
                text_field,
            ],
            actions=[
                self._dialog_button("Copy", copy_to_clipboard, primary=True),
                self._dialog_button("Close", lambda _: self._close_dialog()),
            ],
        )

        try:
            page = self.page
        except RuntimeError:
            return
        page.show_dialog(dialog)

    async def _on_load_click(self, e) -> None:
        paste_field = ft.TextField(
            label="Paste JSON content",
            multiline=True,
            min_lines=12,
            max_lines=18,
            text_size=12,
            color=Design.TEXT_MAIN,
            bgcolor=Design.PANEL_BG,
            label_style=ft.TextStyle(color=Design.TEXT_MUTED, size=12),
            border_color=Design.BORDER_COLOR,
            focused_border_color=Design.PRIMARY,
            border_radius=Design.RADIUS_BASE,
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
                show_error(f"Not valid JSON: {ex}")
                return

            try:
                self.state.load_from_dict(data)
            except Exception as ex:  # noqa: BLE001
                show_error(f"Import failed: {ex}")
                return

            self._close_dialog()

            # A loaded save can touch fields on any tab, so the simplest and most reliable
            # approach is to rebuild the entire left-side form, rather than syncing each
            # TextField/Dropdown's displayed value one by one.
            self.field_refs.clear()
            self.views = self._build_views()
            self.inner_content.content = self.views[self.current_tab_index]
            self.content.controls[0] = self.build_top_bar()
            self._safe_update(self)
            self._notify_change()

        dialog = self._themed_dialog(
            title="Import CASTOR Settings",
            body=[
                self._dialog_hint("Paste the JSON exported by SAVE below:"),
                paste_field,
                error_box,
            ],
            actions=[
                self._dialog_button("Import", do_import, primary=True),
                self._dialog_button("Cancel", lambda _: self._close_dialog()),
            ],
        )

        try:
            page = self.page
        except RuntimeError:
            return
        page.show_dialog(dialog)

    # ==========================================
    # Shared field helpers
    # ==========================================
    def _section_title(self, text: str) -> ft.Text:
        return ft.Text(text, color=Design.PRIMARY, size=Design.SECTION_TITLE_SIZE, weight=ft.FontWeight.BOLD)

    def _divider(self) -> ft.Divider:
        return ft.Divider(color=Design.BORDER_COLOR, height=1)

    def _switch_row(self, value: bool, on_change, label: str, tooltip: str = "") -> ft.Row:
        """ft.Switch's own `label` renders at full Material size — next to this form's
        13px fields it reads oversized. Scaling the switch down and pairing it with a
        plain 12px ft.Text (same size as everything else's labels) keeps it in proportion."""
        return ft.Row(
            [
                ft.Switch(
                    value=value, active_color=Design.PRIMARY, on_change=on_change,
                    scale=0.65, tooltip=tooltip or None,
                ),
                ft.Text(label, color=Design.TEXT_MUTED, size=12),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _safe_update(self, control) -> None:
        """Calling .update() on a Control before it's been added to the page raises a
        RuntimeError (e.g. while building tabs during __init__). This swallows that case and
        only updates when the control is actually mounted."""
        try:
            mounted = control.page is not None
        except RuntimeError:
            mounted = False
        if mounted:
            control.update()

    def _notify_change(self) -> None:
        """Called once a field has actually changed, to trigger the external (right-side
        live preview) recalculation. Wrapped in try/except on purpose: exceptions here are
        mostly errors raised by the calculation engine, and an input event shouldn't be
        allowed to take down the whole form with it."""
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
            border_radius=Design.RADIUS_BASE,
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
            border_radius=Design.RADIUS_BASE,
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
                return  # User is still mid-typing (e.g. "1." or "-"), leave state untouched
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
            border_radius=Design.RADIUS_BASE,
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
            hint_text="Apply a preset…",
            options=[ft.dropdown.Option(key=k, text=k.replace("_", " ")) for k in keys],
            color=Design.TEXT_MAIN,
            border_color=Design.BORDER_COLOR,
            border_radius=Design.RADIUS_BASE,
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
        # Fixed, mode-independent characteristics of the observing site and atmosphere —
        # "when" you're observing (a single instant, or a swept time range) lives on the
        # Options tab instead, alongside the other per-run strategy knobs. See
        # docs/gui_architecture.md for why: keeping the batch on/off switch next to the
        # fields it reveals matters more here than matching the engine's own schema
        # grouping (environment.observing_time_utc there vs. this tab's shape here).
        self.mu_dark_field = self._num_field("environment.mu_dark", "Dark Sky Brightness (mu_dark, baseline)", "mag/arcsec²")

        auto_switch = self._switch_row(
            value=self.state.get("environment.auto_calc_background"),
            on_change=self._on_auto_calc_toggle,
            label="Auto sky background",
            tooltip="Layers the real-time moon/geometry contribution on top of the mu_dark baseline",
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
                self._section_title("Observatory Location"),
                self._num_field("environment.location.latitude_deg", "Latitude", "deg"),
                self._num_field("environment.location.longitude_deg", "Longitude", "deg"),
                self._num_field("environment.location.elevation_m", "Elevation", "m"),
            ],
            spacing=Design.GAP_FIELD,
            scroll=ft.ScrollMode.AUTO,
        )

    def _on_auto_calc_toggle(self, e):
        # mu_dark is unaffected by this switch and stays editable — this just writes the
        # toggle value back to state.
        self.state.set("environment.auto_calc_background", e.control.value)
        self._notify_change()

    # ==========================================
    # Tab 4: Options
    # ==========================================
    def build_options_tab(self) -> ft.Column:
        self.options_dynamic = ft.Column(spacing=Design.GAP_FIELD)
        self._refresh_options_fields(self.state.get("options.type"))

        self.time_dynamic = ft.Column(spacing=Design.GAP_FIELD)
        self._refresh_time_fields(self.state.batch_enabled)

        batch_switch = self._switch_row(
            value=self.state.batch_enabled,
            on_change=self._on_batch_toggle,
            label="Sweep time range",
            tooltip="Compute across a start/end/step time range instead of a single instant",
        )

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
                self._divider(),
                # "When" lives here rather than on the Environment tab: it's not a fixed
                # site/atmosphere characteristic, it's the other half of "what are you
                # asking" — same shape as the solve_snr/solve_time choice above. Keeping
                # the switch and the fields it reveals in the same tab also means turning
                # it on always has a visible, adjacent effect — see docs/gui_architecture.md.
                self._section_title("When"),
                batch_switch,
                self.time_dynamic,
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

    def _refresh_time_fields(self, batch_enabled: bool):
        if batch_enabled:
            self.time_dynamic.controls = [
                self._text_field("batch_time.start_time_utc", "Start Time (UTC, ISO 8601)"),
                self._text_field("batch_time.end_time_utc", "End Time (UTC, ISO 8601)"),
                self._num_field("batch_time.time_step_minutes", "Time Step", "min"),
            ]
        else:
            self.time_dynamic.controls = [
                self._text_field("environment.observing_time_utc", "Observation Time (UTC, ISO 8601)"),
            ]
        self._safe_update(self.time_dynamic)

    def _on_batch_toggle(self, e):
        self.state.batch_enabled = e.control.value
        self._refresh_time_fields(self.state.batch_enabled)
        self._notify_change()
