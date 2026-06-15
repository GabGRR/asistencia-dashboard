from __future__ import annotations

import html

import altair as alt
import pandas as pd
import streamlit as st

from core.attendance import (
    STATUS_AMBIGUOUS,
    STATUS_NOT_FOUND,
    STATUS_WITH_CHECK,
    STATUS_WITHOUT_CHECK,
    analyze_attendance,
)
from core.catalog import (
    CatalogFormatError,
    build_catalog_result,
    configured_catalog_url,
    load_catalog_from_url,
    load_docentes_catalog,
    load_paae_catalog,
)
from core.export import build_excel_report, dataframe_to_csv_bytes
from core.pdf_daily_parser import format_date_with_weekday, parse_pdf
from core.problem_reporting import build_problems_table
from core.query import build_person_suggestions, filter_results


st.set_page_config(
    page_title="Dashboard de asistencia diaria",
    page_icon="✓",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_VERSION = "1.9.0"


def inject_app_shell_css() -> None:
    st.markdown(
        """
        <style>
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        .stAppToolbar {
            display: none !important;
        }
        .block-container {
            padding-top: .7rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def cached_parse_pdf(pdf_bytes: bytes) -> dict[str, object]:
    return parse_pdf(pdf_bytes)


@st.cache_data(show_spinner=False)
def cached_load_paae(excel_bytes: bytes) -> pd.DataFrame:
    return load_paae_catalog(excel_bytes)


@st.cache_data(show_spinner=False)
def cached_load_docentes(excel_bytes: bytes) -> pd.DataFrame:
    return load_docentes_catalog(excel_bytes)


@st.cache_data(show_spinner=False, ttl=900)
def cached_remote_catalog(url: str) -> tuple[bytes | None, str | None, dict[str, object]]:
    return load_catalog_from_url(url)


def inject_dark_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #6b1738;
            --ipn-soft: #a56a7f;
            --ink: #f7f3eb;
            --muted: #aaa7a2;
            --panel: #101011;
            --panel-2: #151516;
            --line: rgba(247,243,235,.09);
            --stone: #c9c3b8;
            --stone-2: #b8b1a6;
            --black: #050506;
            --green: #83a98b;
            --amber: #c5a56b;
            --rose: #bd7d83;
            --blue: #829eb5;
        }
        html, body, [data-testid="stAppViewContainer"] { background: var(--black); }
        .stApp { background: var(--black); color: var(--ink); }
        .block-container { max-width: 1380px; padding-top: 1.25rem; padding-bottom: 2rem; }

            /* Sidebar oscuro IPN para tema Oscuro guinda */
            [data-testid="stSidebar"] {
                background:
                    radial-gradient(circle at 18% 8%, rgba(107,23,56,.35), transparent 30%),
                    radial-gradient(circle at 92% 90%, rgba(197,165,107,.13), transparent 34%),
                    linear-gradient(155deg, #111114 0%, #15161a 48%, #211018 100%) !important;
                border-right: 1px solid rgba(197,165,107,.28) !important;
                box-shadow:
                    inset -1px 0 rgba(255,255,255,.045),
                    18px 0 48px rgba(0,0,0,.36),
                    0 0 26px rgba(107,23,56,.14) !important;
            }

            [data-testid="stSidebar"] * {
                color: #f7f3eb !important;
            }

            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3,
            [data-testid="stSidebar"] h4 {
                color: #fff3df !important;
                text-shadow: 0 2px 6px rgba(0,0,0,.45);
            }

            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] span {
                color: #d8d0c4 !important;
            }

            /* Radio buttons de Apariencia */
            [data-testid="stSidebar"] [data-baseweb="radio"] > div {
                gap: .42rem;
            }

            [data-testid="stSidebar"] [data-baseweb="radio"] label {
                border: 1px solid rgba(197,165,107,.22) !important;
                border-radius: 12px !important;
                padding: .48rem .58rem !important;
                background:
                    linear-gradient(145deg, rgba(37,39,45,.92), rgba(17,18,22,.98)) !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.06),
                    inset -2px -2px rgba(0,0,0,.26),
                    0 7px 15px rgba(0,0,0,.24) !important;
            }

            [data-testid="stSidebar"] [data-baseweb="radio"] label:hover {
                border-color: rgba(197,165,107,.48) !important;
                background:
                    linear-gradient(145deg, rgba(107,23,56,.50), rgba(24,26,32,.98)) !important;
            }

            /* Estado del catálogo */
            [data-testid="stSidebar"] .catalog-strip {
                display: grid;
                gap: .48rem;
            }

            [data-testid="stSidebar"] .catalog-strip div {
                padding: .62rem .72rem !important;
                border-radius: 12px !important;
                border: 1px solid rgba(197,165,107,.24) !important;
                background:
                    linear-gradient(145deg, rgba(38,40,47,.90), rgba(15,16,20,.98)) !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.07),
                    inset -2px -2px rgba(0,0,0,.28),
                    0 9px 18px rgba(0,0,0,.28) !important;
            }

            [data-testid="stSidebar"] .catalog-strip span {
                color: #d8b96f !important;
                float: right;
                font-weight: 760 !important;
            }

            /* Expander Reemplazar catálogos en sidebar */
            [data-testid="stSidebar"] div[data-testid="stExpander"] > details {
                background:
                    linear-gradient(145deg, rgba(107,23,56,.54), rgba(22,24,30,.98)) !important;
                border: 1px solid rgba(197,165,107,.28) !important;
                border-radius: 13px !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.07),
                    0 10px 22px rgba(0,0,0,.34),
                    0 0 18px rgba(107,23,56,.18) !important;
            }

            [data-testid="stSidebar"] div[data-testid="stExpander"] > details summary {
                color: #fff1d4 !important;
                font-weight: 720 !important;
            }

            /* Uploader dentro del sidebar */
            [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
                background:
                    linear-gradient(145deg, #2c2f37, #111318) !important;
                border: 1px solid rgba(197,165,107,.26) !important;
                border-radius: 12px !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.07),
                    0 8px 16px rgba(0,0,0,.30) !important;
            }

            /* Botones del sidebar */
            [data-testid="stSidebar"] button {
                color: #fff5df !important;
                background:
                    linear-gradient(180deg, #6b1738, #461025) !important;
                border: 1px solid rgba(197,165,107,.35) !important;
                border-radius: 11px !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.11),
                    0 8px 16px rgba(0,0,0,.30),
                    0 0 12px rgba(107,23,56,.22) !important;
            }

            [data-testid="stSidebar"] button:hover {
                background:
                    linear-gradient(180deg, #82224a, #57132f) !important;
                border-color: rgba(197,165,107,.55) !important;
                box-shadow:
                    inset 1px 1px rgba(255,255,255,.14),
                    0 9px 18px rgba(0,0,0,.34),
                    0 0 16px rgba(197,165,107,.18) !important;
            }

        
        [data-testid="stHeader"] { background: transparent; }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3 { letter-spacing: -.025em; }
        .hero {
            position: relative; overflow: hidden; border: 1px solid var(--line);
            border-radius: 22px; padding: 1.25rem 1.4rem; margin-bottom: .85rem;
            background: linear-gradient(132deg, #0c0c0d 0%, #09090a 68%, #160a10 100%);
            box-shadow: 0 22px 70px rgba(0,0,0,.48), 0 14px 55px rgba(107,23,56,.13);
        }
        .hero.compact { min-height: 154px; padding: .95rem 1rem; margin: 0; }
        .hero.compact .hero-title { font-size: 1.42rem; }
        .hero.compact .hero-subtitle { font-size: .78rem; line-height: 1.35; }
        .hero.compact .hero-date { margin-top: .5rem; }
        .hero.compact .badge-row { margin-top: .58rem; gap: .32rem; }
        .hero.compact .badge { padding: .24rem .45rem; font-size: .64rem; }
        .hero:after {
            content: ""; position: absolute; width: 190px; height: 190px;
            border-radius: 50%; right: -70px; top: -105px;
            background: radial-gradient(circle, rgba(107,23,56,.62), rgba(107,23,56,0) 68%);
        }
        .hero-kicker { color: #c895a8; font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
        .hero-title { font-size: 1.75rem; font-weight: 720; margin: .2rem 0 .18rem; }
        .hero-subtitle { color: var(--muted); font-size: .92rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #ded9d5; font-size: .86rem; font-weight: 600; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .32rem .58rem;
            border-radius: 999px; background: rgba(247,243,235,.055); border: 1px solid var(--line);
            color: #d7d4d1; font-size: .72rem; font-weight: 650;
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px rgba(131,169,139,.10); }
        .badge.warn .badge-dot { background: var(--amber); }
        .badge.ipn { color: #e5bdcb; border-color: rgba(165,106,127,.35); background: rgba(107,23,56,.18); }
        .badge.ipn .badge-dot { background: #a56a7f; }
        .section-label { color: #d5d1ce; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin: .15rem 0 .65rem; }
        .catalog-strip {
            display: flex; align-items: center; justify-content: space-between; gap: 1rem;
            color: #1a1918; font-size: .78rem; font-weight: 680;
        }
        .catalog-strip span { color: #514d48; font-weight: 570; }
        .metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .65rem; margin: .2rem 0 .9rem; }
        .metric-card {
            min-height: 112px; border: 1px solid var(--line); border-radius: 17px;
            padding: .9rem 1rem; position: relative; overflow: hidden;
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 12%, var(--panel)), var(--panel) 72%);
            box-shadow: 0 12px 30px rgba(0,0,0,.32), 0 10px 28px color-mix(in srgb, var(--accent) 8%, transparent);
        }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--accent, #6b1738); opacity: .9; }
        .metric-label { color: var(--muted); font-size: .75rem; font-weight: 650; }
        .metric-value { font-size: 1.75rem; font-weight: 720; margin-top: .42rem; line-height: 1; }
        .metric-note { color: #8e8d93; font-size: .68rem; margin-top: .5rem; }
        .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .65rem; margin-bottom: .9rem; }
        .group-card {
            border: 1px solid var(--line); border-radius: 16px; padding: .82rem .9rem;
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 13%, var(--panel-2)), var(--panel-2) 74%);
            box-shadow: 0 10px 25px rgba(0,0,0,.28), 0 8px 22px color-mix(in srgb, var(--accent) 7%, transparent);
        }
        .group-title { font-size: .76rem; color: #d6d2cf; font-weight: 680; min-height: 2.1em; }
        .group-main { display: flex; justify-content: space-between; align-items: baseline; margin-top: .35rem; }
        .group-main strong { font-size: 1.28rem; }
        .group-main span { color: var(--muted); font-size: .72rem; }
        .group-bar { height: 5px; background: rgba(255,255,255,.06); border-radius: 99px; overflow: hidden; margin: .55rem 0 .45rem; }
        .group-bar span { display: block; height: 100%; border-radius: 99px; background: var(--accent, #829eb5); }
        .group-foot { display: flex; justify-content: space-between; color: #929096; font-size: .66rem; }
        .empty-state { border: 1px dashed rgba(255,255,255,.12); border-radius: 18px; text-align: center; padding: 2.2rem 1rem; color: var(--muted); background: rgba(255,255,255,.018); }
        .empty-state strong { display: block; color: #d9d5d2; font-size: 1rem; margin-bottom: .3rem; }
        [data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: .7rem .8rem; }
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 13px; background: #111113; border-color: rgba(247,243,235,.10); padding: .55rem; }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        button[kind="secondary"], .stDownloadButton button { border-radius: 11px !important; border-color: rgba(255,255,255,.10) !important; }
        [data-baseweb="tab-list"] { gap: .3rem; background: #0b0b0c; border: 1px solid var(--line); padding: .28rem; border-radius: 13px; }
        [data-baseweb="tab"] { height: 38px; border-radius: 9px; padding: 0 .82rem; }
        [aria-selected="true"][data-baseweb="tab"] { background: #1a1518; box-shadow: inset 0 0 0 1px rgba(165,106,127,.18); }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; box-shadow: 0 16px 38px rgba(0,0,0,.28); }
        details { border: 1px solid var(--line) !important; border-radius: 13px !important; background: var(--panel) !important; }
        div[data-testid="stExpander"] > details {
            background: linear-gradient(120deg, var(--stone), var(--stone-2)) !important;
            border: 1px solid rgba(0,0,0,.13) !important; color: #171615 !important;
            box-shadow: 0 10px 26px rgba(0,0,0,.22); margin-bottom: .8rem;
        }
        div[data-testid="stExpander"] > details p,
        div[data-testid="stExpander"] > details label,
        div[data-testid="stExpander"] > details span,
        div[data-testid="stExpander"] > details summary { color: #171615 !important; }
        div[data-testid="stExpander"] [data-testid="stFileUploaderDropzone"] {
            background: rgba(247,243,235,.36); border-color: rgba(0,0,0,.14);
        }
        div[data-testid="stExpander"] button {
            color: #171615 !important; background: rgba(247,243,235,.46) !important;
            border-color: rgba(0,0,0,.14) !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(247,243,235,.10) !important; border-radius: 18px !important;
            background: linear-gradient(145deg, #131314, #0d0d0e);
            box-shadow: 0 18px 42px rgba(0,0,0,.34), 0 10px 34px rgba(107,23,56,.055);
        }
        [data-testid="stVerticalBlockBorderWrapper"] h4 { color: #e7dfd4; }
        .panel-kicker {
            display: inline-block; border-radius: 999px; padding: .27rem .55rem; margin-bottom: .25rem;
            font-size: .66rem; font-weight: 720; letter-spacing: .07em; text-transform: uppercase;
        }
        .panel-kicker.sage { color: #c4d7cd; background: rgba(118,154,144,.16); border: 1px solid rgba(118,154,144,.28); }
        .panel-kicker.clay { color: #dfc2b6; background: rgba(183,117,97,.15); border: 1px solid rgba(183,117,97,.28); }
        .panel-kicker.mauve { color: #ddc5d1; background: rgba(165,106,127,.16); border: 1px solid rgba(165,106,127,.30); }
        .query-count {
            color: #bdb7b1; font-size: .76rem; margin: -.15rem 0 .55rem;
        }
        .top-control-label {
            color: #aaa7a2; font-size: .68rem; font-weight: 720; letter-spacing: .07em;
            text-transform: uppercase; margin-bottom: .35rem;
        }
        .stAlert { border-radius: 13px; background: #1c1d21; border: 1px solid var(--line); color: #d8d5d2; }
        @media (max-width: 1000px) {
            .metric-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .group-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
        }
        @media (max-width: 650px) {
            .block-container { padding-left: .8rem; padding-right: .8rem; }
            .metric-grid, .group-grid { grid-template-columns: 1fr; }
            .hero-title { font-size: 1.4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_product_ui_theme_css_legacy() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #74445a;
            --ipn-soft: #a8758a;
            --ink: #252724;
            --muted: #747872;
            --panel: #fffefa;
            --panel-2: #f7f7f2;
            --line: #dedfd8;
            --stone: #f2f0e9;
            --stone-2: #e9e7df;
            --black: #f3f3ee;
            --green: #79b99d;
            --amber: #d6b55e;
            --rose: #d68383;
            --blue: #78a9bd;
            --mint: #9ee8ce;
            --mint-strong: #74cfaf;
            --shadow: 0 18px 38px rgba(49,55,50,.13), 0 5px 12px rgba(49,55,50,.08);
        }
        html, body, [data-testid="stAppViewContainer"] { background: #f3f3ee; }
        .stApp { background: linear-gradient(145deg, #f6f5f0 0%, #efefe9 100%); color: var(--ink); }
        .block-container { max-width: 1380px; padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stSidebar"] { background: #ebeae3; border-right: 1px solid #d7d6cf; }
        [data-testid="stSidebar"] * { color: #30322f; }
        [data-testid="stHeader"] { background: rgba(243,243,238,.86); backdrop-filter: blur(14px); }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3, h4 { color: #252724; letter-spacing: -.025em; }
        p, label, [data-testid="stCaptionContainer"] { color: #686c66; }
        .hero {
            position: relative; overflow: hidden; border: 1px solid rgba(121,185,157,.42);
            border-radius: 24px; padding: 1.25rem 1.4rem; margin-bottom: .85rem;
            background: linear-gradient(138deg, #fffefa 0%, #f8faf5 64%, #e8f8f0 100%);
            box-shadow: var(--shadow);
        }
        .hero.compact { min-height: 154px; padding: .95rem 1rem; margin: 0; }
        .hero.compact .hero-title { font-size: 1.42rem; }
        .hero.compact .hero-subtitle { font-size: .78rem; line-height: 1.35; }
        .hero.compact .hero-date { margin-top: .5rem; }
        .hero.compact .badge-row { margin-top: .58rem; gap: .32rem; }
        .hero.compact .badge { padding: .24rem .45rem; font-size: .64rem; }
        .hero:after {
            content: ""; position: absolute; width: 190px; height: 190px; border-radius: 50%;
            right: -70px; top: -105px; background: radial-gradient(circle, rgba(158,232,206,.72), rgba(158,232,206,0) 68%);
        }
        .hero-kicker { color: #548a75; font-size: .72rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
        .hero-title { color: #252724; font-size: 1.75rem; font-weight: 740; margin: .2rem 0 .18rem; }
        .hero-subtitle { color: var(--muted); font-size: .92rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #40443f; font-size: .86rem; font-weight: 650; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .32rem .58rem;
            border-radius: 999px; background: #f1f8f4; border: 1px solid #cfe5da;
            color: #395f50; font-size: .72rem; font-weight: 680; box-shadow: 0 2px 5px rgba(54,89,74,.05);
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px rgba(121,185,157,.14); }
        .badge.warn { color: #775f25; background: #fff7dd; border-color: #ead79b; }
        .badge.warn .badge-dot { background: var(--amber); }
        .badge.ipn { color: #70465a; border-color: #dec3cf; background: #f8edf2; }
        .badge.ipn .badge-dot { background: #a8758a; }
        .section-label, .top-control-label { color: #656a64; font-size: .72rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
        .section-label { margin: .15rem 0 .65rem; }
        .top-control-label { margin-bottom: .35rem; }
        .catalog-strip { display: grid; gap: .45rem; color: #30322f; font-size: .78rem; font-weight: 700; }
        .catalog-strip div { padding: .55rem .65rem; border-radius: 12px; background: rgba(255,255,255,.55); border: 1px solid #d9d8d1; }
        .catalog-strip span { color: #6e726c; font-weight: 580; float: right; }
        .metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .7rem; margin: .2rem 0 .9rem; }
        .metric-card {
            min-height: 112px; border: 1px solid color-mix(in srgb, var(--accent) 26%, #dedfd8); border-radius: 19px;
            padding: .9rem 1rem; position: relative; overflow: hidden;
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 8%, #fffefa), #fffefa 76%);
            box-shadow: 0 18px 34px rgba(49,55,50,.12), 0 12px 28px color-mix(in srgb, var(--accent) 24%, transparent);
        }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 14px; right: 14px; height: 4px; border-radius: 0 0 99px 99px; background: var(--accent); opacity: .72; }
        .metric-label { color: #646963; font-size: .75rem; font-weight: 680; }
        .metric-value { color: #242724; font-size: 1.75rem; font-weight: 740; margin-top: .42rem; line-height: 1; }
        .metric-note { color: #898d87; font-size: .68rem; margin-top: .5rem; }
        .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .7rem; margin-bottom: .9rem; }
        .group-card {
            border: 1px solid color-mix(in srgb, var(--accent) 24%, #dedfd8); border-radius: 18px; padding: .82rem .9rem;
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 9%, #fffefa), #fafaf6 78%);
            box-shadow: 0 15px 28px rgba(49,55,50,.11), 0 10px 24px color-mix(in srgb, var(--accent) 20%, transparent);
        }
        .group-title { font-size: .76rem; color: #464a45; font-weight: 700; min-height: 2.1em; }
        .group-main { display: flex; justify-content: space-between; align-items: baseline; margin-top: .35rem; }
        .group-main strong { color: #242724; font-size: 1.28rem; }
        .group-main span, .group-foot { color: #777b75; font-size: .7rem; }
        .group-bar { height: 6px; background: #e3e5df; border-radius: 99px; overflow: hidden; margin: .55rem 0 .45rem; }
        .group-bar span { display: block; height: 100%; border-radius: 99px; background: var(--accent); }
        .group-foot { display: flex; justify-content: space-between; }
        .empty-state { border: 1px dashed #cfd3cc; border-radius: 20px; text-align: center; padding: 2.2rem 1rem; color: #777b75; background: rgba(255,255,255,.48); }
        .empty-state strong { display: block; color: #333632; font-size: 1rem; margin-bottom: .3rem; }
        [data-testid="stMetric"] { background: #fffefa; border: 1px solid #dedfd8; border-radius: 16px; padding: .7rem .8rem; box-shadow: 0 8px 18px rgba(49,55,50,.06); }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #272a26; }
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 18px; background: #fffefa; border: 1px solid #d8dcd5; padding: .55rem; box-shadow: 0 8px 20px rgba(49,55,50,.07); }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        button, [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input {
            border-radius: 999px !important;
        }
        button svg, summary svg, [data-baseweb="select"] svg,
        [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg {
            color: #303630 !important; fill: #303630 !important; stroke: #303630 !important;
            opacity: 1 !important;
        }
        button [data-testid="stIconMaterial"], summary [data-testid="stIconMaterial"],
        [data-baseweb="select"] [data-testid="stIconMaterial"] {
            color: #303630 !important; opacity: 1 !important;
        }
        button[kind="secondary"], .stDownloadButton button {
            color: #254f40 !important; background: #dff5ec !important; border: 1px solid #b9dfd0 !important;
            box-shadow: 0 5px 12px rgba(65,119,97,.10);
        }
        button[kind="secondary"]:hover, .stDownloadButton button:hover { background: #c8eddf !important; border-color: #83c8ad !important; }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input {
            color: #2b2e2a !important; background: #fffefa !important; border-color: #d5d8d1 !important;
            box-shadow: inset 0 0 0 1px rgba(121,185,157,.10), 0 8px 18px rgba(72,126,104,.10);
        }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
            color: #2b2e2a !important; background: #fffefa !important;
            border: 1px solid #d5d8d1 !important; border-radius: 16px !important;
            box-shadow: 0 20px 44px rgba(49,55,50,.18), 0 9px 26px rgba(116,207,175,.16) !important;
        }
        [role="option"] { color: #30332f !important; background: #fffefa !important; }
        [role="option"]:hover, [role="option"][aria-selected="true"] { background: #dcf4ea !important; color: #244c3d !important; }
        [data-baseweb="tab-list"] { gap: .28rem; background: #e4e5df; border: 1px solid #d3d5ce; padding: .3rem; border-radius: 999px; box-shadow: inset 0 2px 5px rgba(49,55,50,.06); }
        [data-baseweb="tab"] { color: #555a54; height: 38px; border-radius: 999px; padding: 0 .9rem; }
        [aria-selected="true"][data-baseweb="tab"] { color: #234c3d; background: #bcebd9; box-shadow: 0 4px 10px rgba(65,119,97,.14), inset 0 0 0 1px #9bd8c1; }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] {
            border: 1px solid #cbded5; border-radius: 18px; overflow: hidden;
            box-shadow: 0 20px 42px rgba(49,55,50,.14), 0 12px 32px rgba(116,207,175,.18);
            background: #fffefa;
        }
        [data-testid="stArrowVegaLiteChart"] {
            border: 1px solid #cfe0d8; border-radius: 18px; padding: .5rem;
            background: linear-gradient(145deg, #fffefa, #f2faf6);
            box-shadow: 0 20px 42px rgba(49,55,50,.13), 0 12px 30px rgba(120,169,189,.17);
        }
        details { border: 1px solid #d9dad4 !important; border-radius: 16px !important; background: #f8f7f2 !important; box-shadow: 0 12px 26px rgba(49,55,50,.10), 0 7px 18px rgba(116,207,175,.10); }
        details summary { color: #30332f !important; }
        details summary::marker { color: #35634f !important; }
        div[data-testid="stExpander"] > details p, div[data-testid="stExpander"] > details label,
        div[data-testid="stExpander"] > details span, div[data-testid="stExpander"] > details summary { color: #30332f !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color: #cfded6 !important; border-radius: 20px !important; background: #fffefa; box-shadow: 0 20px 42px rgba(49,55,50,.12), 0 12px 30px rgba(116,207,175,.13); }
        [data-testid="stVerticalBlockBorderWrapper"] h4 { color: #292c28; }
        .panel-kicker { display: inline-block; border-radius: 999px; padding: .27rem .55rem; margin-bottom: .25rem; font-size: .66rem; font-weight: 740; letter-spacing: .07em; text-transform: uppercase; }
        .panel-kicker.sage { color: #35634f; background: #dcf2e9; border: 1px solid #b9dfd0; }
        .panel-kicker.clay { color: #7a5948; background: #f5e5dc; border: 1px solid #e4c8b9; }
        .panel-kicker.mauve { color: #70465a; background: #f3e3ea; border: 1px solid #dec3cf; }
        .query-count { color: #737871; font-size: .76rem; margin: -.15rem 0 .55rem; }
        .stAlert { border-radius: 16px; background: #fffefa; border: 1px solid #d9ddd6; color: #333632; box-shadow: 0 8px 18px rgba(49,55,50,.06); }
        [data-testid="stSidebar"] [data-baseweb="radio"] > div { gap: .35rem; }
        [data-testid="stSidebar"] [data-baseweb="radio"] label { border: 1px solid #d6d8d1; border-radius: 14px; padding: .45rem .55rem; background: rgba(255,255,255,.48); }
        @media (max-width: 1000px) {
            .metric-grid, .group-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
        }
        @media (max-width: 650px) {
            .block-container { padding-left: .8rem; padding-right: .8rem; }
            .metric-grid, .group-grid { grid-template-columns: 1fr; }
            .hero-title { font-size: 1.4rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_product_ui_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #547f6d;
            --ipn-soft: #86d8b0;
            --ink: #333333;
            --muted: #757575;
            --panel: #f5f5f0;
            --panel-2: #eeeeea;
            --line: #deded8;
            --stone: #f3f3ee;
            --stone-2: #e6e6e1;
            --black: #f5f5f0;
            --green: #68b991;
            --amber: #d8b45d;
            --rose: #d68585;
            --blue: #7fa7b9;
            --mint: #86d8b0;
            --mint-dark: #58b889;
            --clay-shadow: 10px 10px 22px rgba(171,174,169,.42), -8px -8px 18px rgba(255,255,255,.94);
            --clay-low: 5px 5px 12px rgba(171,174,169,.34), -4px -4px 10px rgba(255,255,255,.88);
            --clay-inset: inset 3px 3px 7px rgba(171,174,169,.30), inset -3px -3px 7px rgba(255,255,255,.86);
        }
        html, body, [data-testid="stAppViewContainer"] { background: #f5f5f0; }
        .stApp {
            color: #333333;
            font-family: Inter, "Helvetica Neue", Arial, sans-serif;
            background:
                linear-gradient(rgba(67,71,67,.035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(67,71,67,.035) 1px, transparent 1px),
                #f5f5f0;
            background-size: 48px 48px;
        }
        .block-container { max-width: 1380px; padding-top: 1rem; padding-bottom: 2.5rem; }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3, h4 { color: #292b29; letter-spacing: -.035em; font-weight: 760; }
        p, label, [data-testid="stCaptionContainer"] { color: #686c68; }
        [data-testid="stSidebar"] {
            background:
                linear-gradient(rgba(67,71,67,.025) 1px, transparent 1px),
                linear-gradient(90deg, rgba(67,71,67,.025) 1px, transparent 1px),
                #efefe9;
            background-size: 32px 32px;
            border-right: 1px solid #d8d8d2;
            box-shadow: 10px 0 24px rgba(174,177,171,.20);
        }
        [data-testid="stSidebar"] * { color: #333633; }
        [data-testid="stSidebar"] [data-baseweb="radio"] > div { gap: .42rem; }
        [data-testid="stSidebar"] label[data-baseweb="radio"] {
            border: 1px solid #deded8; border-radius: 14px; padding: .48rem .62rem;
            background: #efefe9; box-shadow: var(--clay-low);
            transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:hover { transform: translateY(-1px); }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
            background: #d8f3e7; border-color: #a8dcc5; box-shadow: var(--clay-inset), 0 0 0 2px rgba(134,216,176,.18);
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) > div:first-child {
            background: #86d8b0 !important; border-color: #5dbb8e !important;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div { background: #ffffff !important; }
        [data-testid="stSidebar"] .catalog-strip { display: grid; gap: .55rem; }
        [data-testid="stSidebar"] .catalog-strip div {
            padding: .62rem .7rem; border-radius: 14px; background: #efefe9;
            border: 1px solid #deded8; box-shadow: var(--clay-low);
        }
        [data-testid="stSidebar"] .catalog-strip span { color: #517360; font-weight: 760; float: right; }
        .hero {
            position: relative; overflow: hidden; border: 1px solid #e0e0da; border-radius: 22px;
            padding: 1.25rem 1.4rem; margin-bottom: .9rem;
            background: linear-gradient(145deg, #f8f8f4 0%, #f1f4ef 58%, #dff4e9 100%);
            box-shadow: 14px 14px 30px rgba(171,174,169,.38), -10px -10px 24px rgba(255,255,255,.96);
        }
        .hero.compact { min-height: 154px; padding: .95rem 1rem; margin: 0; }
        .hero.compact .hero-title { font-size: 1.42rem; }
        .hero.compact .hero-subtitle { font-size: .78rem; line-height: 1.35; }
        .hero.compact .hero-date { margin-top: .5rem; }
        .hero.compact .badge-row { margin-top: .58rem; gap: .32rem; }
        .hero.compact .badge { padding: .24rem .45rem; font-size: .64rem; }
        .hero:after {
            content: ""; position: absolute; width: 205px; height: 205px; right: -75px; top: -112px; border-radius: 50%;
            background: radial-gradient(circle, rgba(134,216,176,.62), rgba(134,216,176,0) 69%);
        }
        .hero-kicker { color: #4c8b6e; font-size: .72rem; font-weight: 780; letter-spacing: .11em; text-transform: uppercase; }
        .hero-title { color: #292b29; font-size: 1.75rem; font-weight: 780; margin: .2rem 0 .18rem; }
        .hero-subtitle { color: #6c706c; font-size: .92rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #3f4541; font-size: .86rem; font-weight: 680; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .34rem .62rem; border-radius: 999px;
            background: #eeeeea; border: 1px solid #deded8; color: #4c514d; font-size: .72rem; font-weight: 690;
            box-shadow: 3px 3px 7px rgba(171,174,169,.28), -3px -3px 7px rgba(255,255,255,.88);
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 50%; background: #68b991; box-shadow: 0 0 0 3px rgba(104,185,145,.14); }
        .badge.warn { color: #745f2c; background: #f6edcf; border-color: #e5d494; }
        .badge.warn .badge-dot { background: #d8b45d; }
        .badge.ipn { color: #39624f; background: #d8f3e7; border-color: #a8dcc5; }
        .badge.ipn .badge-dot { background: #58b889; }
        .section-label, .top-control-label { color: #5e645f; font-size: .72rem; font-weight: 780; letter-spacing: .08em; text-transform: uppercase; }
        .section-label { margin: .15rem 0 .65rem; }
        .top-control-label { margin-bottom: .35rem; }
        .metric-grid, .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .8rem; }
        .metric-grid { margin: .2rem 0 1rem; }
        .group-grid { margin-bottom: 1rem; }
        .metric-card, .group-card {
            position: relative; overflow: hidden; border: 1px solid color-mix(in srgb, var(--accent) 18%, #deded8);
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 5%, #f8f8f4), #eeeeea 78%);
            box-shadow: var(--clay-shadow); transition: transform .18s ease, box-shadow .18s ease;
        }
        .metric-card:hover, .group-card:hover { transform: translateY(-2px); box-shadow: 13px 13px 26px rgba(171,174,169,.40), -9px -9px 20px rgba(255,255,255,.96); }
        .metric-card { min-height: 112px; border-radius: 18px; padding: .9rem 1rem; }
        .group-card { border-radius: 17px; padding: .82rem .9rem; }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 18px; right: 18px; height: 5px; border-radius: 0 0 999px 999px; background: var(--accent); opacity: .58; }
        .metric-label, .group-title { color: #515652; font-size: .75rem; font-weight: 720; }
        .metric-value { color: #292b29; font-size: 1.75rem; font-weight: 780; margin-top: .42rem; line-height: 1; }
        .metric-note, .group-main span, .group-foot { color: #7a7e7a; font-size: .68rem; }
        .group-title { min-height: 2.1em; }
        .group-main { display: flex; justify-content: space-between; align-items: baseline; margin-top: .35rem; }
        .group-main strong { color: #2d302d; font-size: 1.28rem; }
        .group-bar { height: 7px; background: #deded8; border-radius: 999px; overflow: hidden; margin: .55rem 0 .45rem; box-shadow: var(--clay-inset); }
        .group-bar span { display: block; height: 100%; border-radius: 999px; background: var(--accent); opacity: .82; }
        .group-foot { display: flex; justify-content: space-between; }
        .empty-state { border: 1px solid #deded8; border-radius: 20px; text-align: center; padding: 2rem 1rem; color: #727672; background: #efefe9; box-shadow: var(--clay-shadow); }
        .empty-state strong { display: block; color: #333633; font-size: 1rem; margin-bottom: .3rem; }
        [data-testid="stMetric"] { background: #efefe9; border: 1px solid #deded8; border-radius: 17px; padding: .72rem .82rem; box-shadow: var(--clay-low); }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #303330; }
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 17px; background: #efefe9; border: 1px solid #deded8; padding: .55rem; box-shadow: var(--clay-shadow); }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        [data-testid="stFileUploaderDropzone"] p, [data-testid="stFileUploaderDropzone"] span, [data-testid="stFileUploaderDropzone"] div { color: #4f544f !important; }
        button, [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input { border-radius: 12px !important; }
        button svg, summary svg, [data-baseweb="select"] svg, [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg { color: #3c433e !important; fill: #3c433e !important; stroke: #3c433e !important; opacity: 1 !important; }
        button [data-testid="stIconMaterial"], summary [data-testid="stIconMaterial"], [data-baseweb="select"] [data-testid="stIconMaterial"] { color: #3c433e !important; opacity: 1 !important; }
        button[kind="secondary"], .stDownloadButton button {
            color: #315b48 !important; background: linear-gradient(145deg, #9ce3c1, #76cda3) !important;
            border: 1px solid #75c79f !important; box-shadow: 6px 6px 13px rgba(163,169,164,.38), -5px -5px 11px rgba(255,255,255,.92);
            font-weight: 720 !important;
        }
        button[kind="secondary"]:hover, .stDownloadButton button:hover { background: linear-gradient(145deg, #a9ebcd, #82d9ae) !important; transform: translateY(-1px); box-shadow: 8px 8px 16px rgba(163,169,164,.40), -6px -6px 13px rgba(255,255,255,.95); }
        button[kind="secondary"]:active, .stDownloadButton button:active { transform: translateY(1px); box-shadow: var(--clay-inset); }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input {
            color: #343834 !important; background: #efefe9 !important; border: 1px solid #d9d9d3 !important; box-shadow: var(--clay-inset);
        }
        [data-baseweb="select"] > div:focus-within, [data-baseweb="input"] > div:focus-within, .stTextInput input:focus { border-color: #68b991 !important; box-shadow: var(--clay-inset), 0 0 0 2px rgba(104,185,145,.30), 0 0 13px rgba(134,216,176,.34) !important; }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] { color: #333633 !important; background: #f3f3ee !important; border: 1px solid #d9d9d3 !important; border-radius: 14px !important; box-shadow: 12px 12px 24px rgba(163,169,164,.38), -7px -7px 16px rgba(255,255,255,.92) !important; }
        [role="option"] { color: #333633 !important; background: #f3f3ee !important; }
        [role="option"]:hover, [role="option"][aria-selected="true"] { color: #315b48 !important; background: #d8f3e7 !important; }
        [data-baseweb="tab-list"] { gap: .25rem; background: #e8e8e3; border: 1px solid #d9d9d3; padding: .35rem; border-radius: 16px; box-shadow: var(--clay-inset); }
        [data-baseweb="tab"] { color: #5a5f5a; height: 39px; border-radius: 12px; padding: 0 .92rem; }
        [aria-selected="true"][data-baseweb="tab"] { color: #315b48; background: linear-gradient(145deg, #a0e6c5, #7bd1a7); box-shadow: 4px 4px 9px rgba(163,169,164,.36), -3px -3px 8px rgba(255,255,255,.90); }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 1px solid #d9d9d3; border-radius: 17px; overflow: hidden; background: #f5f5f0; box-shadow: var(--clay-shadow); }
        [data-testid="stArrowVegaLiteChart"] { border: 1px solid #d9d9d3; border-radius: 18px; padding: .6rem; background: #f5f5f0; box-shadow: var(--clay-shadow); }
        details { border: 1px solid #d9d9d3 !important; border-radius: 15px !important; background: #efefe9 !important; box-shadow: var(--clay-low); }
        details summary, div[data-testid="stExpander"] > details p, div[data-testid="stExpander"] > details label, div[data-testid="stExpander"] > details span { color: #343834 !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid #d9d9d3 !important; border-radius: 19px !important; background: #f2f2ed; box-shadow: var(--clay-shadow); }
        [data-testid="stVerticalBlockBorderWrapper"] h4 { color: #303330; }
        .panel-kicker { display: inline-block; border-radius: 999px; padding: .28rem .58rem; margin-bottom: .25rem; font-size: .66rem; font-weight: 760; letter-spacing: .07em; text-transform: uppercase; box-shadow: var(--clay-low); }
        .panel-kicker.sage { color: #315b48; background: #d8f3e7; border: 1px solid #a8dcc5; }
        .panel-kicker.clay { color: #76584b; background: #f0ddd3; border: 1px solid #dfc3b5; }
        .panel-kicker.mauve { color: #715261; background: #ecdde4; border: 1px solid #d9c1cc; }
        .query-count { color: #6e736e; font-size: .76rem; margin: -.15rem 0 .55rem; }
        .stAlert { border-radius: 16px; background: #efefe9; border: 1px solid #d9d9d3; color: #343834; box-shadow: var(--clay-low); }
        @media (max-width: 1000px) { .metric-grid, .group-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
        @media (max-width: 650px) { .block-container { padding-left: .8rem; padding-right: .8rem; } .metric-grid, .group-grid { grid-template-columns: 1fr; } .hero-title { font-size: 1.4rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_tactile_studio_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #8e735e;
            --ipn-soft: #d5b276;
            --ink: #f2eee7;
            --muted: #bbb5ac;
            --panel: #303238;
            --panel-2: #25272d;
            --line: rgba(239,224,196,.22);
            --stone: #6f685f;
            --stone-2: #4a4744;
            --black: #16191e;
            --green: #86c9ad;
            --amber: #e1bf6d;
            --rose: #c88c8e;
            --blue: #72b9ff;
            --electric: #70b9ff;
            --gold: #e4c572;
        }
        html, body, [data-testid="stAppViewContainer"] { background: #171a20; }
        .stApp {
            color: var(--ink);
            background:
                radial-gradient(circle at 18% 8%, rgba(107,137,166,.16), transparent 26%),
                radial-gradient(circle at 88% 4%, rgba(213,178,118,.12), transparent 24%),
                repeating-linear-gradient(117deg, rgba(255,255,255,.012) 0 1px, transparent 1px 4px),
                linear-gradient(145deg, #25282e 0%, #171a20 58%, #12151a 100%);
        }
        .block-container { max-width: 1380px; padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stHeader"] { background: rgba(22,25,30,.75); backdrop-filter: blur(14px); }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3, h4 { color: #f4f0e9; letter-spacing: -.025em; text-shadow: 0 2px 5px rgba(0,0,0,.38); }
        p, label, [data-testid="stCaptionContainer"] { color: #bbb5ac; }
        [data-testid="stSidebar"] {
            background:
                linear-gradient(155deg, rgba(124,112,99,.50), rgba(44,47,55,.96) 45%, rgba(28,32,39,.98)),
                repeating-linear-gradient(110deg, rgba(255,255,255,.018) 0 1px, transparent 1px 4px);
            border-right: 1px solid rgba(231,199,135,.32);
            box-shadow: inset -1px 0 rgba(255,255,255,.08), 18px 0 45px rgba(0,0,0,.28);
        }
        [data-testid="stSidebar"] * { color: #eee8df; }
        [data-testid="stSidebar"] [data-baseweb="radio"] > div { gap: .42rem; }
        [data-testid="stSidebar"] [data-baseweb="radio"] label {
            border: 1px solid rgba(235,215,180,.20); border-radius: 9px; padding: .48rem .58rem;
            background: linear-gradient(145deg, rgba(126,119,110,.44), rgba(48,51,59,.62));
            box-shadow: inset 1px 1px rgba(255,255,255,.08), inset -2px -2px rgba(0,0,0,.22), 0 5px 12px rgba(0,0,0,.20);
        }
        [data-testid="stSidebar"] .catalog-strip { display: grid; gap: .45rem; }
        [data-testid="stSidebar"] .catalog-strip div {
            padding: .58rem .65rem; border-radius: 9px; border: 1px solid rgba(228,197,114,.20);
            background: linear-gradient(145deg, rgba(121,111,99,.40), rgba(41,44,52,.82));
            box-shadow: inset 1px 1px rgba(255,255,255,.08), 0 7px 14px rgba(0,0,0,.24);
        }
        [data-testid="stSidebar"] .catalog-strip span { color: #e7c987; float: right; }
        .hero {
            position: relative; overflow: hidden; border: 1px solid rgba(231,199,135,.42); border-radius: 16px;
            padding: 1.25rem 1.4rem; margin-bottom: .85rem;
            background:
                linear-gradient(135deg, rgba(53,92,128,.90), rgba(43,49,58,.96) 48%, rgba(102,89,75,.92)),
                repeating-linear-gradient(110deg, rgba(255,255,255,.02) 0 1px, transparent 1px 4px);
            box-shadow: inset 1px 1px rgba(255,255,255,.22), inset -3px -3px rgba(0,0,0,.30),
                        0 16px 28px rgba(0,0,0,.48), 0 0 22px rgba(228,197,114,.16);
        }
        .hero.compact { min-height: 154px; padding: .95rem 1rem; margin: 0; }
        .hero.compact .hero-title { font-size: 1.42rem; }
        .hero.compact .hero-subtitle { font-size: .78rem; line-height: 1.35; }
        .hero.compact .hero-date { margin-top: .5rem; }
        .hero.compact .badge-row { margin-top: .58rem; gap: .32rem; }
        .hero.compact .badge { padding: .24rem .45rem; font-size: .64rem; }
        .hero:after {
            content: ""; position: absolute; width: 210px; height: 210px; right: -80px; top: -115px; border-radius: 50%;
            background: radial-gradient(circle, rgba(113,185,255,.32), rgba(113,185,255,0) 68%);
        }
        .hero-kicker { color: #f0d48f; font-size: .72rem; font-weight: 760; letter-spacing: .12em; text-transform: uppercase; }
        .hero-title { color: #fffaf1; font-size: 1.75rem; font-weight: 740; margin: .2rem 0 .18rem; }
        .hero-subtitle { color: #d1cbc2; font-size: .92rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #fff2cf; font-size: .86rem; font-weight: 650; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .32rem .58rem; border-radius: 8px;
            background: linear-gradient(145deg, rgba(120,126,133,.52), rgba(39,43,50,.68));
            border: 1px solid rgba(216,205,185,.25); color: #f2eee7; font-size: .72rem; font-weight: 670;
            box-shadow: inset 1px 1px rgba(255,255,255,.10), 0 4px 9px rgba(0,0,0,.28);
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 50%; background: #86c9ad; box-shadow: 0 0 7px #86c9ad; }
        .badge.warn .badge-dot { background: #e4c572; box-shadow: 0 0 7px #e4c572; }
        .badge.ipn { color: #ffe4ae; border-color: rgba(228,197,114,.42); background: linear-gradient(145deg, rgba(126,94,62,.58), rgba(46,43,43,.72)); }
        .badge.ipn .badge-dot { background: #e4c572; box-shadow: 0 0 7px #e4c572; }
        .section-label, .top-control-label { color: #d8cfc0; font-size: .72rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
        .section-label { margin: .15rem 0 .65rem; }
        .top-control-label { margin-bottom: .35rem; }
        .metric-grid, .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .75rem; }
        .metric-grid { margin: .2rem 0 .95rem; }
        .group-grid { margin-bottom: .95rem; }
        .metric-card, .group-card {
            position: relative; overflow: hidden; border-radius: 12px;
            border: 1px solid color-mix(in srgb, var(--accent) 48%, #cabd9f);
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 22%, #55535a), #303239 45%, #25282e 100%);
            box-shadow: inset 1px 1px rgba(255,255,255,.18), inset -3px -3px rgba(0,0,0,.28),
                        0 12px 18px rgba(0,0,0,.42), 0 0 16px color-mix(in srgb, var(--accent) 20%, transparent);
        }
        .metric-card { min-height: 112px; padding: .9rem 1rem; }
        .group-card { padding: .82rem .9rem; }
        .metric-card:before { content: ""; position: absolute; inset: 5px; border: 1px solid rgba(255,255,255,.09); border-radius: 8px; pointer-events: none; }
        .metric-label, .group-title { color: #e8e1d7; font-size: .75rem; font-weight: 680; }
        .metric-value { color: #fffaf2; font-size: 1.75rem; font-weight: 740; margin-top: .42rem; line-height: 1; text-shadow: 0 2px 5px rgba(0,0,0,.45); }
        .metric-note, .group-main span, .group-foot { color: #bdb6ac; font-size: .68rem; }
        .group-title { min-height: 2.1em; }
        .group-main { display: flex; justify-content: space-between; align-items: baseline; margin-top: .35rem; }
        .group-main strong { color: #fffaf2; font-size: 1.28rem; }
        .group-bar { height: 7px; background: #171a20; border: 1px solid rgba(255,255,255,.09); border-radius: 99px; overflow: visible; margin: .55rem 0 .45rem; box-shadow: inset 0 2px 4px rgba(0,0,0,.58); }
        .group-bar span { display: block; height: 100%; border-radius: 99px; background: var(--accent); box-shadow: 0 0 9px color-mix(in srgb, var(--accent) 70%, transparent); }
        .group-foot { display: flex; justify-content: space-between; }
        .empty-state { border: 1px solid rgba(228,197,114,.26); border-radius: 14px; text-align: center; padding: 2.2rem 1rem; color: #bbb5ac; background: linear-gradient(145deg, #3a3a3d, #24272d); box-shadow: inset 1px 1px rgba(255,255,255,.08), 0 14px 26px rgba(0,0,0,.35); }
        .empty-state strong { display: block; color: #fff3d7; font-size: 1rem; margin-bottom: .3rem; }
        [data-testid="stMetric"] { background: linear-gradient(145deg, #68635d, #34363c); border: 1px solid rgba(232,209,164,.28); border-radius: 11px; padding: .7rem .8rem; box-shadow: inset 1px 1px rgba(255,255,255,.12), 0 9px 16px rgba(0,0,0,.34); }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #f5efe6; }
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 11px; background: linear-gradient(145deg, #5b5753, #303239); border: 1px solid rgba(228,197,114,.38); padding: .55rem; box-shadow: inset 1px 1px rgba(255,255,255,.14), inset -2px -2px rgba(0,0,0,.25), 0 10px 18px rgba(0,0,0,.38); }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        button, [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input { border-radius: 9px !important; }
        button svg, summary svg, [data-baseweb="select"] svg, [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg { color: #f1dfb7 !important; fill: #f1dfb7 !important; stroke: #f1dfb7 !important; opacity: 1 !important; }
        button[kind="secondary"], .stDownloadButton button {
            color: #fff8e9 !important; background: linear-gradient(180deg, #3f6f99, #294b6d) !important;
            border: 1px solid #dfc276 !important; box-shadow: inset 1px 1px rgba(255,255,255,.18), inset -2px -2px rgba(0,0,0,.24), 0 0 10px rgba(113,185,255,.38), 0 8px 14px rgba(0,0,0,.36);
        }
        button[kind="secondary"]:hover, .stDownloadButton button:hover { background: linear-gradient(180deg, #5795c8, #356990) !important; box-shadow: 0 0 16px rgba(113,185,255,.72), 0 9px 16px rgba(0,0,0,.38); }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input {
            color: #f3eee6 !important; background: linear-gradient(180deg, #5b5752, #3a3b40) !important;
            border: 1px solid rgba(226,203,156,.40) !important; box-shadow: inset 0 2px 5px rgba(0,0,0,.30), 0 0 0 1px rgba(255,255,255,.05);
        }
        [data-baseweb="select"] > div:focus-within, [data-baseweb="input"] > div:focus-within, .stTextInput input:focus {
            border-color: #e4c572 !important; box-shadow: 0 0 0 2px rgba(228,197,114,.30), 0 0 14px rgba(113,185,255,.58) !important;
        }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] { color: #f3eee6 !important; background: #d7d0c5 !important; border: 1px solid #e4c572 !important; border-radius: 9px !important; box-shadow: 0 18px 34px rgba(0,0,0,.52), 0 0 12px rgba(228,197,114,.24) !important; }
        [role="option"] { color: #292a2d !important; background: #d7d0c5 !important; }
        [role="option"]:hover, [role="option"][aria-selected="true"] { color: #fff8e9 !important; background: linear-gradient(90deg, #4e7fa8, #315675) !important; box-shadow: inset 0 0 0 1px #e4c572; }
        [data-baseweb="tab-list"] { gap: .3rem; background: linear-gradient(180deg, #55514d, #292c32); border: 1px solid rgba(228,197,114,.28); padding: .34rem; border-radius: 11px; box-shadow: inset 0 2px 5px rgba(0,0,0,.38), 0 9px 18px rgba(0,0,0,.34); }
        [data-baseweb="tab"] { color: #d7d0c7; height: 38px; border-radius: 8px; padding: 0 .86rem; }
        [aria-selected="true"][data-baseweb="tab"] { color: #fff7e6; background: linear-gradient(180deg, #3d6d98, #294b6d); border: 1px solid #e4c572; box-shadow: inset 1px 1px rgba(255,255,255,.14), 0 0 12px rgba(113,185,255,.50); }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 1px solid rgba(228,197,114,.34); border-radius: 11px; overflow: hidden; background: #24272d; box-shadow: inset 1px 1px rgba(255,255,255,.06), 0 16px 28px rgba(0,0,0,.46), 0 0 14px rgba(113,185,255,.12); }
        [data-testid="stArrowVegaLiteChart"] { border: 1px solid rgba(228,197,114,.30); border-radius: 12px; padding: .5rem; background: linear-gradient(145deg, #34373d, #22252b); box-shadow: inset 1px 1px rgba(255,255,255,.07), 0 15px 27px rgba(0,0,0,.44), 0 0 13px rgba(113,185,255,.14); }
        details { border: 1px solid rgba(228,197,114,.30) !important; border-radius: 10px !important; background: linear-gradient(145deg, #625c55, #303239) !important; box-shadow: inset 1px 1px rgba(255,255,255,.12), 0 10px 18px rgba(0,0,0,.38); }
        details summary, div[data-testid="stExpander"] > details p, div[data-testid="stExpander"] > details label, div[data-testid="stExpander"] > details span { color: #f1ebe2 !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color: rgba(228,197,114,.28) !important; border-radius: 13px !important; background: linear-gradient(145deg, #34363c, #22252b); box-shadow: inset 1px 1px rgba(255,255,255,.07), 0 16px 28px rgba(0,0,0,.44); }
        [data-testid="stVerticalBlockBorderWrapper"] h4 { color: #f5eee4; }
        .panel-kicker { display: inline-block; border-radius: 7px; padding: .28rem .55rem; margin-bottom: .25rem; font-size: .66rem; font-weight: 740; letter-spacing: .07em; text-transform: uppercase; box-shadow: inset 1px 1px rgba(255,255,255,.10), 0 4px 8px rgba(0,0,0,.26); }
        .panel-kicker.sage { color: #d8f1e5; background: #3c6658; border: 1px solid #86c9ad; }
        .panel-kicker.clay { color: #ffe3c8; background: #775748; border: 1px solid #c99070; }
        .panel-kicker.mauve { color: #f3dbe5; background: #6d4f60; border: 1px solid #c88caa; }
        .query-count { color: #bdb6ac; font-size: .76rem; margin: -.15rem 0 .55rem; }
        .stAlert { border-radius: 10px; background: linear-gradient(145deg, #5b5751, #303239); border: 1px solid #e4c572; color: #fff2d4; box-shadow: inset 1px 1px rgba(255,255,255,.10), 0 10px 18px rgba(0,0,0,.38), 0 0 10px rgba(228,197,114,.20); }
        @media (max-width: 1000px) { .metric-grid, .group-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
        @media (max-width: 650px) { .block-container { padding-left: .8rem; padding-right: .8rem; } .metric-grid, .group-grid { grid-template-columns: 1fr; } .hero-title { font-size: 1.4rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_obra_vigente_theme_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #111111;
            --ipn-soft: #ffb300;
            --ink: #222222;
            --muted: #666666;
            --panel: #f4f4f1;
            --panel-2: #e7e7e4;
            --line: #191919;
            --stone: #eeeeeb;
            --stone-2: #d7d7d4;
            --black: #f7f7f4;
            --green: #68a87f;
            --amber: #ffb300;
            --rose: #c85f62;
            --blue: #477a9d;
        }
        html, body, [data-testid="stAppViewContainer"] { background: #f7f7f4; }
        .stApp {
            color: #222;
            font-family: "Courier New", Consolas, monospace;
            background:
                linear-gradient(rgba(40,40,40,.065) 1px, transparent 1px),
                linear-gradient(90deg, rgba(40,40,40,.065) 1px, transparent 1px),
                linear-gradient(rgba(40,40,40,.025) 1px, transparent 1px),
                linear-gradient(90deg, rgba(40,40,40,.025) 1px, transparent 1px),
                #f7f7f4;
            background-size: 48px 48px, 48px 48px, 8px 8px, 8px 8px;
        }
        .block-container { max-width: 1380px; padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stHeader"] { background: rgba(247,247,244,.92); border-bottom: 1px solid #bcbcb8; }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3, h4, p, label, button, input { font-family: "Courier New", Consolas, monospace !important; }
        h1, h2, h3, h4 { color: #111; letter-spacing: -.045em; font-weight: 900; text-transform: uppercase; }
        p, label, [data-testid="stCaptionContainer"] { color: #4b4b49; }
        [data-testid="stSidebar"] {
            background:
                linear-gradient(rgba(30,30,30,.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(30,30,30,.06) 1px, transparent 1px),
                #ededE9;
            background-size: 16px 16px;
            border-right: 2px solid #111;
            box-shadow: 7px 0 0 rgba(0,0,0,.12);
        }
        [data-testid="stSidebar"] * { color: #191919; }
        [data-testid="stSidebar"] [data-baseweb="radio"] > div { gap: .35rem; }
        [data-testid="stSidebar"] label[data-baseweb="radio"] {
            border: 1px solid #111; border-radius: 0; padding: .45rem .55rem;
            background: #f4f4f1; box-shadow: 3px 3px 0 #aaa;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
            background: #ffb300; box-shadow: 3px 3px 0 #111;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) > div:first-child {
            background: #ffb300 !important; border-color: #111 !important; box-shadow: 0 0 0 1px #111;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div {
            background: #111 !important;
        }
        [data-testid="stSidebar"] .catalog-strip { display: grid; gap: .42rem; }
        [data-testid="stSidebar"] .catalog-strip div {
            padding: .55rem .62rem; border: 1px solid #111; border-radius: 0;
            background: #f3f3f0; box-shadow: 3px 3px 0 #b8b8b4;
        }
        [data-testid="stSidebar"] .catalog-strip span { color: #111; float: right; font-weight: 900; }
        .hero {
            position: relative; overflow: hidden; border: 2px solid #111; border-radius: 0;
            padding: 1.25rem 1.4rem; margin-bottom: .85rem;
            background:
                linear-gradient(rgba(0,0,0,.035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0,0,0,.035) 1px, transparent 1px),
                #f1f1ee;
            background-size: 12px 12px;
            box-shadow: 6px 6px 0 #111, 11px 11px 0 rgba(255,179,0,.55);
        }
        .hero.compact { min-height: 154px; padding: .95rem 1rem; margin: 0; }
        .hero.compact .hero-title { font-size: 1.42rem; }
        .hero.compact .hero-subtitle { font-size: .78rem; line-height: 1.35; }
        .hero.compact .hero-date { margin-top: .5rem; }
        .hero.compact .badge-row { margin-top: .58rem; gap: .32rem; }
        .hero.compact .badge { padding: .24rem .45rem; font-size: .64rem; }
        .hero:after { content: "SYS / ACTIVE"; position: absolute; right: 10px; top: 8px; color: #777; font-size: .58rem; letter-spacing: .08em; }
        .hero-kicker { color: #111; font-size: .72rem; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; border-bottom: 1px dashed #111; padding-bottom: .22rem; }
        .hero-title { color: #050505; font-size: 1.75rem; font-weight: 900; margin: .3rem 0 .18rem; text-transform: uppercase; }
        .hero-subtitle { color: #4f4f4c; font-size: .88rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #111; font-size: .86rem; font-weight: 900; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .32rem .58rem;
            border-radius: 999px; background: #e3e3e0; border: 1px solid #111;
            color: #191919; font-size: .70rem; font-weight: 800; box-shadow: 2px 2px 0 #aaa;
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 0; background: #333; }
        .badge.warn { background: #fff2c5; }
        .badge.warn .badge-dot { background: #ffb300; }
        .badge.ipn { color: #111; border-color: #111; background: #ffb300; box-shadow: 2px 2px 0 #111; }
        .badge.ipn .badge-dot { background: #111; }
        .section-label, .top-control-label { color: #111; font-size: .72rem; font-weight: 900; letter-spacing: .06em; text-transform: uppercase; }
        .section-label { margin: .15rem 0 .65rem; border-bottom: 1px dashed #111; padding-bottom: .3rem; }
        .top-control-label { margin-bottom: .35rem; }
        .metric-grid, .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .75rem; }
        .metric-grid { margin: .2rem 0 1rem; }
        .group-grid { margin-bottom: 1rem; }
        .metric-card, .group-card {
            position: relative; overflow: hidden; border: 2px solid #111; border-radius: 0;
            background: #f0f0ed; box-shadow: 5px 5px 0 #aaa, 8px 8px 0 color-mix(in srgb, var(--accent) 48%, transparent);
        }
        .metric-card { min-height: 112px; padding: .9rem 1rem; }
        .group-card { padding: .82rem .9rem; }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 11px; background: var(--accent); border-bottom: 1px solid #111; }
        .metric-label, .group-title { color: #333; font-size: .72rem; font-weight: 900; text-transform: uppercase; }
        .metric-label { margin-top: .5rem; }
        .metric-value { color: #050505; font-size: 1.75rem; font-weight: 900; margin-top: .42rem; line-height: 1; }
        .metric-note, .group-main span, .group-foot { color: #555; font-size: .67rem; }
        .group-title { min-height: 2.1em; border-bottom: 1px dashed #777; }
        .group-main { display: flex; justify-content: space-between; align-items: baseline; margin-top: .45rem; }
        .group-main strong { color: #111; font-size: 1.28rem; }
        .group-bar { height: 9px; background: #d4d4d0; border: 1px solid #111; border-radius: 0; overflow: hidden; margin: .55rem 0 .45rem; }
        .group-bar span { display: block; height: 100%; border-radius: 0; background: var(--accent); border-right: 1px solid #111; }
        .group-foot { display: flex; justify-content: space-between; }
        .empty-state { border: 2px solid #111; border-radius: 0; text-align: left; padding: 1.5rem; color: #333; background: #efefec; box-shadow: 6px 6px 0 #111; }
        .empty-state:before { content: "SYSTEM ALERT"; display: block; margin: -1.5rem -1.5rem 1rem; padding: .38rem .55rem; background: #ffb300; border-bottom: 2px solid #111; color: #111; font-weight: 900; }
        .empty-state strong { display: block; color: #111; font-size: 1rem; margin-bottom: .3rem; }
        [data-testid="stMetric"] { background: #eeeeeb; border: 2px solid #111; border-radius: 0; padding: .7rem .8rem; box-shadow: 4px 4px 0 #aaa; }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #111; }
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 0; background: #eeeeeb; border: 2px solid #111; padding: .55rem; box-shadow: 5px 5px 0 #aaa; }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        [data-testid="stFileUploaderDropzone"] p,
        [data-testid="stFileUploaderDropzone"] span,
        [data-testid="stFileUploaderDropzone"] div { color: #111 !important; }
        button, [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input { border-radius: 0 !important; }
        button svg, summary svg, [data-baseweb="select"] svg, [data-testid="stSidebarCollapseButton"] svg, [data-testid="collapsedControl"] svg { color: #111 !important; fill: #111 !important; stroke: #111 !important; opacity: 1 !important; }
        button[kind="secondary"], .stDownloadButton button { color: #111 !important; background: #d8d8d5 !important; border: 2px solid #111 !important; box-shadow: 4px 4px 0 #111; }
        button[kind="secondary"]:hover, .stDownloadButton button:hover { background: #ffb300 !important; box-shadow: 6px 6px 0 #111, 0 0 18px rgba(255,179,0,.55); transform: translate(-1px,-1px); }
        button[kind="secondary"]:active, .stDownloadButton button:active { transform: translate(3px,3px); box-shadow: 1px 1px 0 #111; }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input { color: #111 !important; background: #f0f0ed !important; border: 2px solid #111 !important; box-shadow: 3px 3px 0 #aaa; }
        [data-baseweb="select"] > div:focus-within, [data-baseweb="input"] > div:focus-within, .stTextInput input:focus { border-color: #111 !important; box-shadow: 4px 4px 0 #ffb300, 0 0 12px rgba(255,179,0,.52) !important; }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] { color: #111 !important; background: #f1f1ee !important; border: 2px solid #111 !important; border-radius: 0 !important; box-shadow: 6px 6px 0 #111 !important; }
        [role="option"] { color: #111 !important; background: #f1f1ee !important; border-bottom: 1px solid #c2c2be; }
        [role="option"]:hover, [role="option"][aria-selected="true"] { color: #111 !important; background: #ffb300 !important; }
        [data-baseweb="tab-list"] { gap: 0; background: transparent; border: 0; border-bottom: 2px solid #111; padding: 0; border-radius: 0; box-shadow: none; }
        [data-baseweb="tab"] { color: #111; height: 40px; border-radius: 0; padding: 0 .95rem; border: 1px solid transparent; border-bottom: 0; }
        [aria-selected="true"][data-baseweb="tab"] { color: #111; background: #ffb300; border: 2px solid #111; border-bottom: 0; box-shadow: 3px -2px 0 rgba(0,0,0,.16); }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 2px solid #111; border-radius: 0; overflow: hidden; background: #efefec; box-shadow: 6px 6px 0 #111; }
        [data-testid="stArrowVegaLiteChart"] { border: 2px solid #111; border-radius: 0; padding: .5rem; background: #f0f0ed; box-shadow: 6px 6px 0 #111, 10px 10px 0 rgba(255,179,0,.42); }
        details { border: 2px solid #111 !important; border-radius: 0 !important; background: #e6e6e3 !important; box-shadow: 4px 4px 0 #111; }
        details summary, div[data-testid="stExpander"] > details p, div[data-testid="stExpander"] > details label, div[data-testid="stExpander"] > details span { color: #111 !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { border: 2px solid #111 !important; border-radius: 0 !important; background: #f0f0ed; box-shadow: 6px 6px 0 #111; }
        [data-testid="stVerticalBlockBorderWrapper"] h4 { color: #111; }
        .panel-kicker { display: inline-block; border-radius: 0; padding: .3rem .55rem; margin-bottom: .25rem; font-size: .66rem; font-weight: 900; letter-spacing: .04em; text-transform: uppercase; border: 1px solid #111; box-shadow: 2px 2px 0 #111; }
        .panel-kicker.sage, .panel-kicker.clay, .panel-kicker.mauve { color: #111; background: #ffb300; border-color: #111; }
        .query-count { color: #444; font-size: .76rem; margin: -.15rem 0 .55rem; }
        .stAlert { border-radius: 0; background: #f0f0ed; border: 2px solid #111; border-left: 13px solid #ffb300; color: #111; box-shadow: 5px 5px 0 #111; }
        @media (max-width: 1000px) { .metric-grid, .group-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
        @media (max-width: 650px) { .block-container { padding-left: .8rem; padding-right: .8rem; } .metric-grid, .group-grid { grid-template-columns: 1fr; } .hero-title { font-size: 1.4rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def problems_table(results, pdf_only, catalog_issues) -> pd.DataFrame:
    return build_problems_table(
        results,
        pdf_only,
        catalog_issues,
        problem_statuses={STATUS_NOT_FOUND, STATUS_AMBIGUOUS},
    )


def load_catalog_source(uploaded_file, remote_url: str, loader, label: str) -> tuple[pd.DataFrame | None, dict[str, object]]:
    diagnostic: dict[str, object] = {"origen": "sin configurar", "error": ""}
    payload: bytes | None = None
    if uploaded_file is not None:
        payload = uploaded_file.getvalue()
        diagnostic["origen"] = "archivo subido"
    elif remote_url:
        payload, error, remote_diagnostic = cached_remote_catalog(remote_url)
        diagnostic.update(remote_diagnostic)
        diagnostic["origen"] = "URL remota"
        diagnostic["error"] = error or ""
        if error:
            st.warning(
                f"{label}: no se pudo cargar la fuente remota. "
                f"HTTP: {remote_diagnostic.get('status_http') or 'sin respuesta'}."
            )
    if payload is None:
        return None, diagnostic
    try:
        return loader(payload), diagnostic
    except ValueError as exc:
        diagnostic["error"] = str(exc)
        st.error(f"{label}: {exc}")
        if isinstance(exc, CatalogFormatError) and exc.diagnostics:
            diagnostic_frame = pd.DataFrame(exc.diagnostics)
            st.dataframe(styled_dataframe(diagnostic_frame), use_container_width=True, hide_index=True)
    except Exception as exc:
        diagnostic["error"] = type(exc).__name__
        st.error(f"{label}: no fue posible leer el archivo.")
    return None, diagnostic


def badge(label: str, ok: bool = True, ipn: bool = False) -> str:
    classes = "badge"
    if not ok:
        classes += " warn"
    if ipn:
        classes += " ipn"
    return f'<span class="{classes}"><span class="badge-dot"></span>{html.escape(label)}</span>'


def render_header(
    selected_date: str | None,
    catalog: pd.DataFrame,
    paae_ok: bool,
    docentes_ok: bool,
    pdf_loaded: bool,
    *,
    compact: bool = False,
) -> None:
    date_text = format_date_with_weekday(selected_date) if selected_date else "Esperando reporte PDF"
    badges = "".join(
        [
            badge("IPN · corte operativo", ipn=True),
            badge(f"v{APP_VERSION}", ipn=True),
            badge("PAAE cargado" if paae_ok else "PAAE pendiente", paae_ok),
            badge("Docentes cargado" if docentes_ok else "Docentes pendiente", docentes_ok),
            badge("PDF cargado" if pdf_loaded else "PDF pendiente", pdf_loaded),
            badge(f"Catálogo {len(catalog):,}", not catalog.empty),
        ]
    )
    st.markdown(
        f"""
        <div class="hero{' compact' if compact else ''}">
            <div class="hero-kicker">Asistencia diaria</div>
            <div class="hero-title">Panel ejecutivo de checadas</div>
            <p class="hero-subtitle">Una lectura clara del corte del día, sin calificar horarios ni incidencias.</p>
            <div class="hero-date">{html.escape(date_text)}</div>
            <div class="badge-row">{badges}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str, accent: str) -> str:
    return (
        f'<div class="metric-card" style="--accent:{accent}">'
        f'<div class="metric-label">{html.escape(label)}</div>'
        f'<div class="metric-value">{html.escape(value)}</div>'
        f'<div class="metric-note">{html.escape(note)}</div></div>'
    )


def render_metrics(summary: dict[str, object]) -> None:
    cards = [
        metric_card("Total esperado", f"{int(summary['total_esperado']):,}", "Personal activo en catálogo", "#829eb5"),
        metric_card("Con checada", f"{int(summary['con_checada']):,}", "Al menos un registro", "#83a98b"),
        metric_card("Sin checada", f"{int(summary['sin_checada']):,}", "Localizados sin registro", "#c5a56b"),
        metric_card("No encontrados", f"{int(summary['no_encontrados']):,}", "Requieren revisión", "#bd7d83"),
        metric_card("% con checada", f"{float(summary['porcentaje_asistencia']):.1f}%", "Sobre el total esperado", "#a56a7f"),
    ]
    st.markdown(f'<div class="metric-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def group_values(group_summary: pd.DataFrame, personnel_type: str | None, shift: str) -> tuple[int, int, int]:
    mask = group_summary["turno"].eq(shift)
    if personnel_type:
        mask &= group_summary["tipo_personal"].eq(personnel_type)
    selected = group_summary[mask]
    if selected.empty:
        return 0, 0, 0
    return (
        int(selected["total_esperado"].sum()),
        int(selected["con_checada"].sum()),
        int(selected["sin_checada"].sum()),
    )


def render_group_cards(group_summary: pd.DataFrame) -> None:
    definitions = [
        ("PAAE Matutino", "PAAE", "MATUTINO", "#829eb5"),
        ("PAAE Vespertino", "PAAE", "VESPERTINO", "#8c86ad"),
        ("Docente Matutino", "DOCENTE", "MATUTINO", "#83a98b"),
        ("Docente Vespertino", "DOCENTE", "VESPERTINO", "#b28b72"),
        ("Sin turno / Revisar", None, "SIN TURNO / REVISAR", "#a56a7f"),
    ]
    cards = []
    for title, personnel_type, shift, accent in definitions:
        total, present, absent = group_values(group_summary, personnel_type, shift)
        percentage = (present / total * 100) if total else 0.0
        width = min(max(percentage, 0), 100)
        cards.append(
            f'<div class="group-card" style="--accent:{accent}">'
            f'<div class="group-title">{html.escape(title)}</div>'
            f'<div class="group-main"><strong>{present:,}</strong><span>de {total:,}</span></div>'
            f'<div class="group-bar"><span style="width:{width:.1f}%"></span></div>'
            f'<div class="group-foot"><span>{absent:,} sin checada</span><span>{percentage:.1f}%</span></div></div>'
        )
    st.markdown(f'<div class="group-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


STATUS_LABELS = {
    STATUS_WITH_CHECK: "Con checada",
    STATUS_WITHOUT_CHECK: "Sin checada",
    STATUS_NOT_FOUND: "No encontrado / revisar",
    STATUS_AMBIGUOUS: "Ambiguo / revisar",
}


def query_status_values(selection: str) -> list[str]:
    mapping = {
        "Con checada": [STATUS_WITH_CHECK],
        "Sin checada": [STATUS_WITHOUT_CHECK],
        "Por revisar": [STATUS_NOT_FOUND, STATUS_AMBIGUOUS],
        "No encontrado": [STATUS_NOT_FOUND],
        "Ambiguo": [STATUS_AMBIGUOUS],
    }
    return mapping.get(selection, [])


def query_table(results: pd.DataFrame) -> pd.DataFrame:
    visible = results.copy()
    visible["estado"] = visible["estado"].map(STATUS_LABELS).fillna(visible["estado"])
    visible = visible.rename(
        columns={
            "empleado_id": "ID",
            "nombre_completo": "Nombre",
            "tipo_personal": "Tipo",
            "turno": "Turno",
            "estado": "Estado",
            "checadas": "Checadas",
            "pagina_pdf": "Página PDF",
            "coincidencia_por": "Coincidencia",
            "detalle": "Detalle",
        }
    )
    columns = ["ID", "Nombre", "Tipo", "Turno", "Estado", "Checadas", "Página PDF", "Coincidencia", "Detalle"]
    return visible[columns]


def style_query_rows(row: pd.Series) -> list[str]:
    state = str(row.get("Estado") or "")
    if globals().get("visual_theme") == "Pintado claro":
        backgrounds = {
            "Con checada": "background-color: #dff4e9; color: #315b48",
            "Sin checada": "background-color: #f4e7d8; color: #664d3e",
            "No encontrado / revisar": "background-color: #f5edcf; color: #685725",
            "Ambiguo / revisar": "background-color: #ecdde4; color: #654a57",
        }
        style = backgrounds.get(state, "background-color: #f5f5f0; color: #333633")
        return [style] * len(row)
    if globals().get("visual_theme") == "Studio táctil":
        backgrounds = {
            "Con checada": "background-color: #314d48; color: #edf8f3",
            "Sin checada": "background-color: #59493d; color: #fff1df",
            "No encontrado / revisar": "background-color: #5b5138; color: #fff2c8",
            "Ambiguo / revisar": "background-color: #55404b; color: #f5e1ea",
        }
        style = backgrounds.get(state, "background-color: #292c32; color: #eee8df")
        return [style] * len(row)
    if globals().get("visual_theme") == "Obra vigente":
        backgrounds = {
            "Con checada": "background-color: #e5eee8; color: #111111",
            "Sin checada": "background-color: #fff0c8; color: #111111",
            "No encontrado / revisar": "background-color: #ffdf88; color: #111111",
            "Ambiguo / revisar": "background-color: #ead8de; color: #111111",
        }
        style = backgrounds.get(state, "background-color: #f0f0ed; color: #111111")
        return [style] * len(row)
    backgrounds = {
        "Con checada": "background-color: rgba(118,154,144,.10)",
        "Sin checada": "background-color: rgba(183,117,97,.11)",
        "No encontrado / revisar": "background-color: rgba(180,147,94,.10)",
        "Ambiguo / revisar": "background-color: rgba(165,106,127,.12)",
    }
    style = backgrounds.get(state, "")
    return [style] * len(row)


def styled_dataframe(dataframe: pd.DataFrame, row_styler=None):
    styler = dataframe.style
    if globals().get("visual_theme") == "Pintado claro":
        styler = styler.set_properties(
            **{
                "background-color": "#f5f5f0",
                "color": "#333633",
                "border-color": "#deded8",
            }
        ).set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#d8f3e7"),
                        ("color", "#315b48"),
                        ("border-color", "#b8ddcb"),
                        ("font-weight", "750"),
                    ],
                }
            ]
        )
    elif globals().get("visual_theme") == "Studio táctil":
        styler = styler.set_properties(
            **{
                "background-color": "#292c32",
                "color": "#eee8df",
                "border-color": "#444850",
            }
        ).set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#3b5871"),
                        ("color", "#fff3d4"),
                        ("border-color", "#806f50"),
                        ("font-weight", "700"),
                    ],
                }
            ]
        )
    elif globals().get("visual_theme") == "Obra vigente":
        styler = styler.set_properties(
            **{
                "background-color": "#f0f0ed",
                "color": "#111111",
                "border-color": "#777777",
                "font-family": "Courier New, monospace",
            }
        ).set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#d5d5d2"),
                        ("color", "#111111"),
                        ("border-color", "#111111"),
                        ("font-weight", "900"),
                        ("font-family", "Courier New, monospace"),
                    ],
                }
            ]
        )
    if row_styler is not None:
        styler = styler.apply(row_styler, axis=1)
    return styler


