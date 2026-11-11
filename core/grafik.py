"""
Grafik sebaran sentimen (Altair).

Aturan yang dipakai (panduan visualisasi data):
  - Sentimen adalah skala berurutan (negatif → netral → positif), jadi komposisinya digambar sebagai
    BATANG DIVERGEN yang berpusat pada netral: negatif ke kiri/bawah, positif ke kanan/atas.
  - Warna divergen: merah (negatif) ↔ abu-abu (netral) ↔ biru (positif). Pasangan biru–merah tetap terbedakan
    bagi penderita buta warna merah-hijau; label teks & legenda selalu ada, jadi warna bukan satu-satunya penanda.
  - Satu sumbu-y per grafik (tidak ada grafik dua sumbu). Jumlah berita dan skor digambar di grafik terpisah.
  - Garis bantu tipis, sumbu redup, celah 2px antar-segmen, tooltip di semua grafik.
"""
from __future__ import annotations

import math

import altair as alt
import numpy as np
import pandas as pd

URUT = ["Negatif", "Netral", "Positif"]
WARNA = {"Negatif": "#e34948", "Netral": "#c3c2b7", "Positif": "#2a78d6"}
TINTA = {"Negatif": "#ffffff", "Netral": "#0b0b0b", "Positif": "#ffffff"}   # warna label di dalam segmen
TEKS_2 = "#52514e"
GRID = "#ebeae6"
GARIS_NOL = "#8c8b86"
SURFACE = "#ffffff"
FONT = "Source Sans Pro, 'Source Sans 3', sans-serif"
BUKA_TAB_BARU = {"embedOptions": {"loader": {"target": "_blank"}}}
# label tanggal berbahasa Indonesia: "13 Okt"
TGL_ID = ("timeFormat(datum.value, '%e') + ' ' + ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov',"
          "'Des'][month(datum.value)]")


def skala_sentimen() -> alt.Scale:
    return alt.Scale(domain=URUT, range=[WARNA[k] for k in URUT])


