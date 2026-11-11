"""Analisis hubungan berita dengan rating kredit *perusahaan*, bukan harga saham.

Perubahan rating/outlook hanya dianggap terkonfirmasi bila pengumuman langsung
lembaga pemeringkat ditemukan. Berita media biasa hanya menciptakan indikasi,
bukan perubahan rating yang sudah terjadi. Tidak memakai penyimpanan permanen.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from datetime import date
import pandas as pd

KOLOM = ["Tanggal", "Berita", "Hubungan", "Kategori", "Arah", "Keterangan", "Sumber", "URL"]

# Peristiwa kredit material yang layak ditelaah; nada berita saja tidak cukup.
_NEGATIF = [
    (r"\b(gagal bayar|default(?:ed)?|non.payment|missed (?:debt|coupon|interest) payment)\b", "Risiko gagal bayar"),
    (r"\b(pkpu|pailit|bankrupt(?:cy)?|insolven\w*|debt restructuring|restrukturisasi utang)\b", "Risiko restrukturisasi/insolvensi"),
    (r"\b(krisis likuiditas|liquidity crunch|severe liquidity|tekanan likuiditas berat|cash flow shortfall)\b", "Risiko likuiditas"),
    (r"\b(pelanggaran covenant|covenant breach|pelanggaran perjanjian utang)\b", "Risiko pembiayaan"),
    (r"\b(npl|kredit bermasalah)\b.{0,55}\b(melonjak|naik tajam|memburuk|surge|spike|soar)\b", "Kualitas aset memburuk"),
]
_POSITIF = [
    (r"\b(pelunasan (?:penuh )?(?:utang|obligasi)|fully repaid (?:its )?(?:debt|bonds?)|debt repayment completed)\b", "Pelunasan kewajiban"),
    (r"\b(injeksi modal|suntikan modal|capital injection|additional capital)\b", "Penguatan permodalan"),
]
_RX_RATING = re.compile(r"\b(pefindo|fitch|moody'?s|s&p|standard.{0,5}poor|pemeringkat|credit rating|"
                        r"peringkat kredit|sovereign rating|outlook|creditwatch|downgrade|upgrade|affirm(?:ed)?|"
                        r"penurunan peringkat|kenaikan peringkat)\b", re.I)
_RX_AKSI = re.compile(r"\b(downgrad\w*|upgrad\w*|lower\w*|rais\w*|affirm\w*|reaffirm\w*|"
                      r"menurun(?:kan)? peringkat|menaikkan peringkat|mempertahankan peringkat|"
                      r"perubahan outlook|outlook (?:negatif|positif|negative|positive)|creditwatch)\b", re.I)
_RX_NEG_OUTLOOK = re.compile(r"\b(negative outlook|outlook negatif|creditwatch negative|outlook menjadi negatif)\b", re.I)
_RX_POS_OUTLOOK = re.compile(r"\b(positive outlook|outlook positif|creditwatch positive|outlook menjadi positif)\b", re.I)
_RX_SOVEREIGN = re.compile(r"\b(sovereign rating|peringkat utang negara|rating kredit indonesia|"
                           r"peringkat kredit indonesia|peringkat sovereign)\b", re.I)



# Hanya URL asli lembaga yang boleh dianggap pengumuman rating terkonfirmasi.
_DOMAINS_RESMI = ("pefindo.com", "fitchratings.com", "moodys.com", "spglobal.com")
_RX_INSTRUMEN = re.compile(r"\b(bond[s]?|obligasi|sukuk|mtn|notes|medium.term|surat utang|tranche|seri [a-z])\b", re.I)
_RX_ISSUER = re.compile(r"\b(issuer|corporate|perusahaan|emiten|bank's credit|bank.+?ratings?)\b", re.I)
_RX_UP = re.compile(r"\b(upgrad\w*|rais\w*|menaikkan peringkat|rating dinaikkan)\b", re.I)
_RX_DOWN = re.compile(r"\b(downgrad\w*|lower\w*|menurunkan peringkat|rating diturunkan)\b", re.I)
_RX_AFF = re.compile(r"\b(affirm\w*|reaffirm\w*|menegaskan peringkat|mempertahankan peringkat)\b", re.I)


def _domain_resmi(url: str) -> str:
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            return ""
        return next((d for d in _DOMAINS_RESMI if host == d or host.endswith("." + d)), "")
    except (ValueError, TypeError):
        return ""


def _aksi_dari_resmi(teks: str):
    """Hanya issuer rating, bukan rating obligasi/sukuk tertentu."""
    if _RX_INSTRUMEN.search(teks) and not _RX_ISSUER.search(teks):
        return None
    if _RX_DOWN.search(teks):
        return "Perubahan rating terkonfirmasi", "Negatif", "Pengumuman downgrade rating perusahaan"
    if _RX_UP.search(teks):
        return "Perubahan rating terkonfirmasi", "Positif", "Pengumuman upgrade rating perusahaan"
    if re.search(r"\b(outlook (?:revised|changed|diubah)|revis\w* outlook|creditwatch)\b", teks, re.I):
        return "Perubahan outlook/CreditWatch terkonfirmasi", _arah(teks), "Status outlook/watch, bukan perubahan tingkat rating"
    if _RX_AFF.search(teks):
        return "Afirmasi: rating tetap", "Belum pasti", "Tingkat rating ditegaskan, bukan upgrade/downgrade"
    return None

def _tanggal(value):
    t = pd.to_datetime(value, utc=True, errors="coerce")
    return t if not pd.isna(t) else None


def _tanggal_dalam(value, cutoff, now):
    t = _tanggal(value)
    return t is not None and cutoff <= t <= now + pd.Timedelta(days=1)


def _arah(text):
    if _RX_NEG_OUTLOOK.search(text) or re.search(r"\b(downgrad\w*|lower\w*|diturunkan|menurunkan)\b", text, re.I):
        return "Negatif"
    if _RX_POS_OUTLOOK.search(text) or re.search(r"\b(upgrad\w*|rais\w*|dinaikkan|menaikkan)\b", text, re.I):
        return "Positif"
    return "Belum pasti"


def _buat_row(tgl, judul, relasi, kategori, arah, alasan, sumber, url):
    return {"Tanggal": _tanggal(tgl), "Berita": str(judul or ""), "Hubungan": relasi,
            "Kategori": kategori, "Arah": arah, "Keterangan": alasan,
            "Sumber": str(sumber or ""), "URL": str(url or "")}


def telaah_rating(artikel: pd.DataFrame | None, rilis: list[dict] | None = None,
                  hari: int = 30, sekarang=None) -> dict[str, pd.DataFrame]:
    """Klasifikasi evidence-driven. `rilis` adalah keluaran `rating.riwayat_pefindo()`.

    Pengumuman rating instrumen tidak dianggap perubahan rating *perusahaan*.
    Hubungan tidak langsung hanya ditampilkan untuk berita sovereign yang benar-benar
    menyebut konteks rating; peristiwa makro biasa tidak langsung masuk.
    """
    now = _tanggal(sekarang) if sekarang is not None else pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(days=hari)
    konfirmasi, indikasi, afirmasi = [], [], []
    keys = set()
    for r in rilis or []:
        if not _tanggal_dalam(r.get("tanggal"), cutoff, now) or r.get("tingkat") != "perusahaan":
            continue
        aksi = str(r.get("aksi") or "")
        lembaga = str(r.get("lembaga") or "PEFINDO")
        judul = str(r.get("judul") or "")
        if aksi in ("Naik", "Turun"):
            kategori = "Perubahan rating terkonfirmasi"
            alasan = f"Pengumuman {lembaga}: rating perusahaan {aksi.lower()}" + (f" menjadi {r['rating']}" if r.get("rating") else "")
            dest = konfirmasi
            arah = "Positif" if aksi == "Naik" else "Negatif"
        elif aksi == "Watch" or ("outlook" in judul.lower() and re.search(r"\b(changed|revised|diubah|revisi)\b", judul, re.I)):
            kategori, alasan, dest = "Perubahan outlook/CreditWatch terkonfirmasi", "Tidak selalu mengubah tingkat rating", konfirmasi
            arah = _arah(judul)
        elif aksi in ("Afirmasi", "Baru"):
            kategori, alasan, dest = ("Afirmasi: rating tetap", "Tingkat rating tidak berubah", afirmasi) if aksi == "Afirmasi" else ("Rating baru", "Peringkat pertama, bukan upgrade", afirmasi)
            arah = "Belum pasti"
        else:
            continue
        row = _buat_row(r.get("tanggal"), judul, "Langsung", kategori, arah, alasan,
                        f"{lembaga} (pengumuman resmi)", r.get("url"))
        k = (str(r.get("url") or ""), judul.lower())
        if k in keys:
            continue
        keys.add(k)
        dest.append(row)

    if artikel is not None and not artikel.empty:
        for _, r in artikel.iterrows():
            d = r.to_dict()
            if not _tanggal_dalam(d.get("terbit"), cutoff, now):
                continue
            rel = str(d.get("relasi") or "")
            if rel not in ("Langsung", "Entitas terkait", "Tidak langsung"):
                continue
            judul = str(d.get("judul") or "")
            # Ringkasan bisa dipakai untuk bukti, tetapi teks terlalu pendek atau
            # judul yang tidak relevan tidak cukup untuk mengklaim rating berubah.
            ringkasan = str(d.get("ringkasan") or "")
            isi = f"{judul}. {ringkasan}"[:1800]
            # Pengumuman resmi Fitch/Moody's/S&P/PEFINDO yang lolos filter emiten
            # dapat mengonfirmasi rating walau tidak tercantum dalam riwayat PEFINDO.
            domain = _domain_resmi(str(d.get("url") or ""))
            official = _aksi_dari_resmi(judul) if domain and rel == "Langsung" and _RX_RATING.search(isi) else None
            if official:
                kategori, arah_resmi, alasan_resmi = official
                row = _buat_row(d.get("terbit"), judul, rel, kategori, arah_resmi,
                                alasan_resmi, d.get("sumber") or domain, d.get("url"))
                if not any((x["URL"] == row["URL"] and row["URL"]) or
                           x["Berita"].casefold() == judul.casefold() for x in konfirmasi + afirmasi):
                    (afirmasi if kategori.startswith("Afirmasi") else konfirmasi).append(row)
                continue
            bukti, arah = "", ""
            if rel == "Tidak langsung":
                if not (_RX_RATING.search(isi) and _RX_SOVEREIGN.search(isi)):
                    continue
                bukti, arah = "Peringkat sovereign; pengaruh terhadap emiten belum terbukti", "Belum pasti"
            else:
                for rx, alasan in _NEGATIF:
                    if re.search(rx, isi, re.I):
                        bukti, arah = alasan, "Negatif"
                        break
                if not bukti:
                    for rx, alasan in _POSITIF:
                        if re.search(rx, isi, re.I):
                            bukti, arah = alasan, "Positif"
                            break
                if not bukti and _RX_RATING.search(isi) and _RX_AKSI.search(isi):
                    bukti, arah = "Artikel menyebut aksi rating; wajib konfirmasi ke lembaga rating", _arah(isi)
            if not bukti:
                continue
            url = str(d.get("url") or "")
            if any((x["URL"] == url and url) or (x["Berita"].casefold() == judul.casefold())
                   for x in konfirmasi + afirmasi + indikasi):
                continue
            indikasi.append(_buat_row(d.get("terbit"), judul, rel,
                                      "Indikasi, belum terbukti mengubah rating", arah,
                                      bukti, d.get("sumber") or d.get("domain"), url))
    def frame(rows):
        out = pd.DataFrame(rows, columns=KOLOM)
        return out.sort_values("Tanggal", ascending=False).reset_index(drop=True) if not out.empty else out
    return {"konfirmasi": frame(konfirmasi), "indikasi": frame(indikasi), "afirmasi": frame(afirmasi)}
