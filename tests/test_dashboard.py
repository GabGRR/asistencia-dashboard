from __future__ import annotations

import unittest
from io import BytesIO

import fitz
import pandas as pd

from core.attendance import (
    STATUS_AMBIGUOUS,
    STATUS_NOT_FOUND,
    STATUS_WITH_CHECK,
    STATUS_WITHOUT_CHECK,
    analyze_attendance,
)
from core.catalog import (
    DOCENTES_SHEET,
    build_catalog_result,
    infer_paae_shift,
    load_docentes_catalog,
    load_paae_catalog,
    normalize_catalogs,
)
from core.pdf_daily_parser import extract_rows_from_text, format_date_with_weekday, parse_pdf
from core.problem_reporting import PROBLEM_COLUMNS, build_problems_table
from core.query import filter_results


class PdfParserTests(unittest.TestCase):
    def test_date_label_includes_weekday(self) -> None:
        self.assertEqual(format_date_with_weekday("23/05/2026"), "Sábado 23/05/2026")

    def test_single_date_with_check(self) -> None:
        rows = extract_rows_from_text(["Lunes 08/06/2026 07:01:00 a. m. 15:02:00 p. m."])
        self.assertEqual([row["fecha"] for row in rows], ["08/06/2026"])
        self.assertEqual(len(rows[0]["checadas"]), 2)

    def test_multiple_dates_and_empty_row(self) -> None:
        rows = extract_rows_from_text(
            [
                "Lunes 08/06/2026 07:01:00 a. m.",
                "Martes 09/06/2026",
            ]
        )
        self.assertEqual([row["fecha"] for row in rows], ["08/06/2026", "09/06/2026"])
        self.assertEqual(rows[1]["checadas"], [])

    def test_pdf_is_parsed_from_memory(self) -> None:
        document = fitz.open()
        page = document.new_page()
        lines = [
            "Reporte de Tarjeta",
            "101",
            "PERSONA DE PRUEBA",
            "Lunes 08/06/2026 07:01:00 a. m.",
            "Martes 09/06/2026",
        ]
        for index, line in enumerate(lines):
            page.insert_text((72, 72 + index * 20), line)
        pdf_bytes = document.tobytes()
        document.close()

        parsed = parse_pdf(pdf_bytes)
        self.assertEqual(parsed["dates"], ["08/06/2026", "09/06/2026"])
        self.assertEqual(parsed["pages"][0]["empleado_id"], "101")


