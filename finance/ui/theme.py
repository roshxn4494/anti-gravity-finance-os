"""UI Theme, styling tokens, and custom CSS for Streamlit.
Minimalist monochrome / clean high-contrast black & white aesthetic.
"""
from __future__ import annotations

import streamlit as st
from .. import config
from ..classify import categories as cat_mod

# Dataviz tokens - Clean monochrome & slate scale
SERIES = [
    "#09090b",  # Zinc 950 (Primary Black)
    "#3f3f46",  # Zinc 700
    "#71717a",  # Zinc 500
    "#a1a1aa",  # Zinc 400
    "#27272a",  # Zinc 800
    "#52525b",  # Zinc 600
    "#18181b",  # Zinc 900
    "#78716c",  # Stone 500
]
GRAY = "#a1a1aa"
INK = "#09090b"
SECONDARY = "#71717a"
GRID = "#f4f4f5"

GLOBAL_CAT_ORDER = (
    list(config.CATEGORY_KEYWORDS.keys())
    + ["Salary", "Income", "Ashwin", "Credit Card", "Internal Transfer",
       "Other Income", "Other", config.DEFAULT_CATEGORY]
)

TAB_ICONS = {
    "upload": ":material/cloud_upload:",
    "overview": ":material/analytics:",
    "transactions": ":material/receipt_long:",
    "reconciliation": ":material/account_tree:",
    "chat": ":material/chat:",
    "feedback": ":material/feedback:",
    "rewards": ":material/loyalty:",
    "data_health": ":material/verified_user:",
}


