"""
Data pasar (harga, return, volume, volatilitas) untuk modul Sentiment Trend & Market Response.

Sumber:
  1. Yahoo Finance (grafik harian KODE.JK) — permintaan biasa ke endpoint grafik publik.
  2. Unggah CSV (mis. ekspor "Historical Data" Investing.com/Stockbit/IDX) bila Yahoo tidak bisa diakses.

Catatan metodologi: korelasi & studi peristiwa menunjukkan HUBUNGAN HISTORIS, bukan sebab-akibat. Banyak faktor
lain (pasar global, aliran dana asing, likuiditas) ikut menggerakkan harga.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")
KOLOM = ["Tanggal", "Close", "Volume"]


def _rentang(hari: int) -> str:
    for batas, r in ((25, "3mo"), (80, "6mo"), (170, "1y"), (350, "2y"), (1700, "5y")):
        if hari <= batas:
            return r
    return "10y"


def yahoo_harga(kode: str, hari: int = 90, sesi=None) -> pd.DataFrame:
    """Harga harian dari Yahoo Finance. `kode` = kode saham IDX (BBRI) atau simbol Yahoo lengkap (BBRI.JK, TLK)."""
    kode = (kode or "").strip().upper()
    if not kode:
        return pd.DataFrame(columns=KOLOM)
    sym = kode if "." in kode or not re.fullmatch(r"[A-Z]{4}", kode) else f"{kode}.JK"
    s = sesi or requests.Session()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    r = s.get(url, params={"range": _rentang(hari), "interval": "1d", "includePrePost": "false"},
              headers={"User-Agent": UA, "Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    js = r.json()
    res = (js.get("chart") or {}).get("result") or []
    if not res:
        err = (js.get("chart") or {}).get("error") or {}
        raise RuntimeError(f"Yahoo: {err.get('description') or 'data kosong'}")
    res = res[0]
    ts = res.get("timestamp") or []
    q = (res.get("indicators") or {}).get("quote") or [{}]
    adj = ((res.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
    tz = (res.get("meta") or {}).get("exchangeTimezoneName") or "Asia/Jakarta"
    d = pd.DataFrame({"Tanggal": pd.to_datetime(ts, unit="s", utc=True).tz_convert(tz).tz_localize(None).normalize(),
                      "Close": adj or q[0].get("close"), "Volume": q[0].get("volume")})
    return _rapikan(d)


def _angka(x) -> float:
    """'1,234.5' / '1.234,5' / '12.5M' / '3,2Jt' → float."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    t = str(x).strip().replace(" ", "").replace(" ", "")
    if not t or t in ("-", "—"):
        return np.nan
    kali = 1.0
    m = re.match(r"^(.*?)([KMBTkmbt]|Jt|jt|M[iy]?|Rb|rb)$", t)
    if m and re.search(r"\d", m.group(1)):
        t, suf = m.group(1), m.group(2).lower()
        kali = {"k": 1e3, "rb": 1e3, "m": 1e6, "jt": 1e6, "b": 1e9, "mi": 1e9, "my": 1e9, "t": 1e12}.get(suf, 1)
    t = t.replace("%", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        bag = t.split(",")
        t = t.replace(",", "") if len(bag[-1]) == 3 and len(bag) > 1 else t.replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        return float(t) * kali
    except ValueError:
        return np.nan


_RX_ID = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$|^\d{1,3}(?:,\d+)?$")


def _angka_kolom(s: pd.Series) -> pd.Series:
    """Format Indonesia (titik = ribuan, koma = desimal) dideteksi per kolom, bukan per sel."""
    v = s.dropna().astype(str).str.strip().str.replace("\u00a0", "", regex=False)
    v = v[v != ""]
    if len(v) and v.str.match(_RX_ID).all() and v.str.contains(r"\.\d{3}").any():
        return s.map(lambda x: np.nan if pd.isna(x) or str(x).strip() == "" else
                     float(str(x).strip().replace(".", "").replace(",", ".")))
    return s.map(_angka)


def _pilih_tanggal(tg: pd.Series) -> pd.Series:
    t = pd.to_datetime(tg, errors="coerce", format="ISO8601")
    if t.notna().mean() > 0.5:
        return t
    a = pd.to_datetime(tg, errors="coerce", dayfirst=False)
    b = pd.to_datetime(tg, errors="coerce", dayfirst=True)

    def nilai(x):  # data harian → selisih antar-baris ~1–3 hari; tafsiran yang salah melompat per bulan
        x = x.dropna()
        if len(x) < 2:
            return (-len(x), 0)
        gap = x.sort_values().diff().dt.days.dropna()
        return (-len(x), float(gap.median()))
    return a if nilai(a) <= nilai(b) else b


def dari_csv(berkas) -> pd.DataFrame:
    """Baca CSV/Excel harga historis. Mengenali kolom: Date/Tanggal, Close/Price/Terakhir/Penutupan/Adj Close,
    Volume/Vol./Vol."""
    nama = getattr(berkas, "name", "") or ""
    raw = berkas.read() if hasattr(berkas, "read") else open(berkas, "rb").read()
    if nama.lower().endswith((".xlsx", ".xls")):
        d = pd.read_excel(io.BytesIO(raw))
    else:
        teks = raw.decode("utf-8-sig", errors="replace")
        sep = ";" if teks.count(";") > teks.count(",") else ","
        d = pd.read_csv(io.StringIO(teks), sep=sep, dtype=str)
    low = {c: str(c).strip().lower() for c in d.columns}
    cari = lambda *ks: next((c for c, l in low.items() if l in ks), None)  # noqa: E731
    c_t = cari("date", "tanggal", "time", "datetime")
    c_c = cari("adj close", "adj_close", "close", "price", "terakhir", "penutupan", "harga", "last")
    c_v = cari("volume", "vol.", "vol", "volume (lembar)")
    if not c_t or not c_c:
        raise ValueError("Kolom tanggal/harga tidak dikenali. Butuh kolom Date/Tanggal dan Close/Price/Terakhir.")
    t1 = _pilih_tanggal(d[c_t].astype(str).str.strip())
    out = pd.DataFrame({"Tanggal": t1, "Close": _angka_kolom(d[c_c]),
                        "Volume": _angka_kolom(d[c_v]) if c_v else np.nan})
    if out["Tanggal"].dt.tz is not None:
        out["Tanggal"] = out["Tanggal"].dt.tz_localize(None)
    out["Tanggal"] = out["Tanggal"].dt.normalize()
    return _rapikan(out)


def _rapikan(d: pd.DataFrame) -> pd.DataFrame:
    d = d.dropna(subset=["Tanggal", "Close"])
    d = d[d["Close"] > 0].sort_values("Tanggal").drop_duplicates("Tanggal", keep="last").reset_index(drop=True)
    d["Return"] = d["Close"].pct_change()
    d["Volatilitas 20h"] = d["Return"].rolling(20, min_periods=10).std() * np.sqrt(252)
    return d


def metrik(h: pd.DataFrame, hari: int) -> dict:
    """Return periode, volatilitas tahunan, rata-rata volume & perubahan volume, drawdown maksimum."""
    if h is None or h.empty:
        return {}
    batas = h["Tanggal"].max() - pd.Timedelta(days=hari)
    p = h[h["Tanggal"] >= batas]
    if len(p) < 2:
        return {}
    ret = p["Close"].iloc[-1] / p["Close"].iloc[0] - 1
    vol = p["Return"].std() * np.sqrt(252)
    v_rata = p["Volume"].mean()
    v5 = p["Volume"].tail(5).mean()
    puncak = p["Close"].cummax()
    dd = float((p["Close"] / puncak - 1).min())
    return {"harga": float(p["Close"].iloc[-1]), "tanggal": p["Tanggal"].iloc[-1], "return": float(ret),
            "volatilitas": float(vol) if pd.notna(vol) else None,
            "volume_rata": float(v_rata) if pd.notna(v_rata) else None,
            "volume_5h_vs_rata": float(v5 / v_rata - 1) if v_rata and pd.notna(v5) else None,
            "drawdown": dd, "hari_bursa": len(p)}


def gabung(h: pd.DataFrame, tren: pd.DataFrame) -> pd.DataFrame:
    """Gabungkan harga harian dengan skor sentimen harian (tren dari core.intel.tren_skor)."""
    if h is None or h.empty or tren is None or tren.empty:
        return pd.DataFrame()
    t = tren.copy()
    t["Tanggal"] = pd.to_datetime(t["Tanggal"]).dt.normalize()
    d = h.merge(t, on="Tanggal", how="left")
    d["Return berikut"] = d["Return"].shift(-1)
    return d


def korelasi(g: pd.DataFrame) -> dict:
    """Korelasi peringkat (Spearman) skor sentimen hari t dengan return hari t dan t+1."""
    if g is None or g.empty or "Skor" not in g.columns:
        return {"n": 0}
    x = g.dropna(subset=["Skor", "Return"])
    y = g.dropna(subset=["Skor", "Return berikut"])
    out = {"n": len(x)}
    if len(x) >= 10:
        out["sama_hari"] = float(x["Skor"].rank().corr(x["Return"].rank()))
    if len(y) >= 10:
        out["hari_berikut"] = float(y["Skor"].rank().corr(y["Return berikut"].rank()))
    return out


def _fmt(x: float) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:+.1%}".replace(".", ",")


