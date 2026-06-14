from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, time
from io import BytesIO
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd


CATALOG_COLUMNS = [
    "empleado_id",
    "nombre_completo",
    "apellido_paterno",
    "apellido_materno",
    "nombre",
    "tipo_personal",
    "turno",
    "hora_entrada",
    "hora_salida",
    "activo",
    "fuente",
]

DOCENTES_SHEET = "DOCENTES 2026-21"


def strip_accents(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_column(value: object) -> str:
    text = strip_accents(value).lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    raw = str(value).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return re.sub(r"\s+", "", raw)


def normalize_name(value: object) -> str:
    text = strip_accents(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_shift(value: object) -> str:
    key = normalize_name(value)
    if key in {"M", "MAT", "MATUTINO", "MANANA"} or "MATUT" in key:
        return "MATUTINO"
    if key in {"V", "VES", "VESPERTINO", "TARDE"} or "VESPERT" in key:
        return "VESPERTINO"
    return "SIN TURNO / REVISAR"


def normalize_time(value: object) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return ""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if 0 <= numeric < 1:
            total_minutes = round(numeric * 24 * 60)
            return f"{(total_minutes // 60) % 24:02d}:{total_minutes % 60:02d}"
    raw = clean_text(value)
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p"):
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            pass
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 3:
        digits = f"0{digits}"
    if len(digits) == 4:
        hour, minute = int(digits[:2]), int(digits[2:])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return ""


def infer_paae_shift(entry_time: object) -> str:
    normalized = normalize_time(entry_time)
    if not normalized:
        return "SIN TURNO / REVISAR"
    hour = int(normalized.split(":", maxsplit=1)[0])
    return "MATUTINO" if hour < 12 else "VESPERTINO"


def find_header_row(file_bytes: bytes, sheet_name: str, required: set[str], max_rows: int = 20) -> int:
    preview = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None, nrows=max_rows)
    for row_index, row in preview.iterrows():
        keys = {normalize_column(value) for value in row.tolist() if clean_text(value)}
        if required.issubset(keys):
            return int(row_index)
    raise ValueError(f"No se encontró el encabezado esperado en la hoja {sheet_name}.")


def read_sheet_with_detected_header(file_bytes: bytes, sheet_name: str, required: set[str]) -> pd.DataFrame:
    header_row = find_header_row(file_bytes, sheet_name, required)
    df = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=header_row)
    df.columns = [normalize_column(column) for column in df.columns]
    return df


def choose_paae_sheet(file_bytes: bytes) -> str:
    excel = pd.ExcelFile(BytesIO(file_bytes))
    preferred = [name for name in excel.sheet_names if normalize_column(name) in {"hoja1", "paae"}]
    candidates = preferred + [name for name in excel.sheet_names if name not in preferred]
    for sheet_name in candidates:
        try:
            find_header_row(file_bytes, sheet_name, {"id", "nombre"})
            return sheet_name
        except ValueError:
            continue
    raise ValueError("No se encontró una hoja PAAE con columnas ID y NOMBRE.")


def choose_docentes_sheet(file_bytes: bytes) -> str:
    excel = pd.ExcelFile(BytesIO(file_bytes))
    exact = [name for name in excel.sheet_names if normalize_name(name) == normalize_name(DOCENTES_SHEET)]
    if exact:
        return exact[0]
    for sheet_name in excel.sheet_names:
        try:
            find_header_row(file_bytes, sheet_name, {"no_empleado", "nombre", "turno"})
            return sheet_name
        except ValueError:
            continue
    raise ValueError(f"No se encontró la hoja {DOCENTES_SHEET} ni otra tabla docente compatible.")


def load_paae_catalog(file_bytes: bytes) -> pd.DataFrame:
    sheet_name = choose_paae_sheet(file_bytes)
    source = read_sheet_with_detected_header(file_bytes, sheet_name, {"id", "nombre"})
    records: list[dict[str, object]] = []
    for _, row in source.iterrows():
        employee_id = normalize_id(row.get("id"))
        first_name = normalize_name(row.get("nombre"))
        paternal = normalize_name(row.get("apellido_paterno"))
        maternal = normalize_name(row.get("apellido_materno"))
        if not employee_id and not any((first_name, paternal, maternal)):
            continue
        entry = normalize_time(row.get("hora_entrada"))
        records.append(
            {
                "empleado_id": employee_id,
                "nombre_completo": " ".join(part for part in (first_name, paternal, maternal) if part),
                "apellido_paterno": paternal,
                "apellido_materno": maternal,
                "nombre": first_name,
                "tipo_personal": "PAAE",
                "turno": infer_paae_shift(entry),
                "hora_entrada": entry,
                "hora_salida": normalize_time(row.get("hora_salida")),
                "activo": "SI",
                "fuente": "PAAE",
            }
        )
    return ensure_catalog_columns(pd.DataFrame(records))


def load_docentes_catalog(file_bytes: bytes) -> pd.DataFrame:
    sheet_name = choose_docentes_sheet(file_bytes)
    source = read_sheet_with_detected_header(file_bytes, sheet_name, {"no_empleado", "nombre", "turno"})
    records: list[dict[str, object]] = []
    for _, row in source.iterrows():
        employee_id = normalize_id(row.get("no_empleado"))
        first_name = normalize_name(row.get("nombre"))
        paternal = normalize_name(row.get("apellido_paterno"))
        maternal = normalize_name(row.get("apellido_materno"))
        if not employee_id and not any((first_name, paternal, maternal)):
            continue
        records.append(
            {
                "empleado_id": employee_id,
                "nombre_completo": " ".join(part for part in (first_name, paternal, maternal) if part),
                "apellido_paterno": paternal,
                "apellido_materno": maternal,
                "nombre": first_name,
                "tipo_personal": "DOCENTE",
                "turno": normalize_shift(row.get("turno")),
                "hora_entrada": "",
                "hora_salida": "",
                "activo": "SI",
                "fuente": "DOCENTES",
            }
        )
    return ensure_catalog_columns(pd.DataFrame(records))


