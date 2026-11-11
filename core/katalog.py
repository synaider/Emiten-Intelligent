"""
Katalog SELURUH emiten Bursa Efek Indonesia (± 955 perusahaan tercatat).

Bawaan (core/katalog_emiten.csv) disusun dari:
  - Data Kepemilikan Saham > 1% (KSEI via BEI) per 27 Feb 2026 → daftar kode & nama emiten terkini + pemegang saham
    utama + induk usaha (pemegang korporasi ≥ 20%)
  - Klasifikasi sektor IDX-IC (dataset publik daftar emiten BEI) dan FinanceDatabase (industri & website)
Katalog bisa diperbarui dari aplikasi: tombol "Perbarui dari IDX" (bila situs IDX mengizinkan akses) atau unggah
file "Daftar Saham" dari idx.co.id (Excel/CSV). Hasilnya disimpan di data/katalog_emiten.csv.

Setiap emiten katalog otomatis punya alias, kata kunci, sektor faktor (untuk Global Impact), website (sumber resmi),
dan entitas terkait (induk usaha) — jadi semua fitur bekerja sama seperti emiten di daftar sendiri.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .emiten import KOLOM, rapikan

KATALOG_BAWAAN = Path(__file__).with_name("katalog_emiten.csv")
TANGGAL_BAWAAN = "27 Feb 2026"
KOLOM_KAT = ["Kode", "Nama", "Sektor BEI", "Industri", "Sektor", "Papan", "Tgl Pencatatan", "Website", "Induk",
             "BUMN/Danantara", "Pemegang saham utama", "Grup", "Subgrup", "Dasar grup", "Kode induk", "Pengendali"]
EKSTRA = ["Asal", "Sektor BEI", "Industri", "Papan", "Tgl Pencatatan", "Pemegang saham utama", "BUMN/Danantara"]

# kode saham yang juga kata umum: hanya dicocokkan dalam bentuk $KODE, (KODE), KODE.JK, atau "saham KODE"
KODE_KATA = {"EMAS", "BEST", "GOOD", "LIFE", "MINE", "COIN", "FAST", "TOYS", "PURE", "CASH", "SAFE", "GOLD", "BOLA",
             "BALI", "BIRD", "KOPI", "BIKE", "JAVA", "HOME", "CITY", "HERO", "CARE", "NICE", "WIFI", "MEGA", "INDO",
             "JAYA", "ASIA", "DUTA", "ROTI", "SAPI", "KAYU", "BATA", "PADI", "AKSI", "BUMI", "KOTA", "LAND", "PORT",
             "META", "BOAT", "BOSS", "DATA", "DIVA", "DEWA", "GAMA", "HOPE", "KING", "LUCK", "MARK", "NASA", "PLAN",
             "STAR", "TECH", "TRUE", "UANG", "WOOD", "ZONE", "SOUL", "NAIK", "OBAT", "BLOG", "CHEK", "BAIK", "GULA",
             "RAJA", "RATU", "SURE", "BELL", "BLUE", "IDEA", "KIOS", "LION", "POLA", "PURA", "SAME", "SOFA", "TELE",
             "WINE", "ARTA", "TOTO", "MAXI", "MINA", "TAMA"}
UMUM_BUANG = {"indonesia", "tbk", "persero", "perseroan"}

ID_SEKTOR = {"energy": "Energi", "basic materials": "Barang Baku", "industrials": "Perindustrian",
             "consumer non-cyclicals": "Barang Konsumen Primer", "consumer cyclicals": "Barang Konsumen Non-Primer",
             "healthcare": "Kesehatan", "financials": "Keuangan", "properties & real estate": "Properti & Real Estat",
             "technology": "Teknologi", "infrastructures": "Infrastruktur",
             "transportation & logistic": "Transportasi & Logistik"}


# ----------------------------------------------------------------------------
# Muat & simpan
# ----------------------------------------------------------------------------
def _rapikan_kat(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in KOLOM_KAT:
        if c not in d.columns:
            d[c] = False if c == "BUMN/Danantara" else ""
    d = d[KOLOM_KAT]
    for c in KOLOM_KAT:
        if c != "BUMN/Danantara":
            d[c] = d[c].fillna("").astype(str).str.strip()
    d["BUMN/Danantara"] = d["BUMN/Danantara"].astype(str).str.lower().isin(["true", "1", "ya"])
    d["Kode"] = d["Kode"].str.upper()
    d = d[d["Kode"].str.fullmatch(r"[A-Z]{4}")]
    return d.drop_duplicates("Kode", keep="last").sort_values("Kode").reset_index(drop=True)


def muat(data_dir: Path) -> tuple[pd.DataFrame, str]:
    """(katalog, keterangan sumber). Katalog hasil pembaruan pengguna (data/katalog_emiten.csv) diutamakan."""
    p = Path(data_dir) / "katalog_emiten.csv"
    if p.exists():
        try:
            d = pd.read_csv(p, dtype=str)
            ket = (Path(data_dir) / "katalog_emiten.txt").read_text(encoding="utf-8").strip() \
                if (Path(data_dir) / "katalog_emiten.txt").exists() else "diperbarui pengguna"
            return _rapikan_kat(d), ket
        except Exception:  # noqa: BLE001
            pass
    return _rapikan_kat(pd.read_csv(KATALOG_BAWAAN, dtype=str)), f"bawaan, data per {TANGGAL_BAWAAN}"


def simpan(d: pd.DataFrame, data_dir: Path, keterangan: str) -> None:
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    _rapikan_kat(d).to_csv(Path(data_dir) / "katalog_emiten.csv", index=False)
    (Path(data_dir) / "katalog_emiten.txt").write_text(keterangan, encoding="utf-8")


def reset(data_dir: Path) -> None:
    for n in ("katalog_emiten.csv", "katalog_emiten.txt"):
        (Path(data_dir) / n).unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Katalog → baris emiten (format daftar emiten aplikasi)
# ----------------------------------------------------------------------------
def inti_nama(nama: str) -> str:
    s = re.sub(r"\b(PT|Tbk|Persero|Perseroan|Perseroda)\b\.?", " ", str(nama), flags=re.I)
    s = re.sub(r"[()]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" ,.")


def alias_kueri(nama: str, kode: str) -> tuple[str, str]:
    inti = inti_nama(nama)
    alias = [inti]
    # Bentuk pendek yang tetap spesifik, bukan kata grup umum seperti "Astra".
    if kode == "AALI":
        alias.append("Astra Agro")
    kata = inti.split()
    tanpa = " ".join(w for w in kata if w.lower() not in UMUM_BUANG)
    if tanpa != inti and len(tanpa.split()) >= 2:
        alias.append(tanpa)
    if kode in KODE_KATA:
        alias += [f"${kode}", f"({kode})", f"{kode}.JK", f"saham {kode}"]
        kueri = [f'"{inti}"', f'"saham {kode}"']
    else:
        alias.append(kode)
        kueri = [f'"{inti}"', kode]
    return "; ".join(dict.fromkeys(alias)), "; ".join(dict.fromkeys(kueri))


def ke_emiten(kat: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tercatat = {inti_nama(n).lower() for n in kat["Nama"]}
    for _, r in kat.iterrows():
        al, ku = alias_kueri(r["Nama"], r["Kode"])
        # kolom Terkait = induk/pemegang pengendali yang TIDAK tercatat di bursa (mis. holding pribadi). Induk yang
        # juga emiten tidak dimasukkan: beritanya kebanyakan tentang bisnis induk sendiri, bukan emiten ini.
        induk = "; ".join(x.strip() for x in str(r["Induk"]).split(";")
                          if x.strip() and inti_nama(x).lower() not in tercatat)
        rows.append({"Aktif": True, "Nama": r["Kode"], "Kode": r["Kode"], "Entitas": r["Nama"],
                     "Sektor": r["Sektor"] or "Lainnya", "Lembaga Utama": "PEFINDO", "Alias": al,
                     "Terkait": induk, "Kueri": ku, "Pengecualian": "", "Website IR": r["Website"], "Kode AS": "",
                     "Asal": "Katalog BEI", "Sektor BEI": r["Sektor BEI"], "Industri": r["Industri"],
                     "Papan": r["Papan"], "Tgl Pencatatan": r["Tgl Pencatatan"],
                     "Pemegang saham utama": r["Pemegang saham utama"], "BUMN/Danantara": r["BUMN/Danantara"]})
    return pd.DataFrame(rows, columns=KOLOM + EKSTRA).astype(object)


def gabung(milik: pd.DataFrame, kat_emiten: pd.DataFrame) -> pd.DataFrame:
    """Daftar emiten sendiri (prioritas, punya rating) + seluruh emiten katalog yang kodenya belum ada di daftar
    sendiri. Baris daftar sendiri diperkaya data katalog (website, pemegang saham) bila kodenya cocok."""
    m = rapikan(milik).astype(object)
    for c in EKSTRA:
        m[c] = pd.Series(["Daftar saya" if c == "Asal" else ("" if c != "BUMN/Danantara" else False)] * len(m),
                         index=m.index, dtype=object)
    if kat_emiten is None or kat_emiten.empty:
        return m
    k = kat_emiten.set_index("Kode")
    for i, r in m.iterrows():
        kd = str(r["Kode"]).upper()
        if kd in k.index:
            src = k.loc[kd]
            if not r["Website IR"]:
                m.at[i, "Website IR"] = src["Website IR"]
            for c in EKSTRA[1:]:
                m.at[i, c] = src[c]
    kode_milik = set(m["Kode"].str.upper())
    sisa = kat_emiten[~kat_emiten["Kode"].isin(kode_milik) & ~kat_emiten["Nama"].isin(set(m["Nama"]))]
    return pd.concat([m, sisa], ignore_index=True)


# ----------------------------------------------------------------------------
# Tebak sektor faktor dari sektor/industri BEI (untuk emiten baru hasil pembaruan)
# ----------------------------------------------------------------------------
_ATURAN = [
    (r"\bbank\b|banking", "Perbankan"), (r"insurance|asuransi|reasuransi", "Asuransi & Keuangan"),
    (r"consumer financ|multifinance|financing|pembiayaan|leasing", "Multifinance"),
    (r"securities|investment|capital market|sekuritas|holding", "Asuransi & Keuangan"),
    (r"\bcoal\b|batu ?bara", "Batu Bara"), (r"oil|gas|petroleum|minyak", "Minyak & Gas"),
    (r"metal|mineral|mining|tambang|nikel|nickel|gold|emas|timah", "Pertambangan"),
    (r"plantation|crops|perkebunan|sawit|palm", "Perkebunan"),
    (r"real estate|property|properti", "Properti & Real Estat"),
    (r"toll|jalan tol|transport infrastructure|port|airport", "Infrastruktur"),
    (r"construction|konstruksi|karya|beton", "Konstruksi"), (r"telecom|telekom|tower|seluler", "Telekomunikasi"),
    (r"electric|utilit|power|listrik|energi baru", "Energi & Utilitas"),
    (r"pharma|health|hospital|medic|farma|obat|biotek", "Kesehatan"),
    (r"software|it services|technology|teknologi|digital|internet", "Teknologi"),
    (r"airline|hotel|tourism|leisure|resort|pariwisata", "Transportasi & Pariwisata"),
    (r"shipping|logistic|transportation|pelayaran|samudera|trucking", "Logistik & Pelayaran"),
    (r"cement|semen|construction material|building material", "Industri Dasar"),
    (r"chemical|kimia|paper|pulp|packaging|kertas|plastic", "Kimia & Kertas"),
    (r"food|beverage|tobacco|household|makanan|minuman|roti", "Konsumer"),
    (r"retail|apparel|media|automobile|textile|education|edukasi|footwear|furnish", "Konsumer Siklikal"),
    (r"machinery|electrical|industrial|component|manufactur", "Industri & Manufaktur"),
]
_SEKTOR_KE_FAKTOR = {"Energi": "Minyak & Gas", "Barang Baku": "Kimia & Kertas", "Perindustrian": "Industri & Manufaktur",
                     "Barang Konsumen Primer": "Konsumer", "Barang Konsumen Non-Primer": "Konsumer Siklikal",
                     "Kesehatan": "Kesehatan", "Keuangan": "Asuransi & Keuangan",
                     "Properti & Real Estat": "Properti & Real Estat", "Teknologi": "Teknologi",
                     "Infrastruktur": "Infrastruktur", "Transportasi & Logistik": "Logistik & Pelayaran"}


def tebak_sektor(sektor_bei: str, industri: str, nama: str) -> str:
    teks = f"{industri} {nama}".lower()
    for rx, hasil in _ATURAN:
        if re.search(rx, teks):
            return hasil
    return _SEKTOR_KE_FAKTOR.get(sektor_bei, "Lainnya")


# ----------------------------------------------------------------------------
# Pembaruan: IDX (JSON) atau file "Daftar Saham" dari idx.co.id
# ----------------------------------------------------------------------------
URL_IDX = "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles"


def _kunci(d: dict, *nama):
    low = {str(k).lower(): v for k, v in d.items()}
    for n in nama:
        v = low.get(n.lower())
        if v not in (None, ""):
            return v
    return ""


def _nama_pt(n: str) -> str:
    n = re.sub(r"\s+", " ", str(n)).strip(" ,.")
    n = re.sub(r"^PT\.?\s*", "", n, flags=re.I)
    n = re.sub(r"\s*\bTbk\.?$", "", n, flags=re.I).strip(" ,.")
    return f"PT {n} Tbk"


def dari_idx(sesi=None) -> pd.DataFrame:
    """Profil seluruh emiten dari situs IDX (permintaan biasa; bisa ditolak bila IDX membatasi akses otomatis)."""
    import requests
    s = sesi or requests.Session()
    r = s.get(URL_IDX, params={"emitenType": "s", "start": 0, "length": 9999}, timeout=40,
              headers={"Accept": "application/json", "Referer": "https://www.idx.co.id/",
                       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EmitenIntelligence/1.0"})
    r.raise_for_status()
    try:
        js = r.json()
    except ValueError:
        raise RuntimeError("IDX tidak mengembalikan data (kemungkinan akses otomatis ditolak). Gunakan unggah file "
                           "Daftar Saham.") from None
    data = _kunci(js, "data", "Data", "Replies") or []
    rows = []
    for it in data:
        kode = str(_kunci(it, "KodeEmiten", "Kode", "Code")).strip().upper()
        if not re.fullmatch(r"[A-Z]{4}", kode):
            continue
        sek = str(_kunci(it, "Sektor", "Sector"))
        rows.append({"Kode": kode, "Nama": _nama_pt(_kunci(it, "NamaEmiten", "Nama", "Name")),
                     "Sektor BEI": ID_SEKTOR.get(sek.lower(), sek),
                     "Industri": str(_kunci(it, "Industri", "SubIndustri", "SubSektor", "Industry")),
                     "Papan": str(_kunci(it, "PapanPencatatan", "Papan", "ListingBoard")),
                     "Tgl Pencatatan": str(_kunci(it, "TanggalPencatatan", "ListingDate"))[:10],
                     "Website": re.sub(r"^https?://(www\.)?", "", str(_kunci(it, "Website"))).strip("/").lower()})
    if not rows:
        raise RuntimeError("Data IDX kosong atau formatnya berubah.")
    return pd.DataFrame(rows)


def dari_file(berkas) -> pd.DataFrame:
    """File 'Daftar Saham' dari idx.co.id (Excel/CSV): kolom Kode, Nama Perusahaan, Tanggal Pencatatan, Saham,
    Papan Pencatatan (nama kolom Inggris juga dikenali)."""
    nama = getattr(berkas, "name", "") or ""
    raw = berkas.read() if hasattr(berkas, "read") else Path(berkas).read_bytes()
    if nama.lower().endswith((".xlsx", ".xls")):
        d = None
        for hdr in range(0, 6):                       # judul tabel bisa tidak di baris pertama
            t = pd.read_excel(io.BytesIO(raw), header=hdr, dtype=str)
            if any(str(c).strip().lower() in ("kode", "code", "kode saham", "stock code") for c in t.columns):
                d = t
                break
        if d is None:
            raise ValueError("Kolom 'Kode' tidak ditemukan di file.")
    else:
        teks = raw.decode("utf-8-sig", errors="replace")
        d = pd.read_csv(io.StringIO(teks), sep=";" if teks.count(";") > teks.count(",") else ",", dtype=str)
    low = {c: str(c).strip().lower() for c in d.columns}
    cari = lambda *ks: next((c for c, l in low.items() if l in ks), None)  # noqa: E731
    ck = cari("kode", "code", "kode saham", "stock code", "kode emiten")
    cn = cari("nama perusahaan", "nama", "company name", "name", "nama emiten")
    if not ck or not cn:
        raise ValueError("Butuh kolom Kode dan Nama Perusahaan.")
    cs, ci = cari("sektor", "sector"), cari("industri", "industry", "sub sektor", "subsektor", "sub-sector")
    cp, ct = cari("papan pencatatan", "papan", "listing board", "board"), cari("tanggal pencatatan", "listing date")
    out = pd.DataFrame({"Kode": d[ck].astype(str).str.strip().str.upper(),
                        "Nama": d[cn].map(_nama_pt),
                        "Sektor BEI": d[cs].map(lambda v: ID_SEKTOR.get(str(v).strip().lower(), str(v).strip()))
                        if cs else "",
                        "Industri": d[ci].astype(str) if ci else "", "Papan": d[cp].astype(str) if cp else "",
                        "Tgl Pencatatan": pd.to_datetime(d[ct], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")
                        if ct else ""})
    out = out[out["Kode"].str.fullmatch(r"[A-Z]{4}")]
    if out.empty:
        raise ValueError("Tidak ada kode saham 4 huruf di file.")
    return out.fillna("")


def perbarui(lama: pd.DataFrame, baru: pd.DataFrame, lengkap: bool = True) -> tuple[pd.DataFrame, dict]:
    """Gabungkan daftar baru ke katalog. Emiten baru ditambahkan (sektor ditebak), nama/papan diperbarui.
    lengkap=True (daftar penuh ≥ 700 emiten): kode yang tidak ada lagi dianggap delisting dan dibuang."""
    lama = _rapikan_kat(lama).set_index("Kode")
    baru = baru.drop_duplicates("Kode", keep="last").set_index("Kode")
    tambah, ubah = [], []
    for kd, r in baru.iterrows():
        if kd in lama.index:
            for c in ("Nama", "Papan", "Tgl Pencatatan", "Website", "Sektor BEI", "Industri"):
                v = str(r.get(c, "") or "").strip()
                if v and v.lower() not in ("nan", "nat") and v != lama.at[kd, c]:
                    if c == "Nama":
                        ubah.append(kd)
                    lama.at[kd, c] = v
        else:
            rr = {c: (str(r.get(c, "") or "") if str(r.get(c, "")).lower() not in ("nan", "nat") else "")
                  for c in KOLOM_KAT if c not in ("Kode", "BUMN/Danantara")}
            rr["Sektor"] = tebak_sektor(rr.get("Sektor BEI", ""), rr.get("Industri", ""), rr.get("Nama", ""))
            rr["BUMN/Danantara"] = False
            lama.loc[kd] = pd.Series(rr)
            tambah.append(kd)
    hapus = []
    if lengkap and len(baru) >= 700:
        hapus = [kd for kd in lama.index if kd not in baru.index]
        lama = lama.drop(index=hapus)
    out = _rapikan_kat(lama.reset_index())
    return out, {"tambah": tambah, "ubah_nama": ubah, "hapus": hapus, "total": len(out),
                 "waktu": datetime.now().strftime("%d/%m/%Y %H:%M")}
