from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import fitz


DATE_PATTERN = r"\d{1,2}/\d{1,2}/\d{4}"
DATE_RE = re.compile(DATE_PATTERN)
TIME_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:a|p)\.?\s*m\.?", re.IGNORECASE)
DAY_NAMES = {"lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"}


@dataclass(frozen=True)
class PdfLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


def strip_accents(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_id(value: object) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return re.sub(r"\s+", "", raw)


def normalize_name(value: object) -> str:
    text = strip_accents(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_date(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%d/%m/%Y")
    return parsed.strftime("%d/%m/%Y")


def sort_dates(values: Iterable[str]) -> list[str]:
    return sorted(set(values), key=lambda value: datetime.strptime(value, "%d/%m/%Y"))


def get_page_lines(page: fitz.Page) -> list[PdfLine]:
    grouped: dict[tuple[int, int], list[tuple]] = {}
    for item in page.get_text("words"):
        grouped.setdefault((int(item[5]), int(item[6])), []).append(item)

    lines: list[PdfLine] = []
    for words in grouped.values():
        ordered = sorted(words, key=lambda item: (float(item[0]), int(item[7])))
        text = " ".join(str(item[4]) for item in ordered).strip()
        if text:
            lines.append(
                PdfLine(
                    text=text,
                    x0=min(float(item[0]) for item in ordered),
                    y0=min(float(item[1]) for item in ordered),
                    x1=max(float(item[2]) for item in ordered),
                    y1=max(float(item[3]) for item in ordered),
                )
            )
    return sorted(lines, key=lambda line: (round(line.y0, 1), line.x0))


def extract_employee_identity(lines: list[str]) -> tuple[str, str]:
    for index in range(max(0, len(lines) - 1)):
        employee_id = lines[index].strip()
        employee_name = lines[index + 1].strip()
        if re.fullmatch(r"\d{1,10}", employee_id) and is_probable_name(employee_name):
            return normalize_id(employee_id), re.sub(r"\s+", " ", employee_name).strip()

    for line in lines:
        if is_ignored_identity_line(line):
            continue
        match = re.match(
            r"^\s*(?P<id>\d{1,10})\s+(?P<name>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.'\- ]{5,}?)(?:\s+\d{1,10})?\s*$",
            line,
        )
        if match:
            return normalize_id(match.group("id")), re.sub(r"\s+", " ", match.group("name")).strip()
    return "", ""


def is_probable_name(value: str) -> bool:
    key = normalize_name(value)
    forbidden = ("REPORTE", "PAGINA", "DESDE", "HASTA", "DEPARTAMENTO", "PUESTO")
    return len(key) >= 6 and any(char.isalpha() for char in key) and not any(word in key for word in forbidden)


def is_ignored_identity_line(value: str) -> bool:
    key = normalize_name(value)
    return any(
        word in key
        for word in (
            "REPORTE DE TARJETA",
            "DESDE",
            "HASTA",
            "LUNES",
            "MARTES",
            "MIERCOLES",
            "JUEVES",
            "VIERNES",
            "SABADO",
            "DOMINGO",
        )
    )


def extract_rows_from_text(lines: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in lines:
        date_match = DATE_RE.search(line)
        if not date_match:
            continue
        prefix = normalize_name(line[: date_match.start()]).lower()
        if prefix and not any(day in prefix for day in DAY_NAMES):
            continue
        date_value = normalize_date(date_match.group(0))
        checks = TIME_RE.findall(line[date_match.end() :])
        rows.append({"fecha": date_value, "checadas": checks, "linea_original": line})
    return unique_rows(rows)


def extract_rows_from_positioned_lines(lines: list[PdfLine]) -> list[dict[str, object]]:
    date_lines = [line for line in lines if re.fullmatch(DATE_PATTERN, line.text.strip())]
    if not date_lines:
        return []

    rows: list[dict[str, object]] = []
    for date_line in sorted(date_lines, key=lambda item: item.x0):
        same_column = [line for line in lines if abs(line.x0 - date_line.x0) <= 1.5]
        column_text = " ".join(line.text for line in sorted(same_column, key=lambda item: item.y0, reverse=True))
        normalized_column = normalize_name(column_text).lower()
        if not any(day in normalized_column for day in DAY_NAMES):
            continue
        rows.append(
            {
                "fecha": normalize_date(date_line.text),
                "checadas": TIME_RE.findall(column_text),
                "linea_original": column_text,
            }
        )
    return unique_rows(rows)


def unique_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_date: dict[str, dict[str, object]] = {}
    for row in rows:
        date_value = str(row["fecha"])
        current = by_date.get(date_value)
        if current is None or len(row.get("checadas", [])) > len(current.get("checadas", [])):
            by_date[date_value] = row
    return [by_date[date_value] for date_value in sort_dates(by_date)]


def parse_page(page: fitz.Page, page_number: int) -> dict[str, object]:
    text = page.get_text("text")
    text_lines = [line.strip() for line in text.splitlines() if line.strip()]
    positioned_lines = get_page_lines(page)
    employee_id, name = extract_employee_identity(text_lines)
    positioned_rows = extract_rows_from_positioned_lines(positioned_lines)
    rows = positioned_rows or extract_rows_from_text(text_lines)
    return {
        "pagina_pdf": page_number,
        "empleado_id": employee_id,
        "nombre": name,
        "nombre_normalizado": normalize_name(name),
        "registros": rows,
    }


def parse_pdf(pdf_bytes: bytes) -> dict[str, object]:
    pages: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    dates: set[str] = set()

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError("No se pudo abrir el PDF. Verifica que no esté dañado o protegido.") from exc

    try:
        for page_index in range(document.page_count):
            try:
                parsed = parse_page(document.load_page(page_index), page_index + 1)
                pages.append(parsed)
                dates.update(str(row["fecha"]) for row in parsed["registros"])
                if not parsed["empleado_id"] and not parsed["nombre"]:
                    errors.append({"pagina_pdf": page_index + 1, "error": "No se detectó ID ni nombre."})
                if not parsed["registros"]:
                    errors.append({"pagina_pdf": page_index + 1, "error": "No se detectaron filas con fecha."})
            except Exception as exc:
                errors.append({"pagina_pdf": page_index + 1, "error": f"Error de parseo: {type(exc).__name__}"})
    finally:
        document.close()

    return {
        "pages": pages,
        "dates": sort_dates(dates),
        "diagnostics": {
            "paginas_leidas": len(pages),
            "empleados_detectados": sum(bool(page["empleado_id"] or page["nombre"]) for page in pages),
            "errores": errors,
        },
    }