def gaya(ch):
    """Tampilan seragam: sumbu & grid redup, legenda di atas, tanpa bingkai."""
    return (ch.configure(font=FONT)
            .configure_axis(labelColor=TEKS_2, titleColor=TEKS_2, labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal", gridColor=GRID, domainColor="#cfcec8", tickColor="#cfcec8")
            .configure_legend(labelColor=TEKS_2, titleColor=TEKS_2, labelFontSize=12, orient="top",
                              symbolType="square", title=None)
            .configure_view(strokeWidth=0))


def _wib_hari(s: pd.Series) -> pd.Series:
    return s.dt.tz_convert("Asia/Jakarta").dt.tz_localize(None).dt.normalize()


# ----------------------------------------------------------------------------
# Batang divergen (horizontal) — komposisi per kelompok / per media / per pendorong
# ----------------------------------------------------------------------------
def data_divergen(d: pd.DataFrame, kol: str, persen: bool = True) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame()
    g = d.groupby([kol, "label"]).size().unstack(fill_value=0).reindex(columns=URUT, fill_value=0)
    n = g.sum(axis=1)
    v = g.div(n, axis=0) * 100 if persen else g.astype(float)
    rows = []
    for k in g.index:
        neg, net, pos = v.loc[k, "Negatif"], v.loc[k, "Netral"], v.loc[k, "Positif"]
        for lab, a, b in (("Negatif", -net / 2 - neg, -net / 2), ("Netral", -net / 2, net / 2),
                          ("Positif", net / 2, net / 2 + pos)):
            jml = int(g.loc[k, lab])
            pct = 100 * jml / n[k] if n[k] else 0
            rows.append({kol: k, "Sentimen": lab, "x0": a, "x1": b, "tengah": (a + b) / 2, "Nilai": float(v.loc[k, lab]),
                         "Jumlah": jml, "Total": int(n[k]), "Persen": pct,
                         "Teks": f"{pct:.0f}%" if persen else str(jml)})
    return pd.DataFrame(rows)


def batang_divergen(d: pd.DataFrame, kol: str, persen: bool = True, urutan: list | None = None,
                    judul_x: str | None = None, tinggi_baris: int = 34, label_min: float | None = None):
    data = data_divergen(d, kol, persen)
    if data.empty:
        return None
    if urutan is None:
        urutan = (data.drop_duplicates(kol).sort_values("Total", ascending=False)[kol].tolist())
    ujung = max(data["x0"].abs().max(), data["x1"].abs().max(), 1)
    if persen:
        m = min(100, math.ceil(ujung / 10) * 10)
    else:
        m = max(2, math.ceil(ujung))
    label_min = label_min if label_min is not None else (9 if persen else max(1, 0.07 * 2 * m))
    y = alt.Y(f"{kol}:N", sort=urutan, title=None,
              axis=alt.Axis(labelLimit=260, labelOverlap=False, ticks=False, domain=False, labelPadding=6))
    base = alt.Chart(data)
    tooltip = [alt.Tooltip(f"{kol}:N", title=kol.capitalize() if kol.islower() else kol),
               alt.Tooltip("Sentimen:N"), alt.Tooltip("Jumlah:Q", title="Berita"),
               alt.Tooltip("Persen:Q", title="% dari baris", format=".0f"), alt.Tooltip("Total:Q", title="Total berita")]
    batang = base.mark_bar(stroke=SURFACE, strokeWidth=2, height=alt.RelativeBandSize(0.68)).encode(
        y=y,
        x=alt.X("x0:Q", scale=alt.Scale(domain=[-m, m], nice=False),
                title=judul_x or ("← negatif · % berita · positif →" if persen else "← negatif · jumlah berita · positif →"),
                axis=alt.Axis(labelExpr="abs(datum.value) + '" + ("%'" if persen else "'"), tickCount=6, grid=True,
                              tickMinStep=1 if not persen else 10)),
        x2="x1:Q",
        color=alt.Color("Sentimen:N", scale=skala_sentimen(), sort=URUT, legend=alt.Legend(title=None)),
        tooltip=tooltip)
    teks = base.transform_filter(alt.datum.Nilai >= label_min).mark_text(fontSize=11, fontWeight=600).encode(
        y=y, x="tengah:Q", text="Teks:N",
        color=alt.Color("Sentimen:N", scale=alt.Scale(domain=URUT, range=[TINTA[k] for k in URUT]), legend=None),
        tooltip=tooltip)
    nol = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1).encode(x="x:Q")
    return gaya(alt.layer(batang, nol, teks).resolve_scale(color="independent")
                .properties(height=alt.Step(tinggi_baris)))


# ----------------------------------------------------------------------------
# Per hari: jumlah berita (batang divergen vertikal) + skor harian (grafik terpisah)
# ----------------------------------------------------------------------------
def _rentang_hari(hari: int) -> pd.DatetimeIndex:
    akhir = pd.Timestamp.now(tz="Asia/Jakarta").tz_localize(None).normalize()
    return pd.date_range(akhir - pd.Timedelta(days=hari - 1), akhir, freq="D")