BERPENGARUH = ("Searah & signifikan", "Searah, moderat")
RELASI_REAKSI = ("Langsung", "Entitas terkait", "Tidak langsung")
KETERANGAN_INFO = {
    "Searah tapi lemah": "Arah harga sesuai, tetapi besarnya masih dalam gerak harian normal",
    "Netral / tak terarah": "Dampak berita ke bisnis dinilai netral/kecil",
    "Netral, harga bergerak besar": "Harga bergerak tidak biasa, tetapi berita ini netral — cek pemicu lain",
    "Tidak berarti": "Gerak harga kecil dan tidak searah",
    "Berlawanan": "Harga bergerak berlawanan dengan dampak berita — kemungkinan faktor lain"}


def _ar_harian(h: pd.DataFrame, ihsg: pd.DataFrame | None):
    """(hari, close, volume, close IHSG/None, abnormal return harian)."""
    h = h.reset_index(drop=True)
    hari = h["Tanggal"].to_numpy("datetime64[ns]")
    close, vol = h["Close"].to_numpy(float), h["Volume"].to_numpy(float)
    m = ihsg.set_index("Tanggal")["Close"].reindex(h["Tanggal"]).ffill().to_numpy(float) \
        if ihsg is not None and not ihsg.empty else None
    r_h = pd.Series(close).pct_change()
    r_m = pd.Series(m).pct_change() if m is not None else pd.Series(0.0, index=r_h.index)
    return hari, close, vol, m, (r_h - r_m.fillna(0)).to_numpy(float)


