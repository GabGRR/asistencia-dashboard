from __future__ import annotations

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
from core.pdf_daily_parser import parse_pdf
from core.problem_reporting import build_problems_table


st.set_page_config(page_title="Dashboard de asistencia diaria", page_icon="✓", layout="wide")


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


def group_label(row: pd.Series) -> str:
    return f"{row.get('tipo_personal', '')} {row.get('turno', '')}".strip().title()


def display_group_cards(group_summary: pd.DataFrame) -> None:
    expected_groups = [
        ("PAAE", "MATUTINO"),
        ("PAAE", "VESPERTINO"),
        ("PAAE", "SIN TURNO / REVISAR"),
        ("DOCENTE", "MATUTINO"),
        ("DOCENTE", "VESPERTINO"),
        ("DOCENTE", "SIN TURNO / REVISAR"),
    ]
    columns = st.columns(3)
    for index, (personnel_type, shift) in enumerate(expected_groups):
        container = columns[index % 3]
        match = group_summary[
            (group_summary["tipo_personal"] == personnel_type) & (group_summary["turno"] == shift)
        ]
        if match.empty:
            total = present = absent = 0
        else:
            row = match.iloc[0]
            total = int(row["total_esperado"])
            present = int(row["con_checada"])
            absent = int(row["sin_checada"])
        label_shift = "Sin turno/Revisar" if shift == "SIN TURNO / REVISAR" else shift.title()
        container.metric(
            f"{personnel_type.title()} {label_shift}",
            f"{present} de {total}",
            f"{absent} sin checada",
            delta_color="inverse",
        )


def problems_table(results, pdf_only, catalog_issues) -> pd.DataFrame:
    return build_problems_table(
        results,
        pdf_only,
        catalog_issues,
        problem_statuses={STATUS_NOT_FOUND, STATUS_AMBIGUOUS},
    )


def secure_remote_status(label: str, error: str | None, diagnostic: dict[str, object]) -> None:
    if not diagnostic.get("configurada"):
        return
    if error:
        st.warning(
            f"{label}: no se pudo cargar la fuente remota. "
            f"HTTP: {diagnostic.get('status_http') or 'sin respuesta'}; usa el uploader como respaldo."
        )
    else:
        st.success(f"{label}: catálogo remoto cargado correctamente.")


def load_catalog_source(
    uploaded_file,
    remote_url: str,
    loader,
    label: str,
) -> tuple[pd.DataFrame | None, dict[str, object]]:
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
        secure_remote_status(label, error, remote_diagnostic)
    if payload is None:
        return None, diagnostic
    try:
        return loader(payload), diagnostic
    except ValueError as exc:
        diagnostic["error"] = str(exc)
        st.error(f"{label}: {exc}")
        if isinstance(exc, CatalogFormatError) and exc.diagnostics:
            with st.expander(f"Diagnóstico de hojas de {label}", expanded=False):
                st.dataframe(pd.DataFrame(exc.diagnostics), use_container_width=True, hide_index=True)
    except Exception as exc:
        diagnostic["error"] = type(exc).__name__
        st.error(f"{label}: no fue posible leer el archivo.")
    return None, diagnostic


st.title("Dashboard de asistencia diaria")
st.caption("Cruza un Reporte de Tarjeta con catálogos PAAE y Docentes. Los archivos se procesan en memoria.")

try:
    secrets = st.secrets
except Exception:
    secrets = None

paae_url = configured_catalog_url("PAAE_CATALOG_URL", secrets)
docentes_url = configured_catalog_url("DOCENTES_CATALOG_URL", secrets)