def harian_divergen(d: pd.DataFrame, hari: int):
    if d.empty:
        return None
    x = d.assign(Tgl=_wib_hari(d["terbit"]))
    g = x.groupby(["Tgl", "label"]).size().unstack(fill_value=0).reindex(columns=URUT, fill_value=0)
    g = g.reindex(_rentang_hari(hari), fill_value=0)
    rows = []
    for t, r in g.iterrows():
        neg, net, pos = r["Negatif"], r["Netral"], r["Positif"]
        for lab, a, b in (("Negatif", -net / 2 - neg, -net / 2), ("Netral", -net / 2, net / 2),
                          ("Positif", net / 2, net / 2 + pos)):
            if r[lab]:
                rows.append({"Tgl": t, "Sentimen": lab, "y0": a, "y1": b, "Jumlah": int(r[lab]),
                             "Total": int(neg + net + pos)})
    data = pd.DataFrame(rows)
    if data.empty:
        return None
    m = max(2, math.ceil(max(data["y0"].abs().max(), data["y1"].abs().max())))
    rentang = _rentang_hari(hari)
    dom = [rentang[0], rentang[-1] + pd.Timedelta(days=1)]   # selalu seluruh periode, sejajar grafik skor
    ch = alt.Chart(data).mark_bar(stroke=SURFACE, strokeWidth=1, width=alt.RelativeBandSize(0.72)).encode(
        x=alt.X("yearmonthdate(Tgl):T", title=None, scale=alt.Scale(domain=dom),
                axis=alt.Axis(labelExpr=TGL_ID, labelAngle=0, grid=False,
                                                                  tickCount={"interval": "day", "step": max(1, hari // 10)})),
        y=alt.Y("y0:Q", scale=alt.Scale(domain=[-m, m], nice=False), title="Berita (negatif di bawah garis)",
                axis=alt.Axis(labelExpr="abs(datum.value)", tickMinStep=1, format="d")),
        y2="y1:Q",
        color=alt.Color("Sentimen:N", scale=skala_sentimen(), sort=URUT, legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("yearmonthdate(Tgl):T", title="Tanggal", format="%d %b %Y"), "Sentimen:N",
                 alt.Tooltip("Jumlah:Q", title="Berita"), alt.Tooltip("Total:Q", title="Total hari itu")])
    nol = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1).encode(y="y:Q")
    return gaya(alt.layer(ch, nol).properties(height=240))


def skor_harian(d: pd.DataFrame, hari: int):
    if d.empty:
        return None
    x = d.assign(Tgl=_wib_hari(d["terbit"]))
    g = x.groupby("Tgl").agg(Skor=("skor", lambda s: 100 * s.mean()), Berita=("skor", "size")).reset_index()
    g["Arah"] = g["Skor"].map(lambda v: "Positif" if v > 5 else ("Negatif" if v < -5 else "Netral"))
    dom = [_rentang_hari(hari)[0], _rentang_hari(hari)[-1] + pd.Timedelta(days=1)]
    xenc = alt.X("Tgl:T", title=None, scale=alt.Scale(domain=dom),
                 axis=alt.Axis(labelExpr=TGL_ID, labelAngle=0, grid=False))
    garis = alt.Chart(g).mark_line(color="#3b3a37", strokeWidth=2, interpolate="monotone").encode(
        x=xenc, y=alt.Y("Skor:Q", scale=alt.Scale(domain=[-100, 100]), title="Skor rata-rata harian",
                        axis=alt.Axis(values=[-100, -50, 0, 50, 100])))
    titik = alt.Chart(g).mark_circle(size=70, stroke=SURFACE, strokeWidth=1.5, opacity=1).encode(
        x=xenc, y="Skor:Q", color=alt.Color("Arah:N", scale=skala_sentimen(), legend=None),
        tooltip=[alt.Tooltip("Tgl:T", title="Tanggal", format="%d %b %Y"), alt.Tooltip("Skor:Q", format="+.0f"),
                 alt.Tooltip("Berita:Q")])
    target = titik.mark_circle(size=500, opacity=0)   # area hover lebih besar dari titiknya
    nol = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1, strokeDash=[3, 3]).encode(
        y="y:Q")
    return gaya(alt.layer(nol, garis, titik, target).properties(height=170))


# ----------------------------------------------------------------------------
# Sebaran tiap berita: waktu × skor (klik titik = buka berita)
# ----------------------------------------------------------------------------
def sebaran_berita(d: pd.DataFrame, hari: int):
    if d.empty:
        return None
    x = d.copy()
    x["Waktu"] = x["terbit"].dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    x["Skor"] = (x["skor"] * 100).round(0)
    x["Sentimen"] = x["label"]
    x["Relevansi"] = x["relevansi"].map(lambda v: "Disebut di judul" if v >= 1 else
                                        ("Disebut di isi" if v >= 0.6 else "Hasil pencarian"))
    x = x[["Waktu", "Skor", "Sentimen", "judul", "sumber", "pendorong", "url", "Relevansi", "cakupan"]]
    awal = _rentang_hari(hari)[0]
    tooltip = [alt.Tooltip("judul:N", title="Judul"), alt.Tooltip("sumber:N", title="Sumber"),
               alt.Tooltip("Waktu:T", title="Terbit (WIB)", format="%d %b %Y %H:%M"),
               alt.Tooltip("Sentimen:N"), alt.Tooltip("Skor:Q", format="+.0f"),
               alt.Tooltip("pendorong:N", title="Pendorong"), alt.Tooltip("cakupan:N", title="Cakupan"),
               alt.Tooltip("Relevansi:N")]
    xenc = alt.X("Waktu:T", title=None, scale=alt.Scale(domain=[awal, pd.Timestamp.now(tz="Asia/Jakarta")
                                                                .tz_localize(None)]),
                 axis=alt.Axis(labelExpr=TGL_ID, labelAngle=0, grid=False))
    yenc = alt.Y("Skor:Q", scale=alt.Scale(domain=[-105, 105]), title="Skor berita",
                 axis=alt.Axis(values=[-100, -50, 0, 50, 100]))
    titik = alt.Chart(x).mark_circle(size=80, opacity=0.9, stroke=SURFACE, strokeWidth=1.5).encode(
        x=xenc, y=yenc, color=alt.Color("Sentimen:N", scale=skala_sentimen(), sort=URUT,
                                        legend=alt.Legend(title=None)),
        href="url:N", tooltip=tooltip)
    target = alt.Chart(x).mark_circle(size=420, opacity=0).encode(x=xenc, y=yenc, href="url:N", tooltip=tooltip)
    nol = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1, strokeDash=[3, 3]).encode(
        y="y:Q")
    return gaya(alt.layer(nol, titik, target).properties(height=300, usermeta=BUKA_TAB_BARU))


# ----------------------------------------------------------------------------
# Halaman "Semua emiten"
# ----------------------------------------------------------------------------
def skor_per_emiten(g: pd.DataFrame):
    g = g.copy()
    g["Arah"] = g["Skor_"].map(lambda v: "Positif" if v >= 0 else "Negatif")
    ch = alt.Chart(g).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.62)).encode(
        y=alt.Y("Label:N", sort=list(g["Label"]), title=None,
                axis=alt.Axis(labelLimit=320, labelOverlap=False, ticks=False, domain=False)),
        x=alt.X("Skor_:Q", title="Skor sentimen (−100 … +100)", scale=alt.Scale(domain=[-100, 100])),
        color=alt.Color("Arah:N", scale=alt.Scale(domain=["Negatif", "Positif"],
                                                  range=[WARNA["Negatif"], WARNA["Positif"]]), legend=None),
        tooltip=["Emiten", "Rating", alt.Tooltip("Skor:Q", format="+.0f"), "Berita", "Sinyal"])
    nol = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1).encode(x="x:Q")
    return gaya(alt.layer(ch, nol).properties(height=alt.Step(26)))


