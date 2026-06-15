from __future__ import annotations

import html

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

APP_VERSION = "1.6.0"


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
        [data-testid="stSidebar"] { background: #efede6; border-right: 1px solid #d8d3c9; }
        [data-testid="stSidebar"] * { color: #1a1918; }
        [data-testid="stSidebar"] [data-baseweb="radio"] > div { gap: .35rem; }
        [data-testid="stSidebar"] [data-baseweb="radio"] label {
            border: 1px solid rgba(0,0,0,.10); border-radius: 12px; padding: .42rem .55rem;
            background: rgba(255,255,255,.42);
        }
        [data-testid="stSidebar"] .catalog-strip { display: grid; gap: .4rem; }
        [data-testid="stSidebar"] .catalog-strip div {
            padding: .48rem .58rem; border-radius: 10px; background: rgba(255,255,255,.34);
            border: 1px solid rgba(0,0,0,.08);
        }
        [data-testid="stSidebar"] .catalog-strip span { float: right; }
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


def inject_product_ui_theme_css() -> None:
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
            --shadow: 0 14px 32px rgba(49,55,50,.10), 0 3px 9px rgba(49,55,50,.06);
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
            box-shadow: var(--shadow), 0 10px 25px color-mix(in srgb, var(--accent) 9%, transparent);
        }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 14px; right: 14px; height: 4px; border-radius: 0 0 99px 99px; background: var(--accent); opacity: .72; }
        .metric-label { color: #646963; font-size: .75rem; font-weight: 680; }
        .metric-value { color: #242724; font-size: 1.75rem; font-weight: 740; margin-top: .42rem; line-height: 1; }
        .metric-note { color: #898d87; font-size: .68rem; margin-top: .5rem; }
        .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .7rem; margin-bottom: .9rem; }
        .group-card {
            border: 1px solid color-mix(in srgb, var(--accent) 24%, #dedfd8); border-radius: 18px; padding: .82rem .9rem;
            background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 9%, #fffefa), #fafaf6 78%);
            box-shadow: 0 10px 24px rgba(49,55,50,.08), 0 7px 18px color-mix(in srgb, var(--accent) 7%, transparent);
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
        button[kind="secondary"], .stDownloadButton button {
            color: #254f40 !important; background: #dff5ec !important; border: 1px solid #b9dfd0 !important;
            box-shadow: 0 5px 12px rgba(65,119,97,.10);
        }
        button[kind="secondary"]:hover, .stDownloadButton button:hover { background: #c8eddf !important; border-color: #83c8ad !important; }
        [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stTextInput input {
            color: #2b2e2a !important; background: #fffefa !important; border-color: #d5d8d1 !important;
            box-shadow: inset 0 0 0 1px rgba(121,185,157,.03), 0 5px 12px rgba(49,55,50,.05);
        }
        [data-baseweb="tab-list"] { gap: .28rem; background: #e4e5df; border: 1px solid #d3d5ce; padding: .3rem; border-radius: 999px; box-shadow: inset 0 2px 5px rgba(49,55,50,.06); }
        [data-baseweb="tab"] { color: #555a54; height: 38px; border-radius: 999px; padding: 0 .9rem; }
        [aria-selected="true"][data-baseweb="tab"] { color: #234c3d; background: #bcebd9; box-shadow: 0 4px 10px rgba(65,119,97,.14), inset 0 0 0 1px #9bd8c1; }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 1px solid #d8dad4; border-radius: 18px; overflow: hidden; box-shadow: var(--shadow); background: #fffefa; }
        details { border: 1px solid #d9dad4 !important; border-radius: 16px !important; background: #f8f7f2 !important; box-shadow: 0 7px 18px rgba(49,55,50,.06); }
        div[data-testid="stExpander"] > details p, div[data-testid="stExpander"] > details label,
        div[data-testid="stExpander"] > details span, div[data-testid="stExpander"] > details summary { color: #30332f !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color: #daddd6 !important; border-radius: 20px !important; background: #fffefa; box-shadow: var(--shadow); }
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
            st.dataframe(pd.DataFrame(exc.diagnostics), use_container_width=True, hide_index=True)
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
    backgrounds = {
        "Con checada": "background-color: rgba(118,154,144,.10)",
        "Sin checada": "background-color: rgba(183,117,97,.11)",
        "No encontrado / revisar": "background-color: rgba(180,147,94,.10)",
        "Ambiguo / revisar": "background-color: rgba(165,106,127,.12)",
    }
    style = backgrounds.get(state, "")
    return [style] * len(row)


with st.sidebar:
    st.markdown("### Apariencia")
    visual_theme = st.radio(
        "Tema visual",
        ["Oscuro guinda actual", "Product UI claro"],
        index=0,
        key="visual_theme",
    )
    st.caption(f"Dashboard de asistencia · v{APP_VERSION}")

if visual_theme == "Product UI claro":
    inject_product_ui_theme_css()
else:
    inject_dark_theme_css()

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
                compact_summary[visible_columns],
                use_container_width=True,
                hide_index=True,
                height=330,
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
        styled_query = display_query.style.apply(style_query_rows, axis=1)
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
        st.dataframe(problems, use_container_width=True, hide_index=True, height=470)

with tab_catalog:
    catalog_metrics = st.columns(5)
    catalog_metrics[0].metric("PAAE", int((catalog["tipo_personal"] == "PAAE").sum()))
    catalog_metrics[1].metric("Docentes", int((catalog["tipo_personal"] == "DOCENTE").sum()))
    catalog_metrics[2].metric("Matutino", int((catalog["turno"] == "MATUTINO").sum()))
    catalog_metrics[3].metric("Vespertino", int((catalog["turno"] == "VESPERTINO").sum()))
    catalog_metrics[4].metric("Revisar", int(diagnostics["sin_turno"]))
    st.dataframe(catalog, use_container_width=True, hide_index=True, height=390)
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
            st.dataframe(pd.DataFrame(pdf_diagnostics["errores"]), use_container_width=True, hide_index=True)
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
