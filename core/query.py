from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

import pandas as pd


def normalize_search(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in normalized if not unicodedata.combining(char)).upper()
    return re.sub(r"\s+", " ", text).strip()


def filter_results(
    results: pd.DataFrame,
    *,
    search: str = "",
    statuses: Iterable[str] | None = None,
    personnel_types: Iterable[str] | None = None,
    shifts: Iterable[str] | None = None,
    match_types: Iterable[str] | None = None,
) -> pd.DataFrame:
    filtered = results.copy()
    if filtered.empty:
        return filtered.reset_index(drop=True)

    def apply_values(column: str, selected: Iterable[str] | None) -> None:
        nonlocal filtered
        values = list(selected or [])
        if values and column in filtered.columns:
            filtered = filtered[filtered[column].astype(str).isin(values)]

    apply_values("estado", statuses)
    apply_values("tipo_personal", personnel_types)
    apply_values("turno", shifts)
    apply_values("coincidencia_por", match_types)

    term = normalize_search(search)
    if term:
        employee_ids = filtered.get("empleado_id", pd.Series("", index=filtered.index)).map(normalize_search)
        names = filtered.get("nombre_completo", pd.Series("", index=filtered.index)).map(normalize_search)
        filtered = filtered[employee_ids.str.contains(term, regex=False) | names.str.contains(term, regex=False)]

    return filtered.reset_index(drop=True)