def rating_vs_sentimen(g: pd.DataFrame, urutan: list):
    ch = alt.Chart(g).mark_circle(opacity=0.9, stroke="#3b3a37", strokeWidth=0.6).encode(
        x=alt.X("Skor_:Q", title="Skor sentimen", scale=alt.Scale(domain=[-100, 100])),
        y=alt.Y("Inti:N", sort=urutan, title="Rating", axis=alt.Axis(labelOverlap=False)),
        size=alt.Size("Berita:Q", legend=None, scale=alt.Scale(range=[60, 600])),
        color=alt.Color("Skor_:Q", legend=None, scale=alt.Scale(domain=[-60, 0, 60], interpolate="lab", clamp=True,
                                                                range=[WARNA["Negatif"], "#e4e3de", WARNA["Positif"]])),
        tooltip=["Emiten", "Rating", alt.Tooltip("Skor:Q", format="+.0f"), "Berita", "Sinyal"])
    nol = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=GARIS_NOL, strokeWidth=1, strokeDash=[3, 3]).encode(
        x="x:Q")
    return gaya(alt.layer(nol, ch).properties(height=max(240, 34 * len(urutan))))


# ----------------------------------------------------------------------------
# Emiten Intelligence: tren skor 0–100 vs harga, radar faktor, perbandingan watchlist, studi peristiwa
# ----------------------------------------------------------------------------
TINTA_UTAMA = "#3b3a37"
WARNA_HARGA = "#1f3a5f"
TGL_BLN = ("['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][month(datum.value)] + ' ' + "
           "timeFormat(datum.value, '%y')")
