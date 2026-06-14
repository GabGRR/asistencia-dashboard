from __future__ import annotations

from io import BytesIO

import pandas as pd


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def build_excel_report(
    general_summary: dict[str, object],
    group_summary: pd.DataFrame,
    present: pd.DataFrame,
    absent: pd.DataFrame,
    problems: pd.DataFrame,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([general_summary]).to_excel(writer, sheet_name="Resumen general", index=False)
        group_summary.to_excel(writer, sheet_name="Resumen grupos", index=False)
        present.to_excel(writer, sheet_name="Con checada", index=False)
        absent.to_excel(writer, sheet_name="Sin checada", index=False)
        problems.to_excel(writer, sheet_name="Problemas cruce", index=False)
    output.seek(0)
    return output.getvalue()