def inject_custom_css():
    """Inject minimal clean high-contrast black & white typography and container CSS."""
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="color-scheme" content="light">
    <meta name="theme-color" content="#ffffff">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300..800;1,300..800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" />
    
    <style>
        /* 1. Global Reset & Theme Enforcement */
        :root {
            color-scheme: light !important;
            --background-color: #ffffff !important;
            --secondary-background-color: #f4f4f5 !important;
            --text-color: #09090b !important;
            --primary-color: #09090b !important;
        }

        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
            color: #09090b !important;
            background-color: #ffffff !important;
        }
        
        .stApp {
            background-color: #ffffff !important;
            color: #09090b !important;
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-weight: 700 !important;
            color: #09090b !important;
            letter-spacing: -0.02em !important;
        }

        p, span, label, div {
            color: #09090b;
        }

        /* 2. Metric Cards (Clean White with Crisp Border) */
        .metric-card {
            background: #ffffff !important;
            border: 1px solid #e4e4e7 !important;
            border-radius: 14px !important;
            padding: 18px 20px !important;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04) !important;
            transition: transform 0.2s ease, border-color 0.2s ease !important;
            margin-bottom: 12px;
        }
        .metric-card:hover {
            border-color: #09090b !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
        }
        .metric-card .icon-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            background: #f4f4f5 !important;
            color: #09090b !important;
            border: 1px solid #e4e4e7 !important;
        }
        .metric-card.spend .icon-badge { background: #f4f4f5 !important; color: #09090b !important; }
        .metric-card.income .icon-badge { background: #f4f4f5 !important; color: #09090b !important; }
        .metric-card.savings .icon-badge { background: #f4f4f5 !important; color: #09090b !important; }
        .metric-card.invest .icon-badge { background: #f4f4f5 !important; color: #09090b !important; }

        .metric-title {
            font-size: 11px !important;
            font-weight: 700 !important;
            color: #71717a !important;
            text-transform: uppercase !important;
            letter-spacing: 0.06em !important;
            margin-bottom: 6px;
        }
        .metric-value {
            font-size: 26px !important;
            font-weight: 800 !important;
            color: #09090b !important;
            line-height: 1.15;
            letter-spacing: -0.03em !important;
        }
        .metric-sub {
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #52525b !important;
            margin-top: 8px;
        }

        /* 3. Clean Monochrome Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            background: #f4f4f5 !important;
            padding: 5px !important;
            border-radius: 12px !important;
            border: 1px solid #e4e4e7 !important;
        }
        .stTabs [data-baseweb="tab"] {
            height: 40px !important;
            border-radius: 9px !important;
            padding: 0 16px !important;
            font-weight: 600 !important;
            font-size: 13.5px !important;
            color: #71717a !important;
            border: none !important;
            background: transparent !important;
            transition: all 0.2s ease !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #09090b !important;
        }
        .stTabs [aria-selected="true"] {
            background: #ffffff !important;
            color: #09090b !important;
            border: 1px solid #d4d4d8 !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06) !important;
            font-weight: 700 !important;
        }

        /* 4. Sidebar (Clean Monochrome) */
        [data-testid="stSidebar"] {
            background: #fafafa !important;
            border-right: 1px solid #e4e4e7 !important;
        }
        [data-testid="stSidebar"] * {
            color: #09090b;
        }

        /* 5. Inputs & Text Fields — 100% FIXED HIGH-CONTRAST FOR ALL DEVICES */
        input, textarea, select,
        div[data-baseweb="base-input"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stTextArea"] textarea {
            background-color: #ffffff !important;
            border: 1px solid #d4d4d8 !important;
            border-radius: 10px !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            caret-color: #000000 !important;
            font-size: 14.5px !important;
            font-weight: 500 !important;
        }
        div[data-baseweb="base-input"],
        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            border-radius: 10px !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }

        /* Input Placeholders */
        input::placeholder, textarea::placeholder {
            color: #71717a !important;
            -webkit-text-fill-color: #71717a !important;
            opacity: 1 !important;
        }

        /* Input Focus States */
        input:focus, textarea:focus, select:focus,
        div[data-baseweb="base-input"]:focus-within,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="textarea"]:focus-within,
        div[data-baseweb="select"] > div:focus-within {
            border-color: #09090b !important;
            box-shadow: 0 0 0 1px #09090b !important;
            background-color: #ffffff !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            caret-color: #000000 !important;
        }

        /* WebKit Autofill Overrides (Eliminates Dark Mode / Yellow Inversion) */
        input:-webkit-autofill,
        input:-webkit-autofill:hover, 
        input:-webkit-autofill:focus, 
        textarea:-webkit-autofill,
        textarea:-webkit-autofill:hover,
        textarea:-webkit-autofill:focus,
        select:-webkit-autofill,
        select:-webkit-autofill:hover,
        select:-webkit-autofill:focus {
            -webkit-text-fill-color: #000000 !important;
            -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
            box-shadow: 0 0 0 1000px #ffffff inset !important;
            caret-color: #000000 !important;
            color: #000000 !important;
            transition: background-color 5000s ease-in-out 0s !important;
        }

        /* 5b. Chat Input & Bottom Floating Bar */
        [data-testid="stChatInput"],
        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] textarea {
            background-color: #ffffff !important;
            border: 1px solid #d4d4d8 !important;
            border-radius: 12px !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            caret-color: #000000 !important;
            font-size: 15px !important;
        }
        [data-testid="stChatInput"] textarea:focus {
            border-color: #09090b !important;
            box-shadow: 0 0 0 1px #09090b !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        [data-testid="stChatInput"] button {
            color: #09090b !important;
        }
        [data-testid="stBottomBlockContainer"] {
            background-color: #ffffff !important;
        }

        /* Select Dropdown & Popover Menus */
        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background-color: #ffffff !important;
            border: 1px solid #e4e4e7 !important;
            border-radius: 10px !important;
            color: #000000 !important;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08) !important;
        }
        li[role="option"] {
            color: #09090b !important;
            font-size: 14px !important;
            background-color: #ffffff !important;
        }
        li[role="option"]:hover,
        li[aria-selected="true"] {
            background-color: #f4f4f5 !important;
            color: #000000 !important;
            font-weight: 600 !important;
        }
        div[data-baseweb="select"] span {
            color: #09090b !important;
        }

        /* 6. Minimal Monochrome Buttons */
        .stButton > button {
            border-radius: 10px !important;
            font-weight: 600 !important;
            border: 1px solid #d4d4d8 !important;
            background: #ffffff !important;
            color: #09090b !important;
            transition: all 0.15s ease !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
        }
        .stButton > button:hover {
            border-color: #09090b !important;
            background: #f4f4f5 !important;
            color: #000000 !important;
        }
        .stButton > button[kind="primary"] {
            background: #09090b !important;
            color: #ffffff !important;
            border: 1px solid #09090b !important;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: #27272a !important;
            border-color: #27272a !important;
            color: #ffffff !important;
        }

        /* 7. Clean DataFrames & Containers */
        [data-testid="stDataFrame"] {
            border-radius: 12px !important;
            overflow: hidden !important;
            border: 1px solid #e4e4e7 !important;
            background: #ffffff !important;
        }

        /* 8. Chat Messages */
        [data-testid="stChatMessage"] {
            background: #ffffff !important;
            border-radius: 14px !important;
            border: 1px solid #e4e4e7 !important;
            padding: 16px !important;
            margin-bottom: 12px !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
            color: #09090b !important;
        }
        [data-testid="stChatMessage"] * {
            color: #09090b !important;
        }

        /* 9. Metrics & Alerts */
        [data-testid="stMetricValue"] {
            color: #09090b !important;
            font-weight: 800 !important;
        }
        [data-testid="stMetricLabel"] {
            color: #71717a !important;
            font-weight: 600 !important;
        }
        [data-testid="stAlert"] * {
            color: #09090b !important;
        }
        [data-testid="stExpander"] {
            background: #ffffff !important;
            border: 1px solid #e4e4e7 !important;
            border-radius: 12px !important;
        }
        [data-testid="stExpander"] summary {
            color: #09090b !important;
            font-weight: 600 !important;
        }

        /* ==========================================================================
           Mobile-Specific Responsive Overrides (< 768px Viewports)
           ========================================================================== */
        @media screen and (max-width: 768px) {
            .main .block-container {
                padding: 12px 12px 60px 12px !important;
                max-width: 100% !important;
            }

            h1 {
                font-size: 20px !important;
                letter-spacing: -0.01em !important;
                margin-bottom: 8px !important;
            }
            h2 {
                font-size: 17px !important;
                margin-bottom: 6px !important;
            }
            h3 {
                font-size: 15px !important;
            }

            /* Touch-Optimized Tabs */
            .stTabs [data-baseweb="tab-list"] {
                display: flex !important;
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch !important;
                flex-wrap: nowrap !important;
                padding: 4px 6px !important;
                gap: 5px !important;
                border-radius: 10px !important;
                scrollbar-width: none !important;
            }
            .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
                display: none !important;
            }
            .stTabs [data-baseweb="tab"] {
                height: 38px !important;
                padding: 0 12px !important;
                font-size: 13px !important;
                white-space: nowrap !important;
                flex-shrink: 0 !important;
            }

            /* Metric Cards on Mobile */
            .metric-card {
                padding: 14px !important;
                border-radius: 12px !important;
                margin-bottom: 10px !important;
            }
            .metric-value {
                font-size: 20px !important;
            }
            .metric-title {
                font-size: 10.5px !important;
            }

            /* Touch Friendly & iOS Zoom Elimination (16px font-size prevents auto-zoom) */
            .stButton > button {
                min-height: 44px !important;
                font-size: 14.5px !important;
            }
            input,
            textarea,
            select,
            div[data-baseweb="select"] input,
            [data-testid="stChatInput"] textarea {
                min-height: 44px !important;
                font-size: 16px !important;
                background-color: #ffffff !important;
                color: #000000 !important;
                -webkit-text-fill-color: #000000 !important;
                caret-color: #000000 !important;
            }

            [data-testid="stDataFrame"] {
                width: 100% !important;
                font-size: 12px !important;
                border-radius: 10px !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)