URUT_DAMPAK = ["Merugikan", "Campuran / belum pasti", "Netral / kecil", "Menguntungkan"]
WARNA_DAMPAK = {"Merugikan": WARNA["Negatif"], "Campuran / belum pasti": "#8c8b86", "Netral / kecil": "#c3c2b7",
                "Menguntungkan": WARNA["Positif"]}


def _sumbu_x(hari: int, judul=None, label: bool = True):
    r = _rentang_hari(hari)
    dom = [r[0], r[-1] + pd.Timedelta(days=1)]
    ax = alt.Axis(labelExpr=TGL_ID if hari <= 120 else TGL_BLN, labelAngle=0, grid=False, labels=label,
                  ticks=label, tickCount=8)
    return alt.Scale(domain=dom), ax


def tren_vs_harga(tren: pd.DataFrame, hari: int, harga: pd.DataFrame | None = None) -> list:
    """Panel bertumpuk dengan sumbu-x sama (bukan dua sumbu-y): skor sentimen 0–100, harga penutupan (bila ada),
    dan jumlah peristiwa positif/negatif per hari. Dikembalikan sebagai daftar grafik terpisah; lebar sumbu-y
    disamakan agar sumbu waktunya sejajar."""
    if tren is None or tren.empty:
        return []
    sk, ax = _sumbu_x(hari)
    t = tren.copy()
    t["Tanggal"] = pd.to_datetime(t["Tanggal"])
    ext = {"minExtent": 64, "maxExtent": 64}
    judul = lambda x: alt.TitleParams(x, anchor="start", fontSize=12, color=TEKS_2, fontWeight="normal")  # noqa: E731
    out = []
    pita = alt.Chart(pd.DataFrame({"y0": [0, 60], "y1": [40, 100], "Zona": ["negatif", "positif"]})).mark_rect(
        opacity=0.07).encode(y=alt.Y("y0:Q"), y2="y1:Q", color=alt.Color(
            "Zona:N", scale=alt.Scale(domain=["negatif", "positif"], range=[WARNA["Negatif"], WARNA["Positif"]]),
            legend=None))
    garis = alt.Chart(t).mark_line(color=TINTA_UTAMA, strokeWidth=2, interpolate="monotone").encode(
        x=alt.X("Tanggal:T", title=None, scale=sk, axis=ax),
        y=alt.Y("Skor:Q", scale=alt.Scale(domain=[0, 100]), title="Skor (0–100)",
                axis=alt.Axis(values=[0, 20, 40, 50, 60, 80, 100], **ext)))
    tt = [alt.Tooltip("Tanggal:T", format="%d %b %Y"), alt.Tooltip("Skor:Q", format=".0f", title="Skor"),
          alt.Tooltip("Peristiwa:Q", title="Peristiwa hari itu"), alt.Tooltip("Positif:Q"),
          alt.Tooltip("Negatif:Q")]
    titik = alt.Chart(t.dropna(subset=["Skor"])).mark_circle(size=380, opacity=0).encode(
        x=alt.X("Tanggal:T", scale=sk), y="Skor:Q", tooltip=tt)
    tengah = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(color=GARIS_NOL, strokeDash=[3, 3]).encode(y="y:Q")
    out.append(gaya(alt.layer(pita, tengah, garis, titik).properties(
        height=180, title=judul("Skor sentimen (jendela bergulir; area merah < 40, biru > 60)"))))
    if harga is not None and not harga.empty:
        h = harga[(harga["Tanggal"] >= sk.domain[0]) & (harga["Tanggal"] <= sk.domain[1])].copy()
        if not h.empty:
            lo, hi = float(h["Close"].min()), float(h["Close"].max())
            pad = (hi - lo) * 0.08 or hi * 0.02
            tt_h = [alt.Tooltip("Tanggal:T", format="%d %b %Y"), alt.Tooltip("Close:Q", format=",.0f", title="Harga"),
                    alt.Tooltip("Return:Q", format="+.2%"), alt.Tooltip("Volume:Q", format=",.0f")]
            xh = alt.X("Tanggal:T", title=None, scale=sk, axis=ax)
            gh = alt.Chart(h).mark_line(color=WARNA_HARGA, strokeWidth=2).encode(
                x=xh, y=alt.Y("Close:Q", title="Harga", scale=alt.Scale(domain=[lo - pad, hi + pad]),
                              axis=alt.Axis(format=",.0f", **ext)))
            hv = alt.Chart(h).mark_circle(size=300, opacity=0).encode(x=xh, y="Close:Q", tooltip=tt_h)
            out.append(gaya(alt.layer(gh, hv).properties(height=140, title=judul("Harga saham (penutupan)"))))
    rows = []
    for _, r in t.iterrows():
        if r["Positif"]:
            rows.append({"Tanggal": r["Tanggal"], "Sentimen": "Positif", "y0": 0, "y1": r["Positif"],
                         "Jumlah": r["Positif"]})
        if r["Negatif"]:
            rows.append({"Tanggal": r["Tanggal"], "Sentimen": "Negatif", "y0": -r["Negatif"], "y1": 0,
                         "Jumlah": r["Negatif"]})
    b = pd.DataFrame(rows)
    if not b.empty:
        m = max(1, int(b[["y0", "y1"]].abs().max().max()))
        batang = alt.Chart(b).mark_bar(width=alt.RelativeBandSize(0.75) if hari <= 120 else 2).encode(
            x=alt.X("yearmonthdate(Tanggal):T", title=None, scale=sk, axis=ax),
            y=alt.Y("y0:Q", title="Peristiwa", scale=alt.Scale(domain=[-m, m]),
                    axis=alt.Axis(labelExpr="abs(datum.value)", tickMinStep=1, format="d", **ext)), y2="y1:Q",
            color=alt.Color("Sentimen:N", scale=alt.Scale(domain=["Negatif", "Positif"],
                                                          range=[WARNA["Negatif"], WARNA["Positif"]]),
                            legend=alt.Legend(title=None)),
            tooltip=[alt.Tooltip("yearmonthdate(Tanggal):T", title="Tanggal", format="%d %b %Y"), "Sentimen:N",
                     alt.Tooltip("Jumlah:Q", title="Peristiwa")])
        nol = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GARIS_NOL).encode(y="y:Q")
        out.append(gaya(alt.layer(batang, nol).properties(height=110, title=judul(
            "Peristiwa per hari menurut dampak (positif di atas garis, negatif di bawah)"))))
    return out