def ensure_catalog_columns(df: pd.DataFrame | None) -> pd.DataFrame:
    result = pd.DataFrame() if df is None else df.copy()
    for column in CATALOG_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    return result[CATALOG_COLUMNS].fillna("")


def normalize_catalogs(paae_df: pd.DataFrame | None, docentes_df: pd.DataFrame | None) -> pd.DataFrame:
    frames = [ensure_catalog_columns(frame) for frame in (paae_df, docentes_df) if frame is not None and not frame.empty]
    if not frames:
        return ensure_catalog_columns(None)
    return pd.concat(frames, ignore_index=True)[CATALOG_COLUMNS].fillna("")


def catalog_diagnostics(catalog: pd.DataFrame, paae_count: int = 0, docentes_count: int = 0) -> dict[str, object]:
    normalized = ensure_catalog_columns(catalog)
    ids = normalized["empleado_id"].astype(str).str.strip()
    names = normalized["nombre_completo"].astype(str).str.strip()
    shifts = normalized["turno"].astype(str).str.upper()
    duplicate_mask = ids.ne("") & ids.duplicated(keep=False)
    return {
        "registros_paae": int(paae_count),
        "registros_docentes": int(docentes_count),
        "catalogo_unificado": int(len(normalized)),
        "duplicados_empleado_id": int(ids[duplicate_mask].nunique()),
        "ids_duplicados": sorted(ids[duplicate_mask].unique().tolist()),
        "sin_turno": int(shifts.isin(["", "SIN TURNO", "REVISAR", "SIN TURNO / REVISAR"]).sum()),
        "sin_empleado_id": int(ids.eq("").sum()),
        "sin_nombre": int(names.eq("").sum()),
    }


def build_catalog_result(paae_df: pd.DataFrame | None, docentes_df: pd.DataFrame | None) -> dict[str, object]:
    paae = ensure_catalog_columns(paae_df)
    docentes = ensure_catalog_columns(docentes_df)
    catalog = normalize_catalogs(paae, docentes)
    issues = catalog[
        catalog["empleado_id"].astype(str).str.strip().eq("")
        | catalog["nombre_completo"].astype(str).str.strip().eq("")
        | catalog["turno"].isin(["", "SIN TURNO / REVISAR"])
    ].copy()
    diagnostics = catalog_diagnostics(catalog, len(paae), len(docentes))
    diagnostics["total_activos"] = int(len(catalog))
    diagnostics["total_leidos"] = int(len(catalog))
    diagnostics["hojas"] = [
        {"fuente": "PAAE", "filas": len(paae)},
        {"fuente": "DOCENTES", "filas": len(docentes), "hoja": DOCENTES_SHEET},
    ]
    return {
        "employees": catalog.reset_index(drop=True),
        "all_employees": catalog.reset_index(drop=True),
        "issues": issues.reset_index(drop=True),
        "diagnostics": diagnostics,
    }


def read_catalog(excel_bytes: bytes) -> dict[str, object]:
    """Compatibilidad con el flujo anterior de un solo Excel."""
    errors: list[str] = []
    paae: pd.DataFrame | None = None
    docentes: pd.DataFrame | None = None
    try:
        paae = load_paae_catalog(excel_bytes)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        docentes = load_docentes_catalog(excel_bytes)
    except ValueError as exc:
        errors.append(str(exc))
    if (paae is None or paae.empty) and (docentes is None or docentes.empty):
        raise ValueError("No se pudo reconocer un catálogo PAAE o Docentes. " + " ".join(errors))
    return build_catalog_result(paae, docentes)


def _remote_url_candidates(url: str) -> list[str]:
    original = str(url or "").strip()
    if not original:
        return []
    candidates = [original]
    host = urlsplit(original).netloc.lower()
    if "sharepoint.com" in host or "onedrive" in host:
        parts = urlsplit(original)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["download"] = "1"
        direct = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        if direct not in candidates:
            candidates.append(direct)
    return candidates


def load_catalog_from_url(url: str) -> tuple[bytes | None, str | None, dict[str, object]]:
    diagnostic: dict[str, object] = {
        "configurada": bool(str(url or "").strip()),
        "status_http": None,
        "content_type": "",
        "bytes": 0,
        "intentos": 0,
    }
    if not diagnostic["configurada"]:
        return None, "URL no configurada.", diagnostic
    try:
        import requests

        for candidate in _remote_url_candidates(url):
            diagnostic["intentos"] = int(diagnostic["intentos"]) + 1
            response = requests.get(
                candidate,
                timeout=30,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 CatalogDashboard/1.0"},
            )
            payload = response.content
            diagnostic.update(
                {
                    "status_http": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "bytes": len(payload),
                }
            )
            if not response.ok or not payload.startswith(b"PK"):
                continue
            try:
                pd.ExcelFile(BytesIO(payload))
            except Exception:
                continue
            return payload, None, diagnostic
        return None, "La fuente remota no devolvió un archivo Excel XLSX válido.", diagnostic
    except Exception as exc:
        return None, f"No se pudo cargar el catálogo remoto ({type(exc).__name__}).", diagnostic


def configured_catalog_url(name: str, secrets: Any | None = None) -> str:
    if secrets is not None:
        try:
            secret_value = secrets.get(name)
            if secret_value:
                return str(secret_value).strip()
        except Exception:
            pass
    return str(os.getenv(name, "")).strip()
