"""Ekspor hasil ke Excel: Peringkat emiten, Berita (dengan tautan), Riwayat rating, Info."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HDR = PatternFill("solid", fgColor="1F3A5F")
WARNA_LABEL = {"Positif": "E3F4E8", "Negatif": "FBE4E4", "Netral": "F1F3F5"}


def _tulis(ws, df: pd.DataFrame, lebar: dict | None = None, link_col: str | None = None):
    cols = list(df.columns)
    for j, c in enumerate(cols, start=1):
        x = ws.cell(1, j, c)
        x.font = Font(bold=True, color="FFFFFF", name="Calibri")
        x.fill = HDR
        x.alignment = Alignment(vertical="center", wrap_text=True)
    for i, row in enumerate(df.itertuples(index=False), start=2):
        for j, v in enumerate(row, start=1):
            if v is not None and not isinstance(v, str) and pd.isna(v):
                v = None
            if isinstance(v, pd.Timestamp):
                v = (v.tz_convert("Asia/Jakarta").tz_localize(None) if v.tzinfo else v).floor("s").to_pydatetime()
            c = ws.cell(i, j, v)
            if isinstance(v, datetime):
                c.number_format = "dd/mm/yyyy hh:mm" if (v.hour or v.minute) else "dd/mm/yyyy"
    if link_col and link_col in cols:
        jl = cols.index(link_col) + 1
        jj = cols.index("Judul") + 1 if "Judul" in cols else jl
        for i in range(2, len(df) + 2):
            url = ws.cell(i, jl).value
            if url:
                ws.cell(i, jj).hyperlink = url
                ws.cell(i, jj).font = Font(color="1F5FAD", underline="single")
    for j, c in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(j)].width = (lebar or {}).get(c, min(max(len(c) + 2, 10), 40))
    ws.freeze_panes = "B2"
    if len(df):
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(df) + 1}"


def buat_excel(peringkat: pd.DataFrame, berita: pd.DataFrame, rating: pd.DataFrame, info: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Peringkat"
    kol = ["#", "Emiten", "Kode", "Sektor", "Rating", "Lembaga", "Outlook", "Tgl Rating", "Perubahan",
           "Rating Sebelumnya", "Tgl Perubahan", "Skor", "Kategori", "Tren", "Keyakinan", "Risiko", "Peristiwa",
           "Berita", "Positif", "Netral", "Negatif", "Pendorong negatif", "Pendorong positif", "Sinyal",
           "Berita terbaru", "Tgl berita terbaru"]
    pk = peringkat.reindex(columns=kol).copy()
    for c in ("Skor", "Tren"):
        pk[c] = pd.to_numeric(pk[c], errors="coerce").round(1)
    pk = pk.rename(columns={"Skor": "Skor 0–100", "Tren": "Δ vs 7 hari lalu", "Berita": "Artikel",
                            "Positif": "Peristiwa positif", "Netral": "Peristiwa netral", "Negatif": "Peristiwa negatif"})
    _tulis(ws, pk, {"Emiten": 32, "Sektor": 20, "Sinyal": 42, "Berita terbaru": 70, "Pendorong negatif": 30,
                    "Pendorong positif": 30, "Tgl Rating": 12, "Tgl Perubahan": 12, "Tgl berita terbaru": 16})
    info = {**info, "Skala skor": "Sentiment Score 0–100 berbasis peristiwa unik (sama dengan Overview): 50 = netral, "
                                  "<40 negatif, >60 positif; '—' bila peristiwa unik < 3."}
    if len(pk):
        j = kol.index("Skor") + 1
        col = get_column_letter(j)
        ws.conditional_formatting.add(f"{col}2:{col}{len(pk) + 1}", ColorScaleRule(
            start_type="num", start_value=20, start_color="E06666", mid_type="num", mid_value=50,
            mid_color="FFFFFF", end_type="num", end_value=80, end_color="6FA8DC"))
        for i, p in enumerate(pk["Perubahan"], start=2):
            c = ws.cell(i, kol.index("Perubahan") + 1)
            if p == "Naik":
                c.fill = PatternFill("solid", fgColor="D9EAD3")
            elif p == "Turun":
                c.fill = PatternFill("solid", fgColor="F4CCCC")

    wb2 = wb.create_sheet("Berita")
    kb = {"emiten": "Emiten", "terbit": "Terbit (WIB)", "judul": "Judul", "label": "Sentimen", "skor": "Skor",
          "pendorong": "Pendorong", "alasan": "Alasan", "sumber": "Sumber", "cakupan": "Cakupan", "bahasa": "Bahasa",
          "kanal": "Kanal", "relevansi": "Relevansi", "mesin": "Mesin", "url": "URL"}
    b = berita.reindex(columns=list(kb)).rename(columns=kb)
    _tulis(wb2, b, {"Emiten": 28, "Terbit (WIB)": 16, "Judul": 80, "Pendorong": 24, "Alasan": 34, "Sumber": 22,
                    "Kanal": 22, "URL": 40, "Mesin": 16}, link_col="URL")
    js = list(b.columns).index("Sentimen") + 1
    for i, v in enumerate(b["Sentimen"], start=2):
        if v in WARNA_LABEL:
            wb2.cell(i, js).fill = PatternFill("solid", fgColor=WARNA_LABEL[v])

    wr = wb.create_sheet("Riwayat Rating")
    _tulis(wr, rating.sort_values(["Nama", "Tanggal"], ascending=[True, False]),
           {"Nama": 32, "Keterangan": 70, "Sumber": 40, "Tanggal": 12})

    wi = wb.create_sheet("Info")
    for i, (k, v) in enumerate(info.items(), start=1):
        wi.cell(i, 1, k).font = Font(bold=True)
        wi.cell(i, 2, str(v))
    wi.column_dimensions["A"].width = 30
    wi.column_dimensions["B"].width = 100
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