def category_color(cat: str) -> str:
    if cat in (config.DEFAULT_CATEGORY, "Other"):
        return GRAY
    order = GLOBAL_CAT_ORDER
    idx = order.index(cat) if cat in order else len(order)
    return SERIES[idx % len(SERIES)]


def account_color(acct: str) -> str:
    try:
        return SERIES[config.ACCOUNT_ORDER.index(acct)]
    except ValueError:
        return GRAY


def display_categories() -> list[str]:
    specials = ["Salary", "Income", "Ashwin", "Credit Card", "Internal Transfer",
                "Other Income"]
    cats = cat_mod.all_categories() + specials
    seen, out = set(), []
    for c in cats:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def layout_plot(fig, height: int = 340):
    """Apply consistent clean minimal light styling to Plotly figures."""
    fig.update_layout(
        height=height,
        margin=dict(l=15, r=15, t=50, b=25),
        font=dict(family="'Plus Jakarta Sans', -apple-system, sans-serif",
                  color="#52525b", size=12),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        title_font=dict(color="#09090b", size=14, family="'Plus Jakarta Sans', sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0, font=dict(color="#27272a", size=11)),
    )
    fig.update_xaxes(gridcolor="#f4f4f5", zerolinecolor="#e4e4e7")
    fig.update_yaxes(gridcolor="#f4f4f5", zerolinecolor="#e4e4e7")
    return fig
