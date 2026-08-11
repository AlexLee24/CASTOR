import flet as ft

class Design:
    # ==========================================
    # Color — brand
    # ==========================================
    PRIMARY = "#C5A059"
    PRIMARY_HOVER = "#d4b06a"

    # Surface hierarchy (dark-mode-design: background is darkest, each surface layer
    # gets progressively brighter; modals/dialogs floating on top must be one step
    # brighter than the background, otherwise they blend into it and look "flat")
    BG_DARK = "#0a0a12"      # Surface 0 — page background
    SURFACE_1 = "#14141E"    # Surface 1 — regular cards (PANEL_BG is its translucent version)
    SURFACE_2 = "#1c1c28"    # Surface 2 — Dialog / Modal
    PANEL_BG = "#9914141E"
    BORDER_COLOR = "#1AFFFFFF"

    # Text: off-white rather than pure white, easier on the eyes when staring at a dark
    # background for a long time (contrast 15.9:1, well above the AA 4.5:1 threshold,
    # without sacrificing readability)
    TEXT_MAIN = "#e5e7eb"
    TEXT_MUTED = "#9ca3af"

    # Semantic colors (color-system: status colors should be named, not scattered as
    # magic strings across files)
    ERROR = "#f87171"
    ERROR_BG = "#2a1414"
    WARNING = "#fbbf24"
    WARNING_BG = "#2a2114"
    SUCCESS = "#4ade80"
    SUCCESS_BG = "#122019"

    # ==========================================
    # Spacing — 4px baseline scale (spacing-system: always use a value on the scale,
    # never an arbitrary number)
    # 2xs=2 xs=4 sm=8 md=16 lg=24 xl=32 2xl=48 3xl=64
    # ==========================================
    GAP_MAIN = 32          # xl — between the two main panels / page outer margin
    BORDER_WIDTH = 2
    TAB_FONT_SIZE = 13
    RADIUS_BASE = 5
    RADIUS_INPUT = 6
    RADIUS_CARD = 16

    PADDING_PANEL = 24     # lg
    PADDING_TAB_H = 16     # md
    PADDING_TAB_V = 8      # sm
    PADDING_CARD = 24      # lg

    # Form field spacing: small gap within a related group of fields, large gap between
    # distinct sections
    GAP_FIELD = 8          # sm — fields within the same group
    GAP_GROUP = 24         # lg — between sections like Telescope / Camera / Filter
    GAP_CARD = 16          # md — grid spacing between metric cards (right-side metric card)

    # Section title size: keep at least 1.5x the field labels below it (12px),
    # otherwise color alone can't distinguish "this is a heading" (visual-hierarchy)
    SECTION_TITLE_SIZE = 14

    ICON_SIZE = 16
    BTN_ACTION_WIDTH = 40
    BTN_ACTION_HEIGHT = 30
    GAP_ACTION_BTN = 8     # sm

    # Flet 0.80+ Border syntax, replaces the old border.all()
    _card_side = ft.BorderSide(1, BORDER_COLOR)

    # Shared card style
    GLASS_CARD = {
        "bgcolor": PANEL_BG,
        "border": ft.Border(top=_card_side, right=_card_side, bottom=_card_side, left=_card_side),
        "border_radius": RADIUS_CARD,
        "padding": PADDING_CARD,
        "blur": ft.Blur(12, 12, ft.BlurTileMode.CLAMP),
    }
