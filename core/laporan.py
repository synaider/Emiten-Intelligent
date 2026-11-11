"""
AI Research Report: laporan emiten berbahasa Indonesia (PDF & Excel) dengan referensi bernomor dan periode analisis.
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl import Workbook

from .ekspor import _tulis

DISCLAIMER = ("Laporan ini disusun otomatis dari berita & dokumen publik yang dikumpulkan aplikasi. Bukan rekomendasi "
              "beli/jual dan bukan prediksi harga. Verifikasi informasi penting ke sumber resmi (IDX, OJK, emiten).")


def _tgl(t, jam: bool = False) -> str:
    bln = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    if t is None or (not isinstance(t, str) and pd.isna(t)):
        return "-"
    t = pd.Timestamp(t)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Jakarta")
    return f"{t.day} {bln[t.month - 1]} {t.year}" + (f" {t:%H:%M}" if jam else "")


def skenario_aturan(ev: pd.DataFrame, radar: pd.DataFrame | None) -> list[str]:
    """Skenario dampak kualitatif tanpa AI, dari pendorong peristiwa & faktor global."""
    e = ev[ev["relasi"] != "Tidak langsung"] if not ev.empty else ev
    pos = e[e["dampak"] >= 0.15].groupby("pendorong")["w"].sum().sort_values(ascending=False) if not e.empty else []
    neg = e[e["dampak"] <= -0.15].groupby("pendorong")["w"].sum().sort_values(ascending=False) if not e.empty else []
    out = []
    if len(pos):
        out.append(f"Skenario positif: pendorong {', '.join(pos.index[:2]).lower()} berlanjut dan dikonfirmasi data "
                   "resmi (laporan keuangan/keterbukaan informasi).")
    out.append("Skenario dasar: tidak ada peristiwa material baru; sentimen bergerak mengikuti rilis kinerja & faktor "
               "makro.")
    if len(neg):
        out.append(f"Skenario negatif: isu {', '.join(neg.index[:2]).lower()} membesar atau terkonfirmasi resmi, "
                   "berpotensi menekan " + ", ".join(dict.fromkeys(
                       a.strip() for v in e[e["dampak"] <= -0.15]["aspek"] for a in str(v).split(",") if a.strip()
                   )).lower()[:80] + ".")
    if radar is not None and not radar.empty:
        r = radar[radar["Peristiwa"] > 0]
        rug = r[r["Dampak emiten"] == "Merugikan"]
        if not rug.empty:
            out.append("Faktor eksternal yang perlu dipantau: " + ", ".join(rug["Faktor"]) + ".")
    return out


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------
def _font():
    """Daftarkan font Unicode bila ada (DejaVu di Linux, Arial di Windows); jika tidak, Helvetica."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    kandidat = [("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
                ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
                ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
                ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")]
    for reg, bold in kandidat:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("UI", reg))
                pdfmetrics.registerFont(TTFont("UI-Bold", bold))
                from reportlab.pdfbase.pdfmetrics import registerFontFamily
                registerFontFamily("UI", normal="UI", bold="UI-Bold", italic="UI", boldItalic="UI-Bold")
                return "UI", "UI-Bold", True
            except Exception:  # noqa: BLE001
                continue
    return "Helvetica", "Helvetica-Bold", False


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


def _bersih(t: str, unicode_ok: bool) -> str:
    t = _EMOJI.sub("", str(t or ""))
    if not unicode_ok:
        t = (t.replace("→", "->").replace("−", "-").replace("≥", ">=").replace("≤", "<=").replace("▲", "^")
             .replace("▼", "v").replace("■", "-").replace("“", '"').replace("”", '"').replace("’", "'"))
    return t


def _md(t: str, uok: bool) -> str:
    """Markdown sederhana → markup Paragraph reportlab."""
    t = html.escape(_bersih(t, uok))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#1f5fae">\1</link>', t)
    return t