with st.container(border=True):
    st.subheader("Catálogos")
    catalog_columns = st.columns(2)
    with catalog_columns[0]:
        paae_file = st.file_uploader(
            "Subir Excel PAAE",
            type=["xlsx", "xls"],
            key="paae_catalog_upload",
            help="El archivo subido reemplaza la URL PAAE durante esta sesión.",
        )
        if paae_url and paae_file is None:
            st.caption("Fuente remota PAAE configurada. La URL permanece oculta.")
    with catalog_columns[1]:
        docentes_file = st.file_uploader(
            "Subir Excel Docentes",
            type=["xlsx", "xls"],
            key="docentes_catalog_upload",
            help=f"Se leerá la hoja { 'DOCENTES 2026-21' }.",
        )
        if docentes_url and docentes_file is None:
            st.caption("Fuente remota Docentes configurada. La URL permanece oculta.")

    paae_df, paae_source_diagnostic = load_catalog_source(
        paae_file,
        paae_url,
        cached_load_paae,
        "PAAE",
    )
    docentes_df, docentes_source_diagnostic = load_catalog_source(
        docentes_file,
        docentes_url,
        cached_load_docentes,
        "Docentes",
    )
    catalog_data = build_catalog_result(paae_df, docentes_df)
    catalog = catalog_data["employees"]
    diagnostics = catalog_data["diagnostics"]

    if catalog.empty:
        st.info("Sube al menos uno de los dos catálogos o configura sus URLs remotas.")
    else:
        metric_columns = st.columns(5)
        metric_columns[0].metric("Total PAAE", int((catalog["tipo_personal"] == "PAAE").sum()))
        metric_columns[1].metric("Total Docentes", int((catalog["tipo_personal"] == "DOCENTE").sum()))
        metric_columns[2].metric("Total Matutino", int((catalog["turno"] == "MATUTINO").sum()))
        metric_columns[3].metric("Total Vespertino", int((catalog["turno"] == "VESPERTINO").sum()))
        metric_columns[4].metric("Sin turno/Revisar", int(diagnostics["sin_turno"]))

        with st.expander("Vista previa del catálogo unificado", expanded=False):
            st.dataframe(catalog, use_container_width=True, hide_index=True, height=360)
            st.download_button(
                "Descargar catálogo unificado CSV",
                dataframe_to_csv_bytes(catalog),
                "catalogo_unificado.csv",
                "text/csv",
                use_container_width=True,
            )

        with st.expander("Depuración de catálogos", expanded=False):
            st.json(
                {
                    "registros_leidos_paae": diagnostics["registros_paae"],
                    "registros_leidos_docentes": diagnostics["registros_docentes"],
                    "catalogo_unificado": diagnostics["catalogo_unificado"],
                    "duplicados_por_empleado_id": diagnostics["duplicados_empleado_id"],
                    "ids_duplicados": diagnostics["ids_duplicados"],
                    "sin_turno": diagnostics["sin_turno"],
                    "sin_empleado_id": diagnostics["sin_empleado_id"],
                    "sin_nombre": diagnostics["sin_nombre"],
                    "fuente_paae": paae_source_diagnostic["origen"],
                    "fuente_docentes": docentes_source_diagnostic["origen"],
                }
            )

st.subheader("Reporte de checadas")
pdf_file = st.file_uploader("Sube el PDF", type=["pdf"], help="Una página por empleado.")

if catalog.empty or pdf_file is None:
    st.info("Carga al menos un catálogo y el PDF para generar el análisis.")
    st.stop()

try:
    with st.spinner("Leyendo PDF..."):
        parsed_pdf = cached_parse_pdf(pdf_file.getvalue())
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception:
    st.error("No fue posible procesar el PDF. Revisa su formato.")
    st.stop()

dates = parsed_pdf["dates"]
if not dates:
    st.error("No se detectaron fechas en el PDF. Consulta el panel de depuración.")
    selected_date = None
elif len(dates) == 1:
    selected_date = dates[0]
    st.success(f"Fecha detectada automáticamente: {selected_date}")
else:
    selected_date = st.selectbox("Selecciona la fecha a analizar", dates, index=len(dates) - 1)
    st.caption(f"Se detectaron {len(dates)} fechas en el PDF.")