def _sd_normal(ar_h: np.ndarray, i: int) -> float:
    """Simpangan baku abnormal return 60 hari bursa sebelum hari i (gerak 'normal')."""
    jendela = ar_h[max(1, i - 61):i - 1]
    jendela = jendela[~np.isnan(jendela)]
    return float(np.std(jendela)) if len(jendela) >= 15 else float(np.nanstd(ar_h[1:]))


def dasar_kebetulan(h: pd.DataFrame, ihsg: pd.DataFrame | None = None) -> dict:
    """Seberapa sering harga bergerak 'tidak biasa' tanpa perlu ada berita: porsi hari bursa dengan |z| ≥ 1 dan ≥ 2.
    Bila berita & harga tidak berhubungan, ±separuh dari porsi |z| ≥ 1 akan tampak 'berpengaruh' secara kebetulan."""
    if h is None or len(h) < 30:
        return {"n": 0, "p1": np.nan, "p2": np.nan, "acak": np.nan}
    _, _, _, _, ar_h = _ar_harian(h, ihsg)
    z = [ar_h[i] / sd for i in range(20, len(ar_h)) if not np.isnan(ar_h[i]) and (sd := _sd_normal(ar_h, i)) > 0]
    z = np.abs(np.array(z))
    if not len(z):
        return {"n": 0, "p1": np.nan, "p2": np.nan, "acak": np.nan}
    p1, p2 = float((z >= 1).mean()), float((z >= 2).mean())
    return {"n": int(len(z)), "p1": p1, "p2": p2, "acak": p1 / 2}


