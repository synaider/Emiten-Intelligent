"""
Rating kredit: skala, pengurutan, perubahan (naik/turun), dan sumber data rating.

Sumber rating yang didukung:
  1. Master data aplikasi "Limit Counterparty" (data/master_data.xlsx: sheet Counterparty + Rating)
  2. File Excel "Limit_Countreparty_DDMMYYYY.xlsx" (kolom C = nama, kolom F = rating)
  3. Situs publik PEFINDO (rating terkini + riwayat press release per kode emiten)
  4. Input manual di aplikasi

Skala: idAAA ... idD (PEFINDO), AAA(idn) ... D(idn) (Fitch Indonesia). Akhiran (gg)/(sy)/(cg)
dianggap setara dengan rating polosnya untuk keperluan pengurutan.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime
from io import BytesIO

import pandas as pd

from .emiten import key_group

SKALA = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
         "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C", "SD", "RD", "D"]
_RE_RATING = re.compile(r"^(id)?(AAA|AA|A|BBB|BB|B|CCC|CC|C|SD|RD|D)([+-]?)((?:\([a-z]{2,3}\))*)$", re.I)
KOLOM_RATING = ["Nama", "Lembaga", "Tanggal", "Rating", "Outlook", "Aksi", "Keterangan", "Sumber"]


def inti(rating) -> str | None:
    """'idAA+(gg)' -> 'AA+', 'AA-(idn)' -> 'AA-'. None bila bukan rating jangka panjang."""
    if rating is None or (isinstance(rating, float) and pd.isna(rating)):
        return None
    m = _RE_RATING.match(re.sub(r"\s+", "", str(rating)))
    if not m:
        return None
    return m.group(2).upper() + (m.group(3) or "")


def peringkat(rating) -> int | None:
    """0 = terbaik (AAA). None bila tidak dikenali."""
    c = inti(rating)
    return SKALA.index(c) if c in SKALA else None


def kelompok(rating) -> str:
    p = peringkat(rating)
    if p is None:
        return "Belum ada rating"
    if p <= 3:
        return "AAA – AA-"
    if p <= 6:
        return "A+ – A-"
    if p <= 9:
        return "BBB+ – BBB-"
    return "Di bawah BBB- (non-investment grade)"


def lembaga_dari(rating) -> str:
    s = str(rating or "")
    if s.lower().startswith("id"):
        return "PEFINDO"
    if "(idn)" in s.lower():
        return "Fitch"
    return ""


def arah(lama, baru) -> str:
    """'Naik' / 'Turun' / 'Tetap' / '' (tidak bisa dibandingkan)."""
    a, b = peringkat(lama), peringkat(baru)
    if a is None or b is None:
        return ""
    return "Naik" if b < a else ("Turun" if b > a else "Tetap")


def ke_tanggal(s: pd.Series) -> pd.Series:
    """Tanggal campuran: ISO (2026-10-05) dibaca tahun-bulan-hari; teks lain dibaca hari dulu (05/10/2026)."""
    def f(v):
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
            return pd.NaT
        if isinstance(v, (pd.Timestamp, datetime, date)):
            t = pd.Timestamp(v)
            return t.tz_convert(None) if t.tzinfo is not None else t
        t = str(v).strip()
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", t):
            return pd.to_datetime(t[:10], errors="coerce")
        return pd.to_datetime(t, errors="coerce", dayfirst=True)
    return pd.Series([f(v) for v in s], index=s.index, dtype="datetime64[ns]")


def kosong_rating() -> pd.DataFrame:
    df = pd.DataFrame(columns=KOLOM_RATING)
    df["Tanggal"] = pd.to_datetime(df["Tanggal"])
    return df


def rapikan_rating(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in KOLOM_RATING:
        if c not in df.columns:
            df[c] = None
    df = df[KOLOM_RATING]
    df["Tanggal"] = ke_tanggal(df["Tanggal"]).dt.normalize()
    df["Nama"] = df["Nama"].map(key_group)
    for c in ("Lembaga", "Rating", "Outlook", "Aksi", "Keterangan", "Sumber"):
        df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""
                          else str(v).strip())
    df = df[(df["Nama"] != "") & df["Rating"].notna() & df["Tanggal"].notna()]
    df["Lembaga"] = [l or lembaga_dari(r) or "Lainnya" for l, r in zip(df["Lembaga"], df["Rating"])]
    df = df.sort_values(["Nama", "Lembaga", "Tanggal"], kind="stable")
    df = df.drop_duplicates(subset=["Nama", "Lembaga", "Tanggal", "Rating"], keep="last")
    return df.reset_index(drop=True)


def status_rating(rt: pd.DataFrame, nama: str, lembaga_utama: str = "", per: date | None = None) -> dict:
    """Rating terkini, rating sebelumnya (yang berbeda), arah perubahan & tanggalnya, untuk satu emiten."""
    k = key_group(nama)
    d = rt[rt["Nama"] == k]
    if per is not None:
        d = d[d["Tanggal"] <= pd.Timestamp(per)]
    hasil = {"Rating": None, "Lembaga": None, "Outlook": None, "Tgl Rating": None, "Rating Sebelumnya": None,
             "Perubahan": "", "Tgl Perubahan": None, "Aksi Terakhir": None, "Keterangan": None}
    if d.empty:
        return hasil
    urut = [lembaga_utama, "PEFINDO", "Fitch"] if lembaga_utama else ["PEFINDO", "Fitch"]
    lem = next((l for l in urut if l and (d["Lembaga"] == l).any()), d["Lembaga"].iloc[-1])
    d = d[d["Lembaga"] == lem].sort_values("Tanggal", kind="stable")
    akhir = d.iloc[-1]
    hasil.update({"Rating": akhir["Rating"], "Lembaga": lem, "Outlook": akhir["Outlook"],
                  "Tgl Rating": akhir["Tanggal"], "Aksi Terakhir": akhir["Aksi"], "Keterangan": akhir["Keterangan"]})
    # outlook terakhir yang terisi
    ol = d["Outlook"].dropna()
    if hasil["Outlook"] is None and not ol.empty:
        hasil["Outlook"] = ol.iloc[-1]
    # cari rating berbeda terakhir sebelum rating terkini
    ci = inti(akhir["Rating"])
    for i in range(len(d) - 2, -1, -1):
        if inti(d.iloc[i]["Rating"]) != ci:
            hasil["Rating Sebelumnya"] = d.iloc[i]["Rating"]
            hasil["Perubahan"] = arah(d.iloc[i]["Rating"], akhir["Rating"])
            # tanggal perubahan = baris pertama setelah rating lama
            hasil["Tgl Perubahan"] = d.iloc[i + 1]["Tanggal"]
            break
    else:
        hasil["Perubahan"] = "Tetap" if len(d) > 1 else ""
    return hasil


# ----------------------------------------------------------------------------
# Impor dari aplikasi / file Limit Counterparty
# ----------------------------------------------------------------------------
def impor_master_limit(data: bytes) -> tuple[pd.DataFrame, list[str], dict]:
    """Baca master_data.xlsx aplikasi Limit Counterparty.
    Return (riwayat rating, daftar nama group Non MI, info kode/entitas per group)."""
    xls = pd.ExcelFile(BytesIO(data))
    if "Rating" not in xls.sheet_names:
        raise ValueError("Sheet 'Rating' tidak ditemukan. Pastikan ini file master_data.xlsx dari aplikasi Limit "
                         "Counterparty.")
    rt = pd.read_excel(xls, "Rating")
    cp = pd.read_excel(xls, "Counterparty") if "Counterparty" in xls.sheet_names else pd.DataFrame()
    nama_nonmi, info = [], {}
    if not cp.empty and "Nama" in cp.columns:
        if "Kategori" in cp.columns:
            cp = cp[cp["Kategori"].astype(str).str.strip().str.upper() != "MI"]
        for _, r in cp.iterrows():
            k = key_group(r["Nama"])
            nama_nonmi.append(k)
            info[k] = {"Kode": r.get("Kode PEFINDO"), "Entitas": r.get("Nama Entitas"), "Alias": r.get("Alias"),
                       "Lembaga Utama": r.get("Lembaga Utama")}
    if "Kategori" in cp.columns and not cp.empty:
        rt = rt[rt["Nama"].map(key_group).isin(set(nama_nonmi))]
    out = pd.DataFrame({
        "Nama": rt["Nama"], "Lembaga": rt.get("Lembaga"), "Tanggal": rt.get("Tanggal Efektif"),
        "Rating": rt.get("Rating"), "Outlook": rt.get("Outlook"), "Aksi": None,
        "Keterangan": rt.get("Keterangan"), "Sumber": rt.get("Sumber").fillna("Master Limit Counterparty")
        if "Sumber" in rt.columns else "Master Limit Counterparty"})
    out = out[out["Lembaga"].astype(str).str.upper() != "INTERNAL"]
    return rapikan_rating(out), nama_nonmi, info


def impor_excel_limit(data: bytes, nama_file: str = "") -> tuple[pd.DataFrame, list[str]]:
    """Baca file 'Usulan Limit Counterparty' (format Excel asli): rating Non MI per tanggal laporan."""
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(data), data_only=True)
    for ws in wb.worksheets:
        r0 = next((r for r in range(1, ws.max_row + 1)
                   if re.sub(r"\s+", " ", str(ws.cell(r, 2).value or "")).strip().upper()
                   == "TOTAL NON MANAJER INVESTASI"), None)
        if r0:
            break
    else:
        raise ValueError("Baris 'TOTAL NON MANAJER INVESTASI' tidak ditemukan di kolom B.")
    tgl = None
    for r in range(1, 6):
        for c in range(1, 12):
            if "PER TANGGAL" in str(ws.cell(r, c).value or "").upper():
                for c2 in range(c + 1, 12):
                    v = ws.cell(r, c2).value
                    if isinstance(v, (datetime, date)):
                        tgl = v
                        break
    if tgl is None:
        m = re.search(r"(\d{2})(\d{2})(\d{4})", nama_file or "")
        if m:
            tgl = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if tgl is None:
        raise ValueError("Tanggal laporan tidak terbaca (sel 'per tanggal' atau nama file DDMMYYYY).")
    rows, nama, r = [], [], r0 + 1
    while r <= ws.max_row and isinstance(ws.cell(r, 2).value, (int, float)) and ws.cell(r, 3).value:
        n, rat = ws.cell(r, 3).value, ws.cell(r, 6).value
        nama.append(key_group(n))
        if rat:
            rows.append({"Nama": n, "Lembaga": lembaga_dari(rat) or None, "Tanggal": tgl, "Rating": str(rat).strip(),
                         "Sumber": f"Excel limit {nama_file}".strip()})
        r += 1
    return rapikan_rating(pd.DataFrame(rows)), nama


# ----------------------------------------------------------------------------
# PEFINDO (halaman publik per emiten)
# ----------------------------------------------------------------------------
URL_PEFINDO = "https://www.pefindo.com/rating-action-reports/rating-report/{kode}"
_RE_PEF_TOKEN = re.compile(r"(?<![A-Za-z0-9])id(AAA|AA|A|BBB|BB|B|CCC|SD|D)([+-]?)(?![A-Za-z0-9+])(\((?:sy|gg|cg)\))?")
_RE_HEADER = re.compile(r"Corporate\s+Rating\s*/\s*Outlook\s+(id[A-Z]{1,3}[+-]?(?:\([a-z]{2}\))?)\s*(.{0,40}?)\s*"
                        r"Updated\s+on\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I | re.S)
_RE_INSTR = re.compile(r"\b(bonds?|obligasi|sukuk|mtns?|medium[- ]term|notes?|sbk|commercial papers?|subordinat\w*|"
                       r"shelf[- ]?regist\w*|phase|tahap|series|seri|tranche|programm?e?|instruments?|securities)\b", re.I)
_RE_CORP = re.compile(r"corporate (credit )?ratings?|issuer ratings?|\band its\b|peringkat perusahaan", re.I)
_AKSI = [("Naik", r"\b(upgrad\w*|rais\w*)\b"), ("Turun", r"\b(downgrad\w*|lower\w*|cut\w*)\b"),
         ("Ditarik", r"\b(withdr[ae]w\w*)\b"), ("Afirmasi", r"\b(affirm\w*|reaffirm\w*)\b"),
         ("Watch", r"\b(creditwatch|credit watch|places?)\b"), ("Baru", r"\b(assign\w*|rated|rates?)\b")]
_BULAN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mei": 5, "jun": 6, "jul": 7, "aug": 8, "agu": 8,
          "agt": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "des": 12}


def tgl_teks(s: str) -> date | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})", s or "")
    if not m:
        return None
    b = _BULAN.get(m.group(2)[:3].lower())
    try:
        return date(int(m.group(3)), b, int(m.group(1))) if b else None
    except ValueError:
        return None


def baca_judul_pefindo(judul: str) -> dict:
    """Aksi, rating perusahaan (bila ada), outlook dari judul press release PEFINDO."""
    t = re.sub(r"\s+", " ", (judul or "").replace("“", '"').replace("”", '"').replace("’", "'"))
    aksi = next((a for a, rx in _AKSI if re.search(rx, t, re.I)), "")
    toks = list(_RE_PEF_TOKEN.finditer(t))
    pilih = None
    for m in toks:  # 'to X from Y' -> X
        if re.search(r"\b(to|menjadi)\s*['\"]?\s*$", t[max(0, m.start() - 12):m.start()], re.I):
            pilih = m
            break
    pilih = pilih or (toks[0] if toks else None)
    rating = ("id" + pilih.group(1) + (pilih.group(2) or "") + (pilih.group(3) or "")) if pilih else None
    head = t[:pilih.start()] if pilih else t
    if re.search(r"fully repaid|will mature|jatuh tempo", t, re.I) and aksi not in ("Naik", "Turun", "Afirmasi"):
        tingkat = "lain"
    elif _RE_CORP.search(t):
        tingkat = "perusahaan"
    elif re.search(r"'s\b[^.;]{0,80}?" + _RE_INSTR.pattern, t, re.I) or _RE_INSTR.search(head):
        tingkat = "instrumen"
    else:
        tingkat = "perusahaan" if (aksi or rating) else "lain"
    ol = re.search(r"(stable|negative|positive|developing)\s+outlook|outlook\s+(?:is\s+|to\s+)?"
                   r"(stable|negative|positive|developing)|creditwatch\s+with\s+(negative|positive|developing)", t, re.I)
    outlook = None
    if ol:
        w = (ol.group(1) or ol.group(2) or ol.group(3)).capitalize()
        outlook = ("CreditWatch " + w) if ol.group(3) else w
    return {"aksi": aksi, "rating": rating, "tingkat": tingkat, "outlook": outlook, "judul": t}


def parse_halaman_pefindo(html: str, kode: str, url: str = "") -> dict:
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    full = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    out = {"kode": kode, "url": url, "rating": None, "outlook": None, "tgl": None, "rilis": []}
    m = _RE_HEADER.search(full)
    if m:
        out["rating"], out["outlook"], out["tgl"] = m.group(1), (m.group(2).strip(" :-|") or None), tgl_teks(m.group(3))
    for tb in soup.find_all("table"):
        head = " ".join(c.get_text(" ", strip=True).lower() for c in tb.find_all(["th", "td"], limit=4))
        if "release date" not in head or "title" not in head:
            continue
        for tr in tb.find_all("tr"):
            sel = tr.find_all("td")
            if len(sel) >= 2:
                d = tgl_teks(sel[0].get_text(" ", strip=True))
                if d:
                    a = sel[1].find("a")
                    out["rilis"].append((d, sel[1].get_text(" ", strip=True),
                                      urljoin(url, a.get("href")) if a and a.get("href") else None))
        break  # tabel pertama = Press Release
    out["rilis"].sort(key=lambda x: x[0])
    return out


def riwayat_pefindo(h: dict, nama: str) -> tuple[pd.DataFrame, list[dict]]:
    """(riwayat rating perusahaan, daftar rilis sebagai 'berita' aksi rating)."""
    rows, berita, terakhir = [], [], None
    for tgl, judul, href in h["rilis"]:
        info = baca_judul_pefindo(judul)
        if info["tingkat"] == "lain" and not info["aksi"]:
            continue
        berita.append({"tanggal": tgl, "judul": judul, "url": href or h["url"], "aksi": info["aksi"],
                       "rating": info["rating"], "tingkat": info["tingkat"], "outlook": info["outlook"]})
        if info["tingkat"] != "perusahaan":
            continue
        r = info["rating"] or (terakhir if info["aksi"] == "Afirmasi" else None)
        if r:
            rows.append({"Nama": nama, "Lembaga": "PEFINDO", "Tanggal": tgl, "Rating": r, "Outlook": info["outlook"],
                         "Aksi": info["aksi"], "Keterangan": judul[:200], "Sumber": h["url"]})
            terakhir = r
    if h["rating"] and h["tgl"]:
        rows.append({"Nama": nama, "Lembaga": "PEFINDO", "Tanggal": h["tgl"], "Rating": h["rating"],
                     "Outlook": h["outlook"], "Aksi": "Terkini", "Keterangan": "Corporate Rating/Outlook terkini",
                     "Sumber": h["url"]})
    return rapikan_rating(pd.DataFrame(rows)), berita


def ambil_pefindo(kode: str, sesi=None, timeout: int = 25) -> dict:
    import requests

    url = URL_PEFINDO.format(kode=kode.strip().upper())
    s = sesi or requests.Session()
    r = s.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                           "SentimenEmitenApp/1.0", "Accept-Language": "en,id;q=0.8"})
    if r.status_code == 404:
        raise LookupError(f"Kode {kode} tidak ditemukan di PEFINDO")
    r.raise_for_status()
    return parse_halaman_pefindo(r.text, kode.upper(), url)


def sinkron_pefindo(emiten: pd.DataFrame, progress=None, jeda: float = 0.8) -> tuple[pd.DataFrame, list, pd.DataFrame]:
    """Ambil rating PEFINDO untuk emiten aktif yang punya Kode. Return (rating, berita aksi rating, laporan)."""
    import requests

    d = emiten[emiten["Aktif"] & (emiten["Kode"].str.len() > 0)]
    sesi = requests.Session()
    semua_rt, semua_b, lap = [], [], []
    gagal_koneksi = sukses = 0
    for i, (_, e) in enumerate(d.iterrows(), start=1):
        if progress:
            progress(i, len(d), e["Nama"])
        if gagal_koneksi >= 2 and not sukses:
            lap.append({"Emiten": e["Nama"], "Kode": e["Kode"], "Status": "Dilewati",
                        "Catatan": "pefindo.com tidak dapat dihubungi dari komputer ini"})
            continue
        try:
            h = ambil_pefindo(e["Kode"], sesi)
            rt, br = riwayat_pefindo(h, e["Nama"])
            semua_rt.append(rt)
            semua_b += [{**b, "emiten": e["Nama"]} for b in br]
            lap.append({"Emiten": e["Nama"], "Kode": e["Kode"], "Status": "OK", "Rating": h["rating"],
                        "Outlook": h["outlook"], "Update": h["tgl"], "Jumlah rilis": len(br)})
            sukses += 1
        except Exception as ex:  # noqa: BLE001
            if not isinstance(ex, LookupError):
                gagal_koneksi += 1
            lap.append({"Emiten": e["Nama"], "Kode": e["Kode"], "Status": "Gagal", "Catatan": str(ex)[:200]})
        time.sleep(jeda)
    rt = rapikan_rating(pd.concat(semua_rt, ignore_index=True)) if semua_rt else kosong_rating()
    return rt, semua_b, pd.DataFrame(lap)