if selected_date:
    analysis = analyze_attendance(catalog, parsed_pdf["pages"], selected_date)
    results = analysis["results"]
    summary = analysis["summary"]
    group_summary = analysis["group_summary"]
    present = results[results["estado"] == STATUS_WITH_CHECK].copy()
    absent = results[results["estado"] == STATUS_WITHOUT_CHECK].copy()
    problems = problems_table(results, analysis["pdf_only"], catalog_data["issues"])

    st.subheader(f"Asistencia del {selected_date}")
    metrics = st.columns(5)
    metrics[0].metric("Total esperado", int(summary["total_esperado"]))
    metrics[1].metric("Con checada", int(summary["con_checada"]))
    metrics[2].metric("Sin checada", int(summary["sin_checada"]))
    metrics[3].metric("No encontrados", int(summary["no_encontrados"]))
    metrics[4].metric("% asistencia", f"{summary['porcentaje_asistencia']:.1f}%")
    if summary["ambiguos"]:
        st.warning(f"Hay {summary['ambiguos']} coincidencia(s) ambigua(s) que requieren revisión.")

    st.subheader("Resumen por tipo y turno")
    display_group_cards(group_summary)
    st.dataframe(group_summary, use_container_width=True, hide_index=True)

    chart_data = group_summary.copy()
    if not chart_data.empty:
        chart_data["grupo"] = chart_data.apply(group_label, axis=1)
        st.bar_chart(chart_data.set_index("grupo")[["con_checada", "sin_checada"]], color=["#16825D", "#D95D39"])

    filter_col1, filter_col2 = st.columns(2)
    type_options = sorted(value for value in results["tipo_personal"].dropna().unique() if value)
    shift_options = sorted(value for value in results["turno"].dropna().unique() if value)
    selected_types = filter_col1.multiselect("Filtrar tipo de personal", type_options, default=type_options)
    selected_shifts = filter_col2.multiselect("Filtrar turno", shift_options, default=shift_options)
    filtered = results[results["tipo_personal"].isin(selected_types) & results["turno"].isin(selected_shifts)]

    tab_present, tab_absent, tab_problems = st.tabs(["Con checada", "Sin checada", "Problemas de cruce"])
    with tab_present:
        st.dataframe(filtered[filtered["estado"] == STATUS_WITH_CHECK], use_container_width=True, hide_index=True)
    with tab_absent:
        st.dataframe(filtered[filtered["estado"] == STATUS_WITHOUT_CHECK], use_container_width=True, hide_index=True)
    with tab_problems:
        if problems.empty:
            st.success("No se detectaron problemas de cruce.")
        else:
            st.dataframe(problems, use_container_width=True, hide_index=True)

    st.subheader("Descargas")
    excel_bytes = build_excel_report(summary, group_summary, present, absent, problems)
    download_columns = st.columns(4)
    download_columns[0].download_button(
        "Reporte completo Excel",
        excel_bytes,
        f"asistencia_{selected_date.replace('/', '-')}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    download_columns[1].download_button("Presentes CSV", dataframe_to_csv_bytes(present), "presentes.csv", "text/csv", use_container_width=True)
    download_columns[2].download_button("Sin checada CSV", dataframe_to_csv_bytes(absent), "sin_checada.csv", "text/csv", use_container_width=True)
    download_columns[3].download_button("Problemas CSV", dataframe_to_csv_bytes(problems), "problemas_cruce.csv", "text/csv", use_container_width=True)

with st.expander("Depuración del PDF", expanded=False):
    pdf_diagnostics = parsed_pdf["diagnostics"]
    st.write(
        {
            "páginas_leídas": pdf_diagnostics["paginas_leidas"],
            "empleados_detectados_pdf": pdf_diagnostics["empleados_detectados"],
            "fechas_detectadas": parsed_pdf["dates"],
            "empleados_activos_catálogo": diagnostics["total_activos"],
            "errores_parseo": len(pdf_diagnostics["errores"]),
        }
    )
    if pdf_diagnostics["errores"]:
        st.dataframe(pd.DataFrame(pdf_diagnostics["errores"]), use_container_width=True, hide_index=True)