def radar(rd: pd.DataFrame):
    """Dampak bersih tiap faktor eksternal (−1 merugikan … +1 menguntungkan)."""
    if rd is None or rd.empty:
        return None
    d = rd.copy()
    d["Nilai"] = d["Dampak"].astype(float).fillna(0)
    d["Kategori"] = d["Dampak emiten"].where(d["Dampak emiten"].isin(URUT_DAMPAK), "Netral / kecil")
    d["Label"] = [f"{f}  ({n})" for f, n in zip(d["Faktor"], d["Peristiwa"])]
    tt = [alt.Tooltip("Faktor:N"), alt.Tooltip("Sensitivitas:N"), alt.Tooltip("Arah terbaru:N"),
          alt.Tooltip("Dampak emiten:N"), alt.Tooltip("Peristiwa:Q", title="Berita"),
          alt.Tooltip("Mekanisme:N"), alt.Tooltip("Berita terbaru:N")]
    y = alt.Y("Label:N", sort=list(d["Label"]), title=None, axis=alt.Axis(labelLimit=300, ticks=False, domain=False))
    batang = alt.Chart(d).mark_bar(cornerRadiusEnd=4, height=alt.RelativeBandSize(0.6)).encode(
        y=y, x=alt.X("Nilai:Q", scale=alt.Scale(domain=[-1, 1]), title="← merugikan · dampak bersih · menguntungkan →",
                     axis=alt.Axis(values=[-1, -0.5, 0, 0.5, 1], format="+.1f")),
        color=alt.Color("Kategori:N", scale=alt.Scale(domain=URUT_DAMPAK, range=[WARNA_DAMPAK[k] for k in URUT_DAMPAK]),
                        legend=alt.Legend(title=None, columns=4, orient="top")), tooltip=tt)
    penanda = alt.Chart(d[d["Nilai"] == 0]).mark_tick(thickness=3, size=18).encode(
        y=y, x="Nilai:Q", color=alt.Color("Kategori:N", scale=alt.Scale(domain=URUT_DAMPAK,
                                                                         range=[WARNA_DAMPAK[k] for k in URUT_DAMPAK]),
                                           legend=None), tooltip=tt)
    nol = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=GARIS_NOL).encode(x="x:Q")
    return gaya(alt.layer(batang, penanda, nol).properties(height=alt.Step(34)))