with st.sidebar:
    st.markdown("### Apariencia")
    visual_theme = st.radio(
        "Tema visual",
        ["Oscuro guinda", "Pintado claro", "Studio táctil", "Obra vigente"],
        index=0,
        key="visual_theme",
    )
    st.caption(f"Dashboard de asistencia · v{APP_VERSION}")

if visual_theme == "Pintado claro":
    inject_product_ui_theme_css()
elif visual_theme == "Studio táctil":
    inject_tactile_studio_theme_css()
elif visual_theme == "Obra vigente":
    inject_obra_vigente_theme_css()
else:
    inject_dark_theme_css()

inject_app_shell_css()

try:
    secrets = st.secrets
except Exception:
    secrets = None

paae_url = configured_catalog_url("PAAE_CATALOG_URL", secrets)
docentes_url = configured_catalog_url("DOCENTES_CATALOG_URL", secrets)

with st.sidebar.expander("Reemplazar catálogos", expanded=False):
    st.caption("Los catálogos remotos se cargan automáticamente. Usa estos controles solo para reemplazarlos durante la sesión.")
    paae_file = st.file_uploader(
        "Excel PAAE",
        type=["xlsx", "xls"],
        key="paae_catalog_upload",
        help="Reemplaza la URL PAAE durante esta sesión.",
    )
    docentes_file = st.file_uploader(
        "Excel Docentes",
        type=["xlsx", "xls"],
        key="docentes_catalog_upload",
        help="Acepta formatos docentes original y normalizado.",
    )

