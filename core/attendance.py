from __future__ import annotations

from typing import Any

import pandas as pd

from core.catalog import normalize_id, normalize_name


STATUS_WITH_CHECK = "CON_CHECADA"
STATUS_WITHOUT_CHECK = "SIN_CHECADA"
STATUS_NOT_FOUND = "NO_ENCONTRADO_EN_PDF"
STATUS_AMBIGUOUS = "AMBIGUO"


RESULT_COLUMNS = [
    "empleado_id",
    "nombre_completo",
    "tipo_personal",
    "turno",
    "estado",
    "tiene_checada",
    "checadas",
    "pagina_pdf",
    "coincidencia_por",
    "detalle",
]


def page_checks_for_date(page: dict[str, Any], selected_date: str) -> list[str] | None:
    for record in page.get("registros", []):
        if str(record.get("fecha")) == selected_date:
            return [str(check) for check in record.get("checadas", [])]
    return None


def build_indexes(pages: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        employee_id = normalize_id(page.get("empleado_id"))
        name = normalize_name(page.get("nombre"))
        if employee_id:
            by_id.setdefault(employee_id, []).append(page)
        if name:
            by_name.setdefault(name, []).append(page)
    return by_id, by_name


def match_page(employee: pd.Series, by_id: dict, by_name: dict) -> tuple[list[dict[str, Any]], str]:
    employee_id = normalize_id(employee.get("empleado_id"))
    name = normalize_name(employee.get("nombre_completo"))
    if employee_id and employee_id in by_id:
        return by_id[employee_id], "ID"
    if name and name in by_name:
        return by_name[name], "NOMBRE"
    return [], ""


def analyze_attendance(catalog: pd.DataFrame, pages: list[dict[str, Any]], selected_date: str) -> dict[str, object]:
    by_id, by_name = build_indexes(pages)
    rows: list[dict[str, object]] = []
    matched_page_numbers: set[int] = set()
    duplicate_ids = set(catalog.loc[catalog["empleado_id"].astype(str).ne("") & catalog["empleado_id"].duplicated(False), "empleado_id"].astype(str))
    duplicate_names = set(catalog.loc[catalog["nombre_completo"].map(normalize_name).ne("") & catalog["nombre_completo"].map(normalize_name).duplicated(False), "nombre_completo"].map(normalize_name))

    for _, employee in catalog.iterrows():
        base = {
            "empleado_id": employee.get("empleado_id", ""),
            "nombre_completo": employee.get("nombre_completo", ""),
            "tipo_personal": employee.get("tipo_personal", ""),
            "turno": employee.get("turno", ""),
        }
        employee_id = normalize_id(employee.get("empleado_id"))
        normalized_name = normalize_name(employee.get("nombre_completo"))
        if employee_id in duplicate_ids or (not employee_id and normalized_name in duplicate_names):
            rows.append({**base, "estado": STATUS_AMBIGUOUS, "tiene_checada": False, "checadas": "", "pagina_pdf": "", "coincidencia_por": "CATÁLOGO", "detalle": "ID o nombre duplicado entre personas activas del catálogo."})
            continue

        matches, match_type = match_page(employee, by_id, by_name)
        if not matches:
            rows.append({**base, "estado": STATUS_NOT_FOUND, "tiene_checada": False, "checadas": "", "pagina_pdf": "", "coincidencia_por": "", "detalle": "La persona activa no apareció en el PDF."})
            continue
        if len(matches) > 1:
            rows.append({**base, "estado": STATUS_AMBIGUOUS, "tiene_checada": False, "checadas": "", "pagina_pdf": ", ".join(str(page.get("pagina_pdf", "")) for page in matches), "coincidencia_por": match_type, "detalle": "Más de una página del PDF coincide con esta persona."})
            continue

        page = matches[0]
        matched_page_numbers.add(int(page.get("pagina_pdf", 0)))
        checks = page_checks_for_date(page, selected_date)
        has_check = bool(checks)
        detail = "" if checks is not None else "La persona apareció en el PDF, pero la fecha seleccionada no apareció en su página."
        rows.append(
            {
                **base,
                "estado": STATUS_WITH_CHECK if has_check else STATUS_WITHOUT_CHECK,
                "tiene_checada": has_check,
                "checadas": ", ".join(checks or []),
                "pagina_pdf": page.get("pagina_pdf", ""),
                "coincidencia_por": match_type,
                "detalle": detail,
            }
        )

    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    pdf_only = []
    for page in pages:
        page_number = int(page.get("pagina_pdf", 0))
        if page_number not in matched_page_numbers:
            pdf_only.append(
                {
                    "pagina_pdf": page_number,
                    "empleado_id": page.get("empleado_id", ""),
                    "nombre": page.get("nombre", ""),
                    "problema": "Persona del PDF no cruzada de forma única con el catálogo.",
                }
            )

    return {
        "results": result,
        "summary": summarize(result),
        "group_summary": summarize_groups(result),
        "pdf_only": pd.DataFrame(pdf_only),
    }


def summarize(result: pd.DataFrame) -> dict[str, float | int]:
    total = len(result)
    with_check = int((result["estado"] == STATUS_WITH_CHECK).sum()) if not result.empty else 0
    without_check = int((result["estado"] == STATUS_WITHOUT_CHECK).sum()) if not result.empty else 0
    not_found = int((result["estado"] == STATUS_NOT_FOUND).sum()) if not result.empty else 0
    ambiguous = int((result["estado"] == STATUS_AMBIGUOUS).sum()) if not result.empty else 0
    percentage = (with_check / total * 100) if total else 0.0
    return {"total_esperado": total, "con_checada": with_check, "sin_checada": without_check, "no_encontrados": not_found, "ambiguos": ambiguous, "porcentaje_asistencia": percentage}


def summarize_groups(result: pd.DataFrame) -> pd.DataFrame:
    columns = ["tipo_personal", "turno", "total_esperado", "con_checada", "sin_checada", "no_encontrados", "ambiguos", "porcentaje_asistencia"]
    if result.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for (personnel_type, shift), group in result.groupby(["tipo_personal", "turno"], dropna=False):
        values = summarize(group)
        rows.append({"tipo_personal": personnel_type or "SIN CLASIFICAR", "turno": shift or "SIN CLASIFICAR", **values})
    return pd.DataFrame(rows, columns=columns).sort_values(["tipo_personal", "turno"]).reset_index(drop=True)