class CatalogTests(unittest.TestCase):
    @staticmethod
    def build_paae_workbook() -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {"No.": "", "APELLIDO \nPATERNO": "", "APELLIDO \nMATERNO": "", "NOMBRE": "", "ID": "", "HORA ENTRADA": "", "HORA SALIDA": ""},
                    {"No.": 1, "APELLIDO \nPATERNO": "Pérez", "APELLIDO \nMATERNO": "López", "NOMBRE": "Ana", "ID": 101, "HORA ENTRADA": "07:00", "HORA SALIDA": "14:00"},
                    {"No.": 2, "APELLIDO \nPATERNO": "Ruiz", "APELLIDO \nMATERNO": "Díaz", "NOMBRE": "Luis", "ID": 102, "HORA ENTRADA": "15:30", "HORA SALIDA": "21:30"},
                    {"No.": 3, "APELLIDO \nPATERNO": "Sin", "APELLIDO \nMATERNO": "Turno", "NOMBRE": "Persona", "ID": "", "HORA ENTRADA": "", "HORA SALIDA": ""},
                ]
            ).to_excel(writer, sheet_name="Hoja1", index=False)
        return output.getvalue()

    @staticmethod
    def build_docentes_workbook() -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {"No.": 1, "APELLIDO PATERNO": "García", "APELLIDO MATERNO": "Núñez", "NOMBRE    ": "María", "No. \nEMPLEADO": 201, "TURNO": "MATUTINO", "RFC": "FICTICIO"},
                    {"No.": 2, "APELLIDO PATERNO": "Torres", "APELLIDO MATERNO": "Vega", "NOMBRE    ": "Carlos", "No. \nEMPLEADO": 202, "TURNO": "VESPERTINO", "RFC": "FICTICIO"},
                    {"No.": 3, "APELLIDO PATERNO": "Revisar", "APELLIDO MATERNO": "Turno", "NOMBRE    ": "Docente", "No. \nEMPLEADO": 203, "TURNO": "", "RFC": "FICTICIO"},
                ]
            ).to_excel(writer, sheet_name=DOCENTES_SHEET, index=False, startrow=7)
        return output.getvalue()

    def test_load_paae_current_format_and_infer_shift(self) -> None:
        catalog = load_paae_catalog(self.build_paae_workbook())
        self.assertEqual(len(catalog), 3)
        self.assertEqual(catalog.loc[catalog["empleado_id"] == "101", "turno"].iloc[0], "MATUTINO")
        self.assertEqual(catalog.loc[catalog["empleado_id"] == "102", "turno"].iloc[0], "VESPERTINO")
        self.assertEqual(catalog.iloc[0]["nombre_completo"], "ANA PEREZ LOPEZ")
        self.assertEqual(catalog.iloc[0]["tipo_personal"], "PAAE")

    def test_load_docentes_from_real_sheet_layout(self) -> None:
        catalog = load_docentes_catalog(self.build_docentes_workbook())
        self.assertEqual(len(catalog), 3)
        self.assertEqual(catalog.iloc[0]["empleado_id"], "201")
        self.assertEqual(catalog.iloc[0]["nombre_completo"], "MARIA GARCIA NUNEZ")
        self.assertEqual(catalog.iloc[0]["tipo_personal"], "DOCENTE")
        self.assertEqual(catalog.iloc[1]["turno"], "VESPERTINO")
        self.assertEqual(catalog.iloc[0]["hora_entrada"], "")

    def test_load_docentes_from_catalogo_normalizado(self) -> None:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {
                        "empleado_id": 301,
                        "nombre_completo": "Docente Normalizado Uno",
                        "tipo_personal": "DOCENTE",
                        "turno": "Matutino",
                        "activo": "SI",
                    }
                ]
            ).to_excel(writer, sheet_name="Catalogo_normalizado", index=False)
            pd.DataFrame([{"dato": "no usar"}]).to_excel(writer, sheet_name="Hoja1", index=False)
        catalog = load_docentes_catalog(output.getvalue())
        self.assertEqual(catalog.iloc[0]["empleado_id"], "301")
        self.assertEqual(catalog.iloc[0]["nombre_completo"], "DOCENTE NORMALIZADO UNO")
        self.assertEqual(catalog.iloc[0]["turno"], "MATUTINO")
        self.assertEqual(catalog.attrs["hoja_detectada"], "Catalogo_normalizado")

    def test_load_docentes_from_hoja1_paae_style(self) -> None:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(
                [
                    {
                        "ID": 302,
                        "APELLIDO PATERNO": "Prueba",
                        "APELLIDO MATERNO": "Docente",
                        "NOMBRE": "Persona",
                        "TURNO": "Vespertino",
                        "HORA ENTRADA": "14:00",
                        "HORA SALIDA": "20:00",
                    }
                ]
            ).to_excel(writer, sheet_name="Hoja1", index=False)
        catalog = load_docentes_catalog(output.getvalue())
        self.assertEqual(catalog.iloc[0]["empleado_id"], "302")
        self.assertEqual(catalog.iloc[0]["tipo_personal"], "DOCENTE")
        self.assertEqual(catalog.iloc[0]["turno"], "VESPERTINO")
        self.assertEqual(catalog.iloc[0]["hora_entrada"], "14:00")
        self.assertEqual(catalog.attrs["hoja_detectada"], "Hoja1")

    def test_unify_catalogs_and_report_missing_data(self) -> None:
        paae = load_paae_catalog(self.build_paae_workbook())
        docentes = load_docentes_catalog(self.build_docentes_workbook())
        unified = normalize_catalogs(paae, docentes)
        result = build_catalog_result(paae, docentes)
        self.assertEqual(len(unified), 6)
        self.assertEqual(set(unified["tipo_personal"]), {"PAAE", "DOCENTE"})
        self.assertEqual(result["diagnostics"]["sin_empleado_id"], 1)
        self.assertEqual(result["diagnostics"]["sin_turno"], 2)

    def test_infer_paae_shift_boundaries(self) -> None:
        self.assertEqual(infer_paae_shift("07:00"), "MATUTINO")
        self.assertEqual(infer_paae_shift("12:00"), "VESPERTINO")
        self.assertEqual(infer_paae_shift(""), "SIN TURNO / REVISAR")


class AttendanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pd.DataFrame(
            [
                {"empleado_id": "1", "nombre_completo": "Uno PAAE", "tipo_personal": "PAAE", "turno": "MATUTINO"},
                {"empleado_id": "2", "nombre_completo": "Dos PAAE", "tipo_personal": "PAAE", "turno": "VESPERTINO"},
                {"empleado_id": "3", "nombre_completo": "Tres Docente", "tipo_personal": "DOCENTE", "turno": "MATUTINO"},
                {"empleado_id": "4", "nombre_completo": "Cuatro Docente", "tipo_personal": "DOCENTE", "turno": "VESPERTINO"},
            ]
        )
        self.pages = [
            {"pagina_pdf": 1, "empleado_id": "1", "nombre": "Uno PAAE", "registros": [{"fecha": "08/06/2026", "checadas": ["07:00 a. m."]}]},
            {"pagina_pdf": 2, "empleado_id": "2", "nombre": "Dos PAAE", "registros": [{"fecha": "08/06/2026", "checadas": []}]},
            {"pagina_pdf": 3, "empleado_id": "3", "nombre": "Tres Docente", "registros": [{"fecha": "08/06/2026", "checadas": ["08:00 a. m."]}]},
            {"pagina_pdf": 9, "empleado_id": "99", "nombre": "Fuera Catalogo", "registros": [{"fecha": "08/06/2026", "checadas": ["08:00 a. m."]}]},
        ]

    def test_attendance_states_and_four_groups(self) -> None:
        analysis = analyze_attendance(self.catalog, self.pages, "08/06/2026")
        result = analysis["results"].set_index("empleado_id")
        self.assertEqual(result.loc["1", "estado"], STATUS_WITH_CHECK)
        self.assertEqual(result.loc["2", "estado"], STATUS_WITHOUT_CHECK)
        self.assertEqual(result.loc["4", "estado"], STATUS_NOT_FOUND)
        self.assertEqual(len(analysis["group_summary"]), 4)
        self.assertEqual(len(analysis["pdf_only"]), 1)
        self.assertEqual(analysis["summary"]["porcentaje_asistencia"], 50.0)

    def test_duplicate_catalog_id_is_ambiguous(self) -> None:
        duplicated = pd.concat([self.catalog.iloc[[0]], self.catalog.iloc[[0]]], ignore_index=True)
        analysis = analyze_attendance(duplicated, self.pages, "08/06/2026")
        self.assertTrue((analysis["results"]["estado"] == STATUS_AMBIGUOUS).all())


class ProblemsTableTests(unittest.TestCase):
    def test_empty_inputs_return_standard_columns(self) -> None:
        result = build_problems_table(None, [], {})
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), PROBLEM_COLUMNS)

    def test_duplicate_columns_do_not_raise_invalid_index(self) -> None:
        frame = pd.DataFrame([["1", "Uno", "Uno duplicado", STATUS_NOT_FOUND]], columns=[
            "empleado_id", "nombre_completo", "nombre_completo", "estado"
        ])
        result = build_problems_table(frame, None, None, {STATUS_NOT_FOUND, STATUS_AMBIGUOUS})
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["empleado_id"], "1")

    def test_issues_accept_list_dict_and_dataframe(self) -> None:
        variants = [
            [{"empleado_id": "2", "nombre_completo": "Dos"}],
            {"empleado_id": "2", "nombre_completo": "Dos"},
            pd.DataFrame([{"empleado_id": "2", "nombre_completo": "Dos"}]),
        ]
        for issues in variants:
            with self.subTest(kind=type(issues).__name__):
                result = build_problems_table(pd.DataFrame(), pd.DataFrame(), issues)
                self.assertEqual(len(result), 1)
                self.assertEqual(list(result.columns), PROBLEM_COLUMNS)

    def test_mixed_frame_shapes_are_normalized(self) -> None:
        results = pd.DataFrame([{"estado": STATUS_NOT_FOUND, "id": "3", "nombre": "Tres"}])
        pdf_only = [{"empleado_id": "4", "nombre": "Cuatro", "problema": "No cruzado"}]
        issues = {"empleado_id": "5", "nombre_completo": "Cinco", "turno": ""}
        result = build_problems_table(results, pdf_only, issues, {STATUS_NOT_FOUND})
        self.assertEqual(len(result), 3)
        self.assertEqual(list(result.columns), PROBLEM_COLUMNS)


class QueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = pd.DataFrame(
            [
                {"empleado_id": "101", "nombre_completo": "María Pérez", "tipo_personal": "PAAE", "turno": "MATUTINO", "estado": STATUS_WITH_CHECK, "coincidencia_por": "ID"},
                {"empleado_id": "202", "nombre_completo": "Carlos López", "tipo_personal": "DOCENTE", "turno": "VESPERTINO", "estado": STATUS_WITHOUT_CHECK, "coincidencia_por": "NOMBRE"},
                {"empleado_id": "303", "nombre_completo": "Persona Mixta", "tipo_personal": "DOCENTE", "turno": "MIXTO", "estado": STATUS_NOT_FOUND, "coincidencia_por": ""},
            ]
        )

    def test_search_ignores_accents_and_accepts_id(self) -> None:
        self.assertEqual(filter_results(self.results, search="maria").iloc[0]["empleado_id"], "101")
        self.assertEqual(filter_results(self.results, search="202").iloc[0]["nombre_completo"], "Carlos López")

    def test_combined_filters_include_real_mixed_shift(self) -> None:
        filtered = filter_results(
            self.results,
            statuses=[STATUS_NOT_FOUND],
            personnel_types=["DOCENTE"],
            shifts=["MIXTO"],
        )
        self.assertEqual(filtered["empleado_id"].tolist(), ["303"])

if __name__ == "__main__":
    unittest.main()