def buat_pdf(info: dict, ev: pd.DataFrame, ref: list[dict], radar: pd.DataFrame | None = None,
             narasi: str = "", skenario: list[str] | None = None, pasar: dict | None = None) -> bytes:
    """info: nama, kode, entitas, sektor, periode, dari, sampai, skor, band, keyakinan, keyakinan_label, cakupan,
    kesegaran, risiko, risiko_alasan (list), n_peristiwa, n_artikel, positif, negatif, netral, mesin."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    f, fb, uok = _font()
    gaya = {
        "judul": ParagraphStyle("j", fontName=fb, fontSize=17, leading=21, textColor=colors.HexColor("#1b2a41")),
        "sub": ParagraphStyle("s", fontName=f, fontSize=9, leading=12, textColor=colors.HexColor("#5b6472")),
        "h2": ParagraphStyle("h", fontName=fb, fontSize=12, leading=15, spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#1b2a41")),
        "p": ParagraphStyle("p", fontName=f, fontSize=9.2, leading=13, alignment=TA_LEFT),
        "li": ParagraphStyle("l", fontName=f, fontSize=9.2, leading=13, leftIndent=10, bulletIndent=2),
        "kecil": ParagraphStyle("k", fontName=f, fontSize=7.8, leading=10, textColor=colors.HexColor("#3c4450")),
        "sel": ParagraphStyle("c", fontName=f, fontSize=7.8, leading=9.6),
        "selb": ParagraphStyle("cb", fontName=fb, fontSize=7.8, leading=9.6, textColor=colors.white),
    }
    P = lambda t, g="p": Paragraph(_md(t, uok), gaya[g])  # noqa: E731
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Laporan {info.get('nama')}", author="Emiten Intelligence")
    W = A4[0] - 32 * mm
    el = [P(f"Laporan Riset Emiten — {info.get('nama')}" + (f" ({info['kode']})" if info.get("kode") else ""),
            "judul"),
          Spacer(1, 3),
          P(f"{info.get('entitas') or ''} · Sektor {info.get('sektor') or '-'} · Periode analisis: "
            f"**{info.get('periode')}** ({_tgl(info.get('dari'))} – {_tgl(info.get('sampai'))}) · Dibuat "
            f"{_tgl(pd.Timestamp.now(tz='Asia/Jakarta'), True)} WIB", "sub"),
          Spacer(1, 8)]

    def tabel(data, lebar, header=True, zebra=True):
        t = Table(data, colWidths=lebar, repeatRows=1 if header else 0)
        st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
              ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9dde3"))]
        if header:
            st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")))
        if zebra:
            for i in range(1 if header else 0, len(data)):
                if i % 2 == 0:
                    st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f7fa")))
        t.setStyle(TableStyle(st))
        return t

    s = info.get("skor")
    kpi = [
        ("Skor sentimen", f"{s:.0f}/100 — {info.get('band')}" if s is not None else "Data tidak mencukupi"),
        ("Keyakinan", f"{info.get('keyakinan_label')} ({info['keyakinan']:.0f}/100)"
         if info.get("keyakinan") is not None else "—"),
        ("Tingkat risiko pemberitaan", info.get("risiko") or "—"),
        ("Peristiwa unik / artikel", f"{info.get('n_peristiwa', 0)} / {info.get('n_artikel', 0)}"),
        ("Komposisi (peristiwa)", f"{info.get('positif', 0)} positif · {info.get('netral', 0)} netral · "
                                  f"{info.get('negatif', 0)} negatif"),
        ("Cakupan sumber", info.get("cakupan") or "—"),
        ("Kesegaran data", info.get("kesegaran") or "—"),
        ("Mesin sentimen", info.get("mesin") or "—"),
    ]
    if pasar:
        kpi.append(("Data pasar", f"Harga {pasar.get('harga', 0):,.0f} · return periode "
                                  f"{pasar.get('return', 0):+.1%} · volatilitas "
                                  + (f"{pasar['volatilitas']:.0%}" if pasar.get("volatilitas") else "-")))
    el.append(tabel([[Paragraph(f"<b>{_md(k, uok)}</b>", gaya["sel"]), Paragraph(_md(v, uok), gaya["sel"])]
                     for k, v in kpi], [W * 0.3, W * 0.7], header=False))
    el.append(Spacer(1, 4))
    el.append(P("Skor 0–100: 50 + 50 × Σ(w·s)/Σw per peristiwa unik; w = relevansi × materialitas × kualitas bukti "
                "× kebaruan. 0 sangat negatif · 50 netral · 100 sangat positif.", "kecil"))

    if narasi:
        if not narasi.lstrip().startswith("#"):
            el.append(P("Ringkasan", "h2"))
        for blok in narasi.strip().split("\n"):
            b = blok.strip()
            if not b:
                continue
            if b.startswith("#"):
                el.append(P(b.lstrip("# ").strip(), "h2"))
            elif b[:2] in ("- ", "* ", "• "):
                el.append(Paragraph(_md(b[2:], uok), gaya["li"], bulletText="•"))
            else:
                el.append(P(b))
    el.append(P("Faktor risiko", "h2"))
    for a in info.get("risiko_alasan") or []:
        el.append(Paragraph(_md(a, uok), gaya["li"], bulletText="•"))
    if skenario:
        el.append(P("Skenario dampak (kualitatif)", "h2"))
        for a in skenario:
            el.append(Paragraph(_md(a, uok), gaya["li"], bulletText="•"))

    if not ev.empty:
        el.append(P("Peristiwa terpenting", "h2"))
        top = ev[ev["relasi"] != "Tidak langsung"].sort_values("w", ascending=False).head(14)
        no = {r["judul"]: r["no"] for r in ref}
        data = [[Paragraph(h, gaya["selb"]) for h in ("Tanggal", "Peristiwa", "Sumber", "Sentimen teks",
                                                      "Dampak emiten", "Verifikasi")]]
        for _, r in top.iterrows():
            n = no.get(r["judul"])
            data.append([Paragraph(_tgl(r["terbit"]), gaya["sel"]),
                         Paragraph(_md(f"{r['judul']}" + (f" [{n}]" if n else ""), uok), gaya["sel"]),
                         Paragraph(_md(f"{r['sumber']}" + (f" +{r['n_sumber'] - 1}" if r["n_sumber"] > 1 else ""),
                                       uok), gaya["sel"]),
                         Paragraph(r["label"], gaya["sel"]), Paragraph(_md(r["dampak_label"], uok), gaya["sel"]),
                         Paragraph(_md(r["konfirmasi"], uok), gaya["sel"])])
        el.append(tabel(data, [W * 0.1, W * 0.35, W * 0.13, W * 0.1, W * 0.16, W * 0.16]))

    if radar is not None and not radar.empty:
        judul_radar = P("Global & Domestic Impact Radar", "h2")
        data = [[Paragraph(h, gaya["selb"]) for h in ("Faktor", "Sensitivitas", "Arah terbaru", "Dampak emiten",
                                                      "Mekanisme")]]
        for _, r in radar.iterrows():
            data.append([Paragraph(_md(r["Faktor"], uok), gaya["sel"]), Paragraph(_md(r["Sensitivitas"], uok),
                                                                                gaya["sel"]),
                         Paragraph(_md(r["Arah terbaru"], uok), gaya["sel"]),
                         Paragraph(_md(r["Dampak emiten"], uok), gaya["sel"]),
                         Paragraph(_md(r["Mekanisme"], uok), gaya["sel"])])
        el.append(KeepTogether([judul_radar, tabel(data, [W * 0.18, W * 0.15, W * 0.14, W * 0.14, W * 0.39])]))

    if ref:
        el.append(P("Referensi", "h2"))
        for r in ref:
            el.append(Paragraph(f"[{r['no']}] " + _md(f"{r['judul']} — {r['sumber']}, {r['tanggal']}. ", uok)
                                + f'<link href="{html.escape(r["url"])}" color="#1f5fae">'
                                  f'{html.escape(r["url"][:110])}</link>', gaya["kecil"]))
    el.append(Spacer(1, 8))
    el.append(KeepTogether([P(DISCLAIMER, "kecil")]))

    def kaki(c, d):
        c.saveState()
        c.setFont(f, 7)
        c.setFillColor(colors.HexColor("#7a8290"))
        c.drawString(16 * mm, 8 * mm, _bersih(f"Emiten Intelligence · {info.get('nama')} · {info.get('periode')}",
                                              uok))
        c.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Hal. {d.page}")
        c.restoreState()
    doc.build(el, onFirstPage=kaki, onLaterPages=kaki)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------------
def buat_excel(info: dict, ev: pd.DataFrame, berita: pd.DataFrame, ref: list[dict], radar: pd.DataFrame | None,
               alerts: pd.DataFrame | None, narasi: str = "", skenario: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ringkasan"
    s = info.get("skor")
    rows = [("Emiten", info.get("nama")), ("Kode", info.get("kode")), ("Entitas", info.get("entitas")),
            ("Sektor", info.get("sektor")), ("Periode analisis", info.get("periode")),
            ("Dari", _tgl(info.get("dari"))), ("Sampai", _tgl(info.get("sampai"))),
            ("Skor sentimen (0–100)", round(s, 1) if s is not None else "Data tidak mencukupi"),
            ("Kategori skor", info.get("band")), ("Keyakinan", f"{info.get('keyakinan_label')} "
                                                               f"({info.get('keyakinan') or 0:.0f}/100)"),
            ("Tingkat risiko", info.get("risiko")), ("Alasan risiko", "; ".join(info.get("risiko_alasan") or [])),
            ("Peristiwa unik", info.get("n_peristiwa")), ("Artikel", info.get("n_artikel")),
            ("Cakupan sumber", info.get("cakupan")), ("Kesegaran", info.get("kesegaran")),
            ("Mesin sentimen", info.get("mesin")), ("Dibuat", datetime.now().strftime("%d/%m/%Y %H:%M")),
            ("Ringkasan", re.sub(r"\*\*", "", narasi or "")), ("Skenario", "\n".join(skenario or [])),
            ("Catatan", DISCLAIMER)]
    _tulis(ws, pd.DataFrame(rows, columns=["Item", "Nilai"]), {"Item": 26, "Nilai": 110})
    from openpyxl.styles import Alignment
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    if not ev.empty:
        e = ev.copy()
        e["Sumber lain"] = e["sumber_list"].map(lambda xs: "; ".join(f"{a} ({c})" for a, _, c in xs[1:]))
        e = e.rename(columns={"terbit": "Tanggal", "judul": "Judul", "sumber": "Sumber", "relasi": "Relasi",
                              "label": "Sentimen teks", "skor": "Skor teks", "dampak_label": "Dampak emiten",
                              "dampak": "Skor dampak", "pendorong": "Kategori", "aspek": "Aspek", "M": "Materialitas",
                              "Q": "Kualitas bukti", "D": "Kebaruan", "w": "Bobot", "konfirmasi": "Verifikasi",
                              "n_sumber": "Jumlah sumber", "penjelasan": "Penjelasan", "faktor": "Faktor",
                              "url": "URL"})
        kol = ["Tanggal", "Judul", "Sumber", "Jumlah sumber", "Verifikasi", "Relasi", "Kategori", "Faktor",
               "Sentimen teks", "Skor teks", "Dampak emiten", "Skor dampak", "Aspek", "Materialitas",
               "Kualitas bukti", "Kebaruan", "Bobot", "Penjelasan", "Sumber lain", "URL"]
        for c in ("Bobot", "Kebaruan"):
            e[c] = e[c].astype(float).round(3)
        _tulis(wb.create_sheet("Peristiwa"), e[kol], {"Judul": 70, "Penjelasan": 60, "Sumber lain": 40, "URL": 40},
               link_col="URL")
    if berita is not None and not berita.empty:
        b = berita.rename(columns={"terbit": "Tanggal", "judul": "Judul", "sumber": "Sumber", "cakupan": "Cakupan",
                                   "relasi": "Relasi", "label": "Sentimen", "skor": "Skor", "dampak_label": "Dampak",
                                   "pendorong": "Kategori", "verifikasi": "Verifikasi", "kanal": "Kanal",
                                   "url": "URL"})
        kol = [c for c in ["Tanggal", "Judul", "Sumber", "Cakupan", "Relasi", "Verifikasi", "Kategori", "Sentimen",
                           "Skor", "Dampak", "Kanal", "URL"] if c in b.columns]
        _tulis(wb.create_sheet("Berita"), b[kol], {"Judul": 70, "URL": 40}, link_col="URL")
    if radar is not None and not radar.empty:
        _tulis(wb.create_sheet("Faktor Global"), radar.rename(columns={"Berita terbaru": "Judul"}),
               {"Mekanisme": 60, "Judul": 60, "URL": 40}, link_col="URL")
    if alerts is not None and not alerts.empty:
        al = alerts.drop(columns=[c for c in ("rincian", "berita") if c in alerts.columns])
        if "berita" in alerts.columns:
            al["jumlah_pemicu"] = alerts["berita"].map(lambda v: len(v) if isinstance(v, list) else 0)
        _tulis(wb.create_sheet("Peringatan"), al, {"judul": 60, "detail": 40, "url": 40})
        rinci = [{"Peringatan": f"{r['tingkat']} · {r['jenis']}: {r['judul']}", "Tanggal": b.get("waktu", "")[:10],
                  "Berita pemicu": b.get("judul", ""), "Sumber": b.get("sumber", ""), "Dampak": b.get("dampak", ""),
                  "Verifikasi": b.get("verifikasi", ""), "URL": b.get("url", "")}
                 for _, r in alerts.iterrows() if isinstance(r.get("berita"), list) for b in r["berita"]]
        if rinci:
            _tulis(wb.create_sheet("Pemicu peringatan"), pd.DataFrame(rinci),
                   {"Peringatan": 50, "Berita pemicu": 70, "URL": 40}, link_col="URL")
    if ref:
        r = pd.DataFrame(ref)[["no", "tanggal", "judul", "sumber", "label", "dampak", "verifikasi", "url"]]
        r.columns = ["No", "Tanggal", "Judul", "Sumber", "Sentimen", "Dampak", "Verifikasi", "URL"]
        _tulis(wb.create_sheet("Referensi"), r, {"Judul": 70, "URL": 50}, link_col="URL")
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