def skor_banding(g: pd.DataFrame):
    """Skor 0–100 per emiten, batang bertolak dari 50 (netral)."""
    if g is None or g.empty:
        return None
    d = g.dropna(subset=["Skor"]).copy()
    if d.empty:
        return None
    d["Arah"] = d["Skor"].map(lambda v: "Positif" if v >= 50 else "Negatif")
    d["Tengah"] = 50
    tt = ["Emiten:N", alt.Tooltip("Skor:Q", format=".0f"), "Kategori:N", "Risiko:N", "Keyakinan:N",
          alt.Tooltip("Peristiwa:Q")]
    y = alt.Y("Emiten:N", sort=list(d["Emiten"]), title=None, axis=alt.Axis(labelLimit=260, ticks=False, domain=False))
    ch = alt.Chart(d).mark_bar(height=alt.RelativeBandSize(0.6)).encode(
        y=y, x=alt.X("Skor:Q", scale=alt.Scale(domain=[0, 100]), title="Skor sentimen (0–100, 50 = netral)",
                     axis=alt.Axis(values=[0, 20, 40, 50, 60, 80, 100])), x2="Tengah:Q",
        color=alt.Color("Arah:N", scale=alt.Scale(domain=["Negatif", "Positif"],
                                                  range=[WARNA["Negatif"], WARNA["Positif"]]), legend=None),
        tooltip=tt)
    teks_k = alt.Chart(d[d["Skor"] >= 50]).mark_text(dx=4, align="left", fontSize=11, color=TEKS_2).encode(
        y=y, x=alt.X("Skor:Q"), text=alt.Text("Skor:Q", format=".0f"))
    teks_n = alt.Chart(d[d["Skor"] < 50]).mark_text(dx=-4, align="right", fontSize=11, color=TEKS_2).encode(
        y=y, x=alt.X("Skor:Q"), text=alt.Text("Skor:Q", format=".0f"))
    teks = alt.layer(teks_k, teks_n)
    nol = alt.Chart(pd.DataFrame({"x": [50]})).mark_rule(color=GARIS_NOL).encode(x="x:Q")
    return gaya(alt.layer(ch, nol, teks).properties(height=alt.Step(30)))


URUT_PENILAIAN = ["Searah & signifikan", "Searah, moderat", "Searah tapi lemah", "Netral / tak terarah",
                  "Netral, harga bergerak besar", "Tidak berarti", "Berlawanan"]
WARNA_JENIS = {"Berita emiten": "#2a78d6", "Faktor eksternal": "#eb6834"}


