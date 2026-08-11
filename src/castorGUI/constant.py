import flet as ft

class Design:
    # ==========================================
    # Color — brand
    # ==========================================
    PRIMARY = "#C5A059"
    PRIMARY_HOVER = "#d4b06a"

    # Surface hierarchy（dark-mode-design：background 最暗，每一層 surface
    # 依序調亮，modal/dialog 這種浮在最上層的東西一定要比背景亮一階，
    # 不然會跟背景糊在一起、看起來很「抽象」）
    BG_DARK = "#0a0a12"      # Surface 0 — 頁面底色
    SURFACE_1 = "#14141E"    # Surface 1 — 一般卡片（PANEL_BG 是它的半透明版本）
    SURFACE_2 = "#1c1c28"    # Surface 2 — Dialog / Modal
    PANEL_BG = "#9914141E"
    BORDER_COLOR = "#1AFFFFFF"

    # 文字：用 off-white 不用純白，長時間盯著深色背景比較不刺眼
    # （contrast 15.9:1，遠高於 AA 4.5:1 門檻，不犧牲可讀性）
    TEXT_MAIN = "#e5e7eb"
    TEXT_MUTED = "#9ca3af"

    # 語意色（color-system：狀態色要有名字、不要散落在各檔案裡的 magic string）
    ERROR = "#f87171"
    ERROR_BG = "#2a1414"
    WARNING = "#fbbf24"
    WARNING_BG = "#2a2114"
    SUCCESS = "#4ade80"
    SUCCESS_BG = "#122019"

    # ==========================================
    # Spacing — 4px 基準刻度（spacing-system：一律用刻度上的值，不用隨意數字）
    # 2xs=2 xs=4 sm=8 md=16 lg=24 xl=32 2xl=48 3xl=64
    # ==========================================
    GAP_MAIN = 32          # xl，兩大面板之間 / 頁面外距
    BORDER_WIDTH = 2
    TAB_FONT_SIZE = 13
    RADIUS_BASE = 5
    RADIUS_INPUT = 6
    RADIUS_CARD = 16

    PADDING_PANEL = 24     # lg
    PADDING_TAB_H = 16     # md
    PADDING_TAB_V = 8      # sm
    PADDING_CARD = 24      # lg

    # 表單欄位間距：同組相關欄位用小間距，不同群組（distinct sections）用大間距
    GAP_FIELD = 8          # sm — 同一組內的欄位
    GAP_GROUP = 24         # lg — Telescope / Camera / Filter 這種區塊之間
    GAP_CARD = 16          # md — 指標卡片（右側 metric card）之間的網格間距

    # 標題字級：跟底下欄位標籤（12px）至少拉開到 1.5x 以上，
    # 不然只靠顏色分不出「這是標題」（visual-hierarchy）
    SECTION_TITLE_SIZE = 14

    ICON_SIZE = 16
    BTN_ACTION_WIDTH = 40
    BTN_ACTION_HEIGHT = 30
    GAP_ACTION_BTN = 8     # sm

    # Flet 0.80+ 的 Border 寫法，取代舊版的 border.all()
    _card_side = ft.BorderSide(1, BORDER_COLOR)

    # 共用卡片樣式
    GLASS_CARD = {
        "bgcolor": PANEL_BG,
        "border": ft.Border(top=_card_side, right=_card_side, bottom=_card_side, left=_card_side),
        "border_radius": RADIUS_CARD,
        "padding": PADDING_CARD,
        "blur": ft.Blur(12, 12, ft.BlurTileMode.CLAMP), 
    }