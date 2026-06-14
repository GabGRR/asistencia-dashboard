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


st.set_page_config(page_title="Dashboard de asistencia diaria", page_icon="✓", layout="wide")

APP_VERSION = "1.1.0"


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


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ipn: #6b1738;
            --ipn-soft: #a56a7f;
            --ink: #f3f1ed;
            --muted: #a5a4aa;
            --panel: #17181c;
            --panel-2: #1d1e23;
            --line: rgba(255,255,255,.08);
            --green: #83a98b;
            --amber: #c5a56b;
            --rose: #bd7d83;
            --blue: #829eb5;
        }
        .stApp { background: #101115; color: var(--ink); }
        .block-container { max-width: 1380px; padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stSidebar"] { background: #141519; border-right: 1px solid var(--line); }
        [data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
        [data-testid="stHeader"] { background: transparent; }
        #MainMenu, footer { visibility: hidden; }
        h1, h2, h3 { letter-spacing: -.025em; }
        .hero {
            position: relative; overflow: hidden; border: 1px solid var(--line);
            border-radius: 22px; padding: 1.25rem 1.4rem; margin-bottom: .85rem;
            background: linear-gradient(130deg, #1c1d22 0%, #17181c 65%, #21171c 100%);
            box-shadow: 0 18px 55px rgba(0,0,0,.18);
        }
        .hero:after {
            content: ""; position: absolute; width: 190px; height: 190px;
            border-radius: 50%; right: -70px; top: -105px;
            background: radial-gradient(circle, rgba(107,23,56,.48), rgba(107,23,56,0) 68%);
        }
        .hero-kicker { color: #c895a8; font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
        .hero-title { font-size: 1.75rem; font-weight: 720; margin: .2rem 0 .18rem; }
        .hero-subtitle { color: var(--muted); font-size: .92rem; margin: 0; }
        .hero-date { margin-top: .75rem; color: #ded9d5; font-size: .86rem; font-weight: 600; }
        .badge-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .85rem; }
        .badge {
            display: inline-flex; align-items: center; gap: .38rem; padding: .32rem .58rem;
            border-radius: 999px; background: rgba(255,255,255,.055); border: 1px solid var(--line);
            color: #d7d4d1; font-size: .72rem; font-weight: 650;
        }
        .badge-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px rgba(131,169,139,.10); }
        .badge.warn .badge-dot { background: var(--amber); }
        .badge.ipn { color: #e5bdcb; border-color: rgba(165,106,127,.35); background: rgba(107,23,56,.18); }
        .badge.ipn .badge-dot { background: #a56a7f; }
        .section-label { color: #d5d1ce; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin: .15rem 0 .65rem; }
        .metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .65rem; margin: .2rem 0 .9rem; }
        .metric-card {
            min-height: 112px; border: 1px solid var(--line); border-radius: 17px;
            padding: .9rem 1rem; background: var(--panel); position: relative; overflow: hidden;
        }
        .metric-card:before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--accent, #6b1738); opacity: .9; }
        .metric-label { color: var(--muted); font-size: .75rem; font-weight: 650; }
        .metric-value { font-size: 1.75rem; font-weight: 720; margin-top: .42rem; line-height: 1; }
        .metric-note { color: #8e8d93; font-size: .68rem; margin-top: .5rem; }
        .group-grid { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: .65rem; margin-bottom: .9rem; }
        .group-card { border: 1px solid var(--line); border-radius: 16px; padding: .82rem .9rem; background: var(--panel-2); }
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
        [data-testid="stFileUploaderDropzone"] { min-height: 68px; border-radius: 13px; background: #1b1c21; border-color: rgba(255,255,255,.09); padding: .55rem; }
        [data-testid="stFileUploaderDropzone"] small { display: none; }
        button[kind="secondary"], .stDownloadButton button { border-radius: 11px !important; border-color: rgba(255,255,255,.10) !important; }
        [data-baseweb="tab-list"] { gap: .3rem; background: #15161a; border: 1px solid var(--line); padding: .28rem; border-radius: 13px; }
        [data-baseweb="tab"] { height: 38px; border-radius: 9px; padding: 0 .82rem; }
        [aria-selected="true"][data-baseweb="tab"] { background: #25262c; }
        [data-baseweb="tab-highlight"] { display: none; }
        [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
        details { border: 1px solid var(--line) !important; border-radius: 13px !important; background: var(--panel) !important; }
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


def render_header(selected_date: str | None, catalog: pd.DataFrame, paae_ok: bool, docentes_ok: bool) -> None:
    date_text = format_date_with_weekday(selected_date) if selected_date else "Esperando reporte PDF"
    badges = "".join(
        [
            badge("IPN · corte operativo", ipn=True),
            badge(f"v{APP_VERSION}", ipn=True),
            badge("PAAE cargado" if paae_ok else "PAAE pendiente", paae_ok),
            badge("Docentes cargado" if docentes_ok else "Docentes pendiente", docentes_ok),
            badge(f"Catálogo {len(catalog):,}", not catalog.empty),
        ]
    )
    st.markdown(
        f"""
        <div class="hero">
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


inject_styles()

try:
    secrets = st.secrets
except Exception:
    secrets = None

paae_url = configured_catalog_url("PAAE_CATALOG_URL", secrets)
docentes_url = configured_catalog_url("DOCENTES_CATALOG_URL", secrets)

with st.sidebar:
    st.markdown("### Fuentes de personal")
    st.caption("Los catálogos remotos se usan automáticamente. Los archivos manuales sirven como respaldo.")
    with st.expander("Reemplazar catálogos", expanded=False):
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

    st.divider()
    st.caption("ESTADO")
    st.write(f"PAAE · **{len(paae_df) if paae_df is not None else 0}**")
    st.write(f"Docentes · **{len(docentes_df) if docentes_df is not None else 0}**")
    st.write(f"Catálogo unificado · **{len(catalog)}**")
    st.caption("Las URLs privadas permanecen ocultas.")
    st.caption(f"Versión {APP_VERSION}")

header_slot = st.empty()

st.markdown('<div class="section-label">Reporte del día</div>', unsafe_allow_html=True)
pdf_file = st.file_uploader(
    "Sube el Reporte de Tarjeta en PDF",
    type=["pdf"],
    help="Una página por empleado. El archivo se procesa en memoria.",
    label_visibility="visible",
)

parsed_pdf = None
selected_date = None
if pdf_file is not None and not catalog.empty:
    try:
        with st.spinner("Leyendo reporte..."):
            parsed_pdf = cached_parse_pdf(pdf_file.getvalue())
    except ValueError as exc:
        st.error(str(exc))
    except Exception:
        st.error("No fue posible procesar el PDF. Revisa su formato.")

if parsed_pdf is not None:
    dates = parsed_pdf["dates"]
    if not dates:
        st.error("No se detectaron fechas en el PDF. Consulta la pestaña Depuración.")
    elif len(dates) == 1:
        selected_date = dates[0]
    else:
        selected_date = st.selectbox(
            "Fecha del corte",
            dates,
            index=len(dates) - 1,
            format_func=format_date_with_weekday,
        )

with header_slot.container():
    render_header(
        selected_date,
        catalog,
        paae_df is not None and not paae_df.empty,
        docentes_df is not None and not docentes_df.empty,
    )

if catalog.empty:
    st.markdown(
        '<div class="empty-state"><strong>Catálogos pendientes</strong>'
        'Revisa las fuentes remotas o usa los reemplazos de la barra lateral.</div>',
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

tab_summary, tab_absent, tab_present, tab_problems, tab_catalog, tab_debug = st.tabs(
    ["Resumen", "Sin checada", "Presentes", "Problemas", "Catálogo", "Depuración"]
)

with tab_summary:
    left, right = st.columns([1.15, 1], gap="large")
    with left:
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
                color=["#83a98b", "#a56a7f"],
                height=300,
            )
    with right:
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
        visible_columns = ["Tipo", "Turno", "Total", "Con checada", "Sin checada", "%"]
        st.dataframe(compact_summary[visible_columns], use_container_width=True, hide_index=True, height=300)

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

with tab_absent:
    st.caption(f"{len(absent)} personas localizadas sin checada en {format_date_with_weekday(selected_date)}.")
    st.dataframe(absent, use_container_width=True, hide_index=True, height=470)

with tab_present:
    st.caption(f"{len(present)} personas con al menos una checada en {format_date_with_weekday(selected_date)}.")
    st.dataframe(present, use_container_width=True, hide_index=True, height=470)

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