paae_df, paae_source_diagnostic = load_catalog_source(paae_file, paae_url, cached_load_paae, "PAAE")
docentes_df, docentes_source_diagnostic = load_catalog_source(
    docentes_file, docentes_url, cached_load_docentes, "Docentes"
)
catalog_data = build_catalog_result(paae_df, docentes_df)
catalog = catalog_data["employees"]
diagnostics = catalog_data["diagnostics"]

with st.sidebar:
    st.markdown("#### Estado del catálogo")
    st.markdown(
        '<div class="catalog-strip">'
        f'<div>PAAE <span>{len(paae_df) if paae_df is not None else 0}</span></div>'
        f'<div>Docentes <span>{len(docentes_df) if docentes_df is not None else 0}</span></div>'
        f'<div>Catálogo unificado <span>{len(catalog)}</span></div>'
        '<div><span>URLs privadas ocultas</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )

parsed_pdf = None
selected_date = None
identity_column, report_column, date_column = st.columns([1.35, 1, .8], gap="large")

with report_column:
    st.markdown('<div class="top-control-label">Reporte del día</div>', unsafe_allow_html=True)
    pdf_file = st.file_uploader(
        "Sube el Reporte de Tarjeta en PDF",
        type=["pdf"],
        help="Una página por empleado. El archivo se procesa en memoria.",
        label_visibility="collapsed",
    )
    if pdf_file is not None and not catalog.empty:
        try:
            with st.spinner("Leyendo reporte..."):
                parsed_pdf = cached_parse_pdf(pdf_file.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("No fue posible procesar el PDF. Revisa su formato.")

with date_column:
    st.markdown('<div class="top-control-label">Fecha del corte</div>', unsafe_allow_html=True)
    if parsed_pdf is not None:
        dates = parsed_pdf["dates"]
        if not dates:
            st.error("No se detectaron fechas en el PDF.")
        elif len(dates) == 1:
            selected_date = dates[0]
            st.markdown(f"**{format_date_with_weekday(selected_date)}**")
        else:
            selected_date = st.selectbox(
                "Fecha del corte",
                dates,
                index=len(dates) - 1,
                format_func=format_date_with_weekday,
                label_visibility="collapsed",
            )
    else:
        st.caption("Disponible al cargar el PDF")

with identity_column:
    render_header(
        selected_date,
        catalog,
        paae_df is not None and not paae_df.empty,
        docentes_df is not None and not docentes_df.empty,
        parsed_pdf is not None,
        compact=True,
    )

if catalog.empty:
    st.markdown(
        '<div class="empty-state"><strong>Catálogos pendientes</strong>'
        'Revisa las fuentes remotas o abre la barra lateral para reemplazarlas.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

if parsed_pdf is None or selected_date is None:
    st.markdown(
        '<div class="empty-state"><strong>El resumen aparecerá aquí</strong>'
        'Sube el PDF para generar el corte de asistencia y el desglose por grupo.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

analysis = analyze_attendance(catalog, parsed_pdf["pages"], selected_date)
results = analysis["results"]
summary = analysis["summary"]
group_summary = analysis["group_summary"]
present = results[results["estado"] == STATUS_WITH_CHECK].copy()
absent = results[results["estado"] == STATUS_WITHOUT_CHECK].copy()
problems = problems_table(results, analysis["pdf_only"], catalog_data["issues"])

st.markdown('<div class="section-label">Resumen ejecutivo</div>', unsafe_allow_html=True)
render_metrics(summary)
render_group_cards(group_summary)

if summary["ambiguos"]:
    st.warning(f"Hay {summary['ambiguos']} coincidencia(s) ambigua(s) que requieren revisión.")

tab_summary, tab_query, tab_problems, tab_catalog, tab_debug = st.tabs(
    ["Resumen", "Consulta", "Problemas", "Catálogo", "Depuración"]
)

with tab_summary:
    left, right = st.columns([0.9, 1.1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<span class="panel-kicker sage">Lectura visual</span>', unsafe_allow_html=True)
            st.markdown("#### Cobertura por grupo")
            chart_data = group_summary.copy()
            if not chart_data.empty:
                chart_data["grupo"] = (
                    chart_data["tipo_personal"].astype(str).str.title()
                    + " · "
                    + chart_data["turno"].astype(str).str.title()
                )
                if visual_theme == "Pintado claro":
                    chart_long = chart_data.melt(
                        id_vars="grupo",
                        value_vars=["con_checada", "sin_checada"],
                        var_name="estado",
                        value_name="personas",
                    )
                    chart = (
                        alt.Chart(chart_long)
                        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                        .encode(
                            x=alt.X("grupo:N", title=None, sort=None, axis=alt.Axis(labelAngle=-55, labelLimit=120)),
                            y=alt.Y("personas:Q", title=None, stack="zero", axis=alt.Axis(gridColor="#deded8")),
                            color=alt.Color(
                                "estado:N",
                                title=None,
                                scale=alt.Scale(
                                    domain=["con_checada", "sin_checada"],
                                    range=["#86d8b0", "#d8aa91"],
                                ),
                            ),
                            tooltip=["grupo:N", "estado:N", "personas:Q"],
                        )
                        .properties(height=300, background="#f5f5f0")
                        .configure_view(stroke=None)
                        .configure_axis(labelColor="#555b56", domainColor="#bfc2bc", tickColor="#bfc2bc")
                        .configure_legend(labelColor="#555b56", orient="bottom")
                    )
                    st.altair_chart(chart, use_container_width=True)
                elif visual_theme == "Studio táctil":
                    chart_long = chart_data.melt(
                        id_vars="grupo",
                        value_vars=["con_checada", "sin_checada"],
                        var_name="estado",
                        value_name="personas",
                    )
                    chart = (
                        alt.Chart(chart_long)
                        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                        .encode(
                            x=alt.X("grupo:N", title=None, sort=None, axis=alt.Axis(labelAngle=-55, labelLimit=120)),
                            y=alt.Y("personas:Q", title=None, stack="zero", axis=alt.Axis(gridColor="#444850")),
                            color=alt.Color(
                                "estado:N",
                                title=None,
                                scale=alt.Scale(
                                    domain=["con_checada", "sin_checada"],
                                    range=["#72b9ff", "#e4c572"],
                                ),
                            ),
                            tooltip=["grupo:N", "estado:N", "personas:Q"],
                        )
                        .properties(height=300, background="#292c32")
                        .configure_view(stroke=None)
                        .configure_axis(labelColor="#ddd6cb", domainColor="#80745f", tickColor="#80745f")
                        .configure_legend(labelColor="#ddd6cb", orient="bottom")
                    )
                    st.altair_chart(chart, use_container_width=True)
                elif visual_theme == "Obra vigente":
                    chart_long = chart_data.melt(
                        id_vars="grupo",
                        value_vars=["con_checada", "sin_checada"],
                        var_name="estado",
                        value_name="personas",
                    )
                    chart = (
                        alt.Chart(chart_long)
                        .mark_bar(stroke="#111111", strokeWidth=1)
                        .encode(
                            x=alt.X("grupo:N", title=None, sort=None, axis=alt.Axis(labelAngle=-55, labelLimit=120)),
                            y=alt.Y("personas:Q", title=None, stack="zero", axis=alt.Axis(gridColor="#c5c5c1")),
                            color=alt.Color(
                                "estado:N",
                                title=None,
                                scale=alt.Scale(
                                    domain=["con_checada", "sin_checada"],
                                    range=["#333333", "#ffb300"],
                                ),
                            ),
                            tooltip=["grupo:N", "estado:N", "personas:Q"],
                        )
                        .properties(height=300, background="#f0f0ed")
                        .configure_view(stroke="#111111", strokeWidth=1)
                        .configure_axis(
                            labelColor="#111111",
                            domainColor="#111111",
                            tickColor="#111111",
                            labelFont="Courier New",
                        )
                        .configure_legend(labelColor="#111111", labelFont="Courier New", orient="bottom")
                    )
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.bar_chart(
                        chart_data.set_index("grupo")[["con_checada", "sin_checada"]],
                        color=["#769a90", "#b77561"],
                        height=330,
                    )
    with right:
        with st.container(border=True):
            st.markdown('<span class="panel-kicker clay">Datos del corte</span>', unsafe_allow_html=True)
            st.markdown("#### Detalle del corte")
            compact_summary = group_summary.rename(
                columns={
                    "tipo_personal": "Tipo",
                    "turno": "Turno",
                    "total_esperado": "Total",
                    "con_checada": "Con checada",
                    "sin_checada": "Sin checada",
                    "porcentaje_asistencia": "%",
                }
            )
            compact_summary["%"] = compact_summary["%"].astype(float).round(1)
            visible_columns = ["Tipo", "Turno", "Total", "Con checada", "Sin checada", "%"]
            st.dataframe(
                styled_dataframe(compact_summary[visible_columns]),
                use_container_width=True,
                hide_index=True,
                height="auto",
                row_height=35,
                column_config={
                    "%": st.column_config.ProgressColumn(
                        "% con checada",
                        help="Porcentaje del grupo con al menos una checada.",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    )
                },
            )

    excel_bytes = build_excel_report(summary, group_summary, present, absent, problems)
    download_columns = st.columns(4)
    download_columns[0].download_button(
        "Reporte Excel",
        excel_bytes,
        f"asistencia_{selected_date.replace('/', '-')}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    download_columns[1].download_button(
        "Presentes CSV", dataframe_to_csv_bytes(present), "presentes.csv", "text/csv", use_container_width=True
    )
    download_columns[2].download_button(
        "Sin checada CSV", dataframe_to_csv_bytes(absent), "sin_checada.csv", "text/csv", use_container_width=True
    )
    download_columns[3].download_button(
        "Problemas CSV", dataframe_to_csv_bytes(problems), "problemas_cruce.csv", "text/csv", use_container_width=True
    )

with tab_query:
    with st.container(border=True):
        st.markdown('<span class="panel-kicker mauve">Consulta de personal</span>', unsafe_allow_html=True)
        st.markdown("#### Buscar asistencia individual")
        search_col, status_col = st.columns([2.1, 1], gap="medium")
        suggestion_options, suggestion_search_values = build_person_suggestions(results)
        search_selection = search_col.selectbox(
            "Nombre o ID",
            suggestion_options,
            index=None,
            placeholder="Escribe un nombre, apellido o ID...",
            accept_new_options=True,
            filter_mode="fuzzy",
            key="query_person",
        )
        search_value = suggestion_search_values.get(search_selection, search_selection or "")
        status_selection = status_col.selectbox(
            "Estado",
            ["Todos", "Con checada", "Sin checada", "Por revisar", "No encontrado", "Ambiguo"],
            key="query_status",
        )

        type_col, shift_col, match_col = st.columns(3, gap="medium")
        personnel_options = sorted(value for value in results["tipo_personal"].astype(str).unique() if value)
        shift_options = sorted(value for value in results["turno"].astype(str).unique() if value)
        match_options = sorted(value for value in results["coincidencia_por"].astype(str).unique() if value)
        personnel_selection = type_col.selectbox("Tipo de personal", ["Todos", *personnel_options], key="query_type")
        shift_selection = shift_col.selectbox("Turno", ["Todos", *shift_options], key="query_shift")
        match_selection = match_col.selectbox(
            "Coincidencia",
            ["Todos", *match_options, "Sin coincidencia"],
            key="query_match",
        )

        filtered_results = filter_results(
            results,
            search=search_value,
            statuses=query_status_values(status_selection),
            personnel_types=[] if personnel_selection == "Todos" else [personnel_selection],
            shifts=[] if shift_selection == "Todos" else [shift_selection],
            match_types=(
                []
                if match_selection == "Todos"
                else [""]
                if match_selection == "Sin coincidencia"
                else [match_selection]
            ),
        )

        query_metrics = st.columns(4)
        query_metrics[0].metric("Resultados", len(filtered_results))
        query_metrics[1].metric("Con checada", int((filtered_results["estado"] == STATUS_WITH_CHECK).sum()))
        query_metrics[2].metric("Sin checada", int((filtered_results["estado"] == STATUS_WITHOUT_CHECK).sum()))
        query_metrics[3].metric(
            "Por revisar",
            int(filtered_results["estado"].isin([STATUS_NOT_FOUND, STATUS_AMBIGUOUS]).sum()),
        )

        st.markdown(
            f'<div class="query-count">Corte: {html.escape(format_date_with_weekday(selected_date))} · '
            f'{len(filtered_results)} de {len(results)} personas</div>',
            unsafe_allow_html=True,
        )
        display_query = query_table(filtered_results)
        styled_query = styled_dataframe(display_query, style_query_rows)
        st.dataframe(
            styled_query,
            use_container_width=True,
            hide_index=True,
            height=500,
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Nombre": st.column_config.TextColumn("Nombre", width="large"),
                "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                "Turno": st.column_config.TextColumn("Turno", width="medium"),
                "Estado": st.column_config.TextColumn("Estado", width="medium"),
                "Checadas": st.column_config.TextColumn("Checadas", width="large"),
                "Página PDF": st.column_config.TextColumn("Página", width="small"),
                "Coincidencia": st.column_config.TextColumn("Coincidencia", width="small"),
                "Detalle": st.column_config.TextColumn("Detalle", width="large"),
            },
        )
        st.download_button(
            "Descargar consulta CSV",
            dataframe_to_csv_bytes(filtered_results),
            f"consulta_asistencia_{selected_date.replace('/', '-')}.csv",
            "text/csv",
        )

with tab_problems:
    if problems.empty:
        st.success("No se detectaron problemas de cruce.")
    else:
        st.caption("Estos registros requieren revisión; no detienen el análisis.")
        st.dataframe(styled_dataframe(problems), use_container_width=True, hide_index=True, height=470)

with tab_catalog:
    catalog_metrics = st.columns(5)
    catalog_metrics[0].metric("PAAE", int((catalog["tipo_personal"] == "PAAE").sum()))
    catalog_metrics[1].metric("Docentes", int((catalog["tipo_personal"] == "DOCENTE").sum()))
    catalog_metrics[2].metric("Matutino", int((catalog["turno"] == "MATUTINO").sum()))
    catalog_metrics[3].metric("Vespertino", int((catalog["turno"] == "VESPERTINO").sum()))
    catalog_metrics[4].metric("Revisar", int(diagnostics["sin_turno"]))
    st.dataframe(styled_dataframe(catalog), use_container_width=True, hide_index=True, height=390)
    st.download_button(
        "Descargar catálogo unificado",
        dataframe_to_csv_bytes(catalog),
        "catalogo_unificado.csv",
        "text/csv",
    )

with tab_debug:
    pdf_diagnostics = parsed_pdf["diagnostics"]
    debug_left, debug_right = st.columns(2)
    with debug_left:
        st.markdown("#### PDF")
        st.json(
            {
                "páginas_leídas": pdf_diagnostics["paginas_leidas"],
                "empleados_detectados_pdf": pdf_diagnostics["empleados_detectados"],
                "fechas_detectadas": parsed_pdf["dates"],
                "errores_parseo": len(pdf_diagnostics["errores"]),
            }
        )
        if pdf_diagnostics["errores"]:
            errors_frame = pd.DataFrame(pdf_diagnostics["errores"])
            st.dataframe(styled_dataframe(errors_frame), use_container_width=True, hide_index=True)
    with debug_right:
        st.markdown("#### Catálogos")
        st.json(
            {
                "registros_leidos_paae": diagnostics["registros_paae"],
                "registros_leidos_docentes": diagnostics["registros_docentes"],
                "catalogo_unificado": diagnostics["catalogo_unificado"],
                "duplicados_por_empleado_id": diagnostics["duplicados_empleado_id"],
                "sin_turno": diagnostics["sin_turno"],
                "sin_empleado_id": diagnostics["sin_empleado_id"],
                "sin_nombre": diagnostics["sin_nombre"],
                "fuente_paae": paae_source_diagnostic["origen"],
                "fuente_docentes": docentes_source_diagnostic["origen"],
            }
        )