def studi_peristiwa(h: pd.DataFrame, ev: pd.DataFrame, min_m: float = 0.55, ihsg: pd.DataFrame | None = None,
                    relasi: tuple = RELASI_REAKSI) -> pd.DataFrame:
    """Reaksi harga setelah tiap peristiwa yang terkait emiten — langsung maupun tidak langsung.

    - Relasi terpilih: Langsung (menyebut emiten / dokumen resminya), Entitas terkait (anak usaha/merek/induk),
      Tidak langsung (faktor eksternal sektor: harga minyak, batu bara, kurs, BI Rate, dll. — berlaku bila
      dampaknya ke sektor emiten punya arah), Pencarian (lemah).
    - Materialitas ≥ min_m untuk berita emiten. Faktor eksternal (materialitas maks. 0,6) ikut bila arah dampaknya
      jelas; berita faktor yang sama di hari bursa yang sama digabung jadi satu baris.
    - Return dari penutupan sebelum peristiwa s.d. H+1 dan H+3 hari bursa. Abnormal return (AR) = return saham −
      return IHSG → bagian gerak yang bukan sekadar ikut pasar. z = AR H+1 / simpangan baku AR 60 hari sebelumnya.
    - Peristiwa lain (termasuk faktor eksternal) di hari bursa yang sama dicatat karena reaksinya tak terpisahkan.
    - Kolom 'Berpengaruh' = harga bergerak searah dampak berita dan ≥ 1× gerak normal (Searah & signifikan /
      moderat). Sisanya hanya informasi.
    """
    kol = ["Tanggal", "Peristiwa", "Sumber", "Relasi", "Faktor", "Kaitan", "Kategori", "Aspek", "Sentimen", "Dampak",
           "Jalur dampak", "Return H+1", "IHSG H+1", "AR H+1", "Return H+3", "AR H+3", "z", "Volume x",
           "Peristiwa lain", "Penilaian", "Berpengaruh", "Keterangan", "Kesimpulan", "URL", "Verifikasi", "Serupa"]
    if h is None or h.empty or ev is None or ev.empty:
        return pd.DataFrame(columns=kol)
    rel_ok = ev["relasi"].isin(relasi)
    tl = ev["relasi"] == "Tidak langsung"
    e = ev[rel_ok & ((~tl & (ev["M"] >= min_m)) | (tl & (ev["dampak"].abs() >= 0.1) & (min_m <= 0.6)))]
    if e.empty:
        return pd.DataFrame(columns=kol)
    h = h.reset_index(drop=True)
    hari, close, vol, m, ar_h = _ar_harian(h, ihsg)

    def t0_dari(t):
        t = pd.Timestamp(t).tz_convert("Asia/Jakarta").tz_localize(None)
        t0 = (t.normalize() + pd.Timedelta(days=1)) if t.hour >= 16 else t.normalize()   # setelah bursa tutup
        return t, int(np.searchsorted(hari, t0.to_datetime64()))

    idx_semua = {}
    for _, r in ev.iterrows():
        if pd.notna(r["terbit"]) and (r["relasi"] != "Tidak langsung" or abs(r["dampak"] or 0) >= 0.1):
            pref = f"[{r.get('faktor') or 'faktor'}] " if r["relasi"] == "Tidak langsung" else ""
            idx_semua.setdefault(t0_dari(r["terbit"])[1], []).append((r["judul"], pref + r["judul"]))
    rows = []
    for _, r in e.iterrows():
        if pd.isna(r["terbit"]):
            continue
        t, i = t0_dari(r["terbit"])
        if i == 0 or i >= len(h):
            continue
        base = close[i - 1]
        r1 = close[i] / base - 1
        r3 = close[min(i + 2, len(h) - 1)] / base - 1 if i + 2 < len(h) else np.nan
        if m is not None and not np.isnan(m[i - 1]):
            m1 = m[i] / m[i - 1] - 1
            m3 = m[min(i + 2, len(h) - 1)] / m[i - 1] - 1 if i + 2 < len(h) else np.nan
        else:
            m1 = m3 = np.nan
        ar1 = r1 - (0 if np.isnan(m1) else m1)
        ar3 = r3 - (0 if np.isnan(m3) else m3) if not np.isnan(r3) else np.nan
        sd = _sd_normal(ar_h, i)
        z = ar1 / sd if sd > 0 else np.nan
        v_rata = np.nanmean(vol[max(0, i - 21):i - 1]) if i > 2 else np.nan
        vx = vol[i] / v_rata if v_rata and not np.isnan(v_rata) and v_rata > 0 else np.nan
        lain = [teks for j, teks in idx_semua.get(i, []) if j != r["judul"]]
        rows.append({"Tanggal": t.normalize(), "Peristiwa": r["judul"], "Sumber": r["sumber"], "Relasi": r["relasi"],
                     "Faktor": (r.get("faktor") or "") if r["relasi"] == "Tidak langsung" else "",
                     "Kaitan": r.get("kaitan") or "", "Kategori": r["pendorong"], "Aspek": r.get("aspek") or "",
                     "Sentimen": r["label"], "Dampak": r["dampak_label"], "Jalur dampak": r.get("penjelasan") or "",
                     "Return H+1": r1, "IHSG H+1": m1, "AR H+1": ar1, "Return H+3": r3, "AR H+3": ar3, "z": z,
                     "Volume x": vx, "Peristiwa lain": lain, "URL": r["url"], "Verifikasi": r["konfirmasi"],
                     "_dampak": r["dampak"], "_i": i, "_w": float(r.get("w") or 0)})
    d = pd.DataFrame(rows)
    if d.empty:
        return pd.DataFrame(columns=kol)
    # faktor eksternal yang sama di hari bursa yang sama → satu baris (yang dampaknya paling jelas)
    d["_k"] = np.where(d["Relasi"] == "Tidak langsung", d["Faktor"] + "|" + d["_i"].astype(str), d.index.astype(str))
    d["Serupa"] = d.groupby("_k")["_k"].transform("size") - 1
    d = d.assign(_p=d["_dampak"].abs() + d["_w"]).sort_values("_p", ascending=False).drop_duplicates("_k")
    pen, kes = zip(*[nilai_reaksi(x) for _, x in d.iterrows()])
    d["Penilaian"], d["Kesimpulan"] = pen, kes
    d["Berpengaruh"] = d["Penilaian"].isin(BERPENGARUH)
    d["Keterangan"] = d["Penilaian"].map(lambda p: "" if p in BERPENGARUH else KETERANGAN_INFO.get(p, ""))
    return d.sort_values("Tanggal", ascending=False)[kol].reset_index(drop=True)