def studi_peristiwa(sp: pd.DataFrame):
    """Selisih return saham − IHSG pada H+1 untuk peristiwa yang BERPENGARUH. Warna = jenis keterkaitan (berita
    emiten vs faktor eksternal), pekat/pudar = signifikan (≥ 2× gerak normal) vs moderat (1–2×)."""
    if sp is None or sp.empty:
        return None
    d = sp.dropna(subset=["AR H+1"]).copy()
    if d.empty:
        return None
    d["Jenis"] = np.where(d["Relasi"] == "Tidak langsung", "Faktor eksternal", "Berita emiten")
    d["Kekuatan"] = np.where(d["Penilaian"] == "Searah & signifikan", "Signifikan (≥ 2×)", "Moderat (1–2×)")
    d["Faktor"] = d["Faktor"].fillna("") if "Faktor" in d.columns else ""

    def _lbl(t, j, jenis, f):
        teks = f"{f}: {j}" if jenis == "Faktor eksternal" and f else j
        return f"{t:%d/%m} · {teks[:54]}{'…' if len(teks) > 54 else ''}"
    d["Label"] = [_lbl(t, j, k, f) for t, j, k, f in zip(d["Tanggal"], d["Peristiwa"], d["Jenis"], d["Faktor"])]
    d = d.drop_duplicates("Label")
    y = alt.Y("Label:N", sort=list(d.sort_values("Tanggal", ascending=False)["Label"]), title=None,
              axis=alt.Axis(labelLimit=340, ticks=False, domain=False))
    tt = ["Peristiwa:N", alt.Tooltip("Tanggal:T", format="%d %b %Y"), "Jenis:N", "Relasi:N", "Faktor:N", "Dampak:N",
          alt.Tooltip("Return H+1:Q", format="+.2%", title="Return saham H+1"),
          alt.Tooltip("IHSG H+1:Q", format="+.2%"), alt.Tooltip("AR H+1:Q", format="+.2%", title="Selisih vs IHSG"),
          alt.Tooltip("z:Q", format=".1f", title="× gerak normal"), "Penilaian:N"]
    ch = alt.Chart(d).mark_bar(height=alt.RelativeBandSize(0.6), cornerRadiusEnd=3).encode(
        y=y, x=alt.X("AR H+1:Q", title="Selisih return vs IHSG, H+1", axis=alt.Axis(format="+.1%")),
        color=alt.Color("Jenis:N", scale=alt.Scale(domain=list(WARNA_JENIS), range=list(WARNA_JENIS.values())),
                        legend=alt.Legend(title=None, orient="top")),
        opacity=alt.Opacity("Kekuatan:N", scale=alt.Scale(domain=["Signifikan (≥ 2×)", "Moderat (1–2×)"],
                                                          range=[1.0, 0.45]),
                            legend=alt.Legend(title=None, orient="top", symbolFillColor="#2a78d6",
                                              symbolStrokeColor="#2a78d6", symbolType="square")),
        tooltip=tt, href="URL:N")
    nol = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=GARIS_NOL).encode(x="x:Q")
    return gaya(alt.layer(ch, nol).properties(height=alt.Step(26), usermeta=BUKA_TAB_BARU))


def matriks_konfusi(cm: pd.DataFrame, judul: str = ""):
    """Confusion matrix (baris = label manusia, kolom = prediksi) sebagai peta panas satu warna + angka."""
    if cm is None or cm.empty:
        return None
    d = cm.reset_index().melt(id_vars=cm.index.name or "index", var_name="Prediksi", value_name="Jumlah")
    d = d.rename(columns={cm.index.name or "index": "Manusia"})
    tot = d.groupby("Manusia")["Jumlah"].transform("sum").replace(0, np.nan)
    d["Porsi"] = d["Jumlah"] / tot
    urut_y, urut_x = list(cm.index), list(cm.columns)
    base = alt.Chart(d).encode(
        x=alt.X("Prediksi:N", sort=urut_x, title="Prediksi mesin", axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("Manusia:N", sort=urut_y, title="Label manusia"))
    sel = base.mark_rect(stroke="#ffffff", strokeWidth=2).encode(
        color=alt.Color("Porsi:Q", scale=alt.Scale(domain=[0, 1], range=["#f4f7fb", "#1c5cab"]),
                        legend=alt.Legend(title="Porsi baris", format=".0%")),
        tooltip=["Manusia:N", "Prediksi:N", "Jumlah:Q", alt.Tooltip("Porsi:Q", format=".0%")])
    teks = base.mark_text(fontSize=13).encode(
        text="Jumlah:Q", color=alt.condition("datum.Porsi > 0.55", alt.value("#ffffff"), alt.value("#1b1b19")))
    ch = alt.layer(sel, teks).properties(height=46 * len(urut_y) + 20)
    return gaya(ch.properties(title=judul) if judul else ch)
