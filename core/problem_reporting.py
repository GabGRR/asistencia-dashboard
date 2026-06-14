from __future__ import annotations

from typing import Any

import pandas as pd


PROBLEM_COLUMNS = [
    "fuente",
    "tipo_problema",
    "empleado_id",
    "nombre_completo",
    "tipo_personal",
    "turno",
    "detalle",
]


def _as_dataframe(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
    elif isinstance(value, dict):
        try:
            frame = pd.DataFrame(value)
        except ValueError:
            frame = pd.DataFrame([value])
    elif isinstance(value, (list, tuple)):
        frame = pd.DataFrame(list(value))
    else:
        return pd.DataFrame()
    frame = frame.loc[:, ~frame.columns.astype(str).duplicated()].copy()
    frame.columns = [str(column) for column in frame.columns]
    return frame.reset_index(drop=True)


def _series(frame: pd.DataFrame, *candidates: str, default: str = "") -> pd.Series:
    for candidate in candidates:
        if candidate in frame.columns:
            value = frame[candidate]
            if isinstance(value, pd.DataFrame):
                value = value.iloc[:, 0]
            return value.fillna("").astype(str)
    return pd.Series([default] * len(frame), index=frame.index, dtype="object")


def _standardize(
    value: Any,
    *,
    source: str,
    default_type: str,
    default_detail: str,
) -> pd.DataFrame:
    frame = _as_dataframe(value)
    if frame.empty:
        return pd.DataFrame(columns=PROBLEM_COLUMNS)
    standardized = pd.DataFrame(index=frame.index)
    standardized["fuente"] = _series(frame, "fuente", "origen", default=source).replace("", source)
    standardized["tipo_problema"] = _series(
        frame, "tipo_problema", "estado", default=default_type
    ).replace("", default_type)
    standardized["empleado_id"] = _series(frame, "empleado_id", "id")
    standardized["nombre_completo"] = _series(frame, "nombre_completo", "nombre")
    standardized["tipo_personal"] = _series(frame, "tipo_personal")
    standardized["turno"] = _series(frame, "turno")
    standardized["detalle"] = _series(
        frame, "detalle", "problema", "error", default=default_detail
    ).replace("", default_detail)
    return standardized[PROBLEM_COLUMNS].reset_index(drop=True)


def build_problems_table(
    results: Any,
    pdf_only: Any,
    catalog_issues: Any,
    problem_statuses: set[str] | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    result_frame = _as_dataframe(results)
    if not result_frame.empty and "estado" in result_frame.columns:
        statuses = problem_statuses or set()
        if statuses:
            result_frame = result_frame[result_frame["estado"].isin(statuses)].reset_index(drop=True)
        if not result_frame.empty:
            frames.append(
                _standardize(
                    result_frame,
                    source="CATÁLOGO",
                    default_type="PROBLEMA_DE_CRUCE",
                    default_detail="La persona no pudo cruzarse de forma única.",
                )
            )

    pdf_frame = _standardize(
        pdf_only,
        source="PDF",
        default_type="PERSONA_PDF_NO_CRUZADA",
        default_detail="Persona del PDF no cruzada con el catálogo.",
    )
    if not pdf_frame.empty:
        frames.append(pdf_frame)

    catalog_frame = _standardize(
        catalog_issues,
        source="CATÁLOGO",
        default_type="DATO_DE_CATÁLOGO_INCOMPLETO",
        default_detail="Falta ID, nombre o turno en el catálogo.",
    )
    if not catalog_frame.empty:
        frames.append(catalog_frame)

    usable = [frame[PROBLEM_COLUMNS].reset_index(drop=True) for frame in frames if not frame.empty]
    if not usable:
        return pd.DataFrame(columns=PROBLEM_COLUMNS)
    combined = pd.concat(usable, ignore_index=True, sort=False)
    combined = combined.loc[:, ~combined.columns.duplicated()].reset_index(drop=True)
    return combined[PROBLEM_COLUMNS].fillna("").drop_duplicates(ignore_index=True)