PENILAIAN = ["Searah & signifikan", "Searah, moderat", "Searah tapi lemah", "Berlawanan", "Tidak berarti",
             "Netral, harga bergerak besar", "Netral / tak terarah"]


def nilai_reaksi(x) -> tuple[str, str]:
    """(kategori penilaian, kesimpulan dalam bahasa sehari-hari). Bukan klaim sebab-akibat."""
    d = x.get("_dampak", 0) or 0
    harap = 1 if d >= 0.15 else (-1 if d <= -0.15 else 0)
    if x.get("Relasi") == "Tidak langsung":      # dampak faktor sudah diperkecil (×0,6): ambang lebih rendah
        harap = 1 if d >= 0.1 else (-1 if d <= -0.1 else 0)
    ar, z = x["AR H+1"], x["z"]
    az = abs(z) if z is not None and not pd.isna(z) else 0
    pasar_ada = x["IHSG H+1"] is not None and not pd.isna(x["IHSG H+1"])
    gerak = (f"Saham {_fmt(x['Return H+1'])}" + (f" sementara IHSG {_fmt(x['IHSG H+1'])}" if pasar_ada else "")
             + (f" → selisih {_fmt(ar)}" if pasar_ada else "")
             + (f", sekitar {az:.1f}× gerak harian normal".replace(".", ",") if az else ""))
    if harap == 0 and az >= 2:
        kat = "Netral, harga bergerak besar"
        teks = (f"{gerak}. Harga bergerak tidak biasa di hari itu, tetapi dampak berita ini ke bisnis dinilai "
                "netral/kecil — kemungkinan ada pemicu lain (lihat peristiwa lain di hari yang sama), atau penilaian "
                "dampaknya perlu dicek ulang.")
    elif harap == 0:
        kat = "Netral / tak terarah"
        teks = (f"{gerak}. Dampak berita ini ke bisnis dinilai netral/kecil, jadi pergerakan harga kemungkinan besar "
                "dipengaruhi hal lain.")
    elif np.sign(ar) == harap and az >= 2:
        kat = "Searah & signifikan"
        teks = (f"{gerak}. Arah harga sesuai dengan dampak beritanya dan jauh melebihi gerak biasa"
                + (" serta pergerakan pasar" if pasar_ada else "") + " → indikasi kuat pasar merespons berita ini.")
    elif np.sign(ar) == harap and az >= 1:
        kat = "Searah, moderat"
        teks = f"{gerak}. Arah harga sesuai dengan dampak beritanya dan di atas gerak biasa → indikasi respons moderat."
    elif np.sign(ar) == harap:
        kat = "Searah tapi lemah"
        teks = (f"{gerak}. Arahnya sesuai, tetapi besarnya masih dalam gerak harian normal → bukti bahwa berita ini "
                "menggerakkan harga masih lemah.")
    elif az >= 1:
        kat = "Berlawanan"
        teks = (f"{gerak}. Harga bergerak BERLAWANAN dengan dampak beritanya → kemungkinan didorong faktor lain "
                "(berita lain, sentimen pasar, aliran dana) atau berita sudah diantisipasi pasar.")
    else:
        kat = "Tidak berarti"
        teks = f"{gerak}. Pergerakan kecil dan tidak searah → berita ini tampaknya tidak berdampak berarti pada harga."
    if x.get("Relasi") == "Tidak langsung":
        teks += (" Ini faktor eksternal: pengaruhnya ke emiten lewat mekanisme bisnis sektor (lihat jalur dampak), "
                 "dan faktor yang sama juga bisa menggerakkan saham lain di sektornya.")
    if not pasar_ada:
        teks += " (IHSG tidak tersedia; reaksi belum dikoreksi pergerakan pasar.)"
    if x["Volume x"] is not None and not pd.isna(x["Volume x"]) and x["Volume x"] >= 1.8:
        teks += f" Volume transaksi {x['Volume x']:.1f}× rata-rata 20 hari → perhatian pasar meningkat."
    lain = x["Peristiwa lain"] or []
    if lain:
        teks += (f" Catatan: ada {len(lain)} peristiwa lain di hari bursa yang sama (mis. “{lain[0][:70]}”), jadi "
                 "reaksi harga tidak bisa dipisahkan sepenuhnya.")
    return kat, teks


CATATAN = ("Hubungan historis, bukan sebab-akibat: harga juga digerakkan pasar global, aliran dana asing, "
           "likuiditas, dan faktor lain di luar berita. Aplikasi tidak memprediksi harga dan tidak memberi "
           "rekomendasi beli/jual.")
