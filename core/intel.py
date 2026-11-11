"""
Mesin intelijen emiten (Emiten Intelligence).

Memisahkan tiga hal yang sering dianggap sama:
  1. Sentimen teks      – nada isi berita (kolom `skor`/`label`, dari kamus / IndoBERT / FinBERT / Claude)
  2. Dampak ke emiten   – apakah peristiwa itu menguntungkan/merugikan emiten terpilih (kolom `dampak`)
  3. Prediksi harga     – TIDAK dibuat. Aplikasi hanya menampilkan hubungan historis dengan data pasar.

Alur penilaian:
  entity matching (relasi) → klasifikasi (pendorong) → sentimen teks → penalaran dampak (aspek, materialitas)
  → verifikasi & keyakinan → penggabungan peristiwa → skor 0–100.

Skor dashboard per peristiwa unik i:
  s_i = dampak peristiwa (−1 … +1; untuk berita langsung = sentimen teks terhadap emiten)
  w_i = R_i × M_i × Q_i × D_i     (relevansi × materialitas × kualitas bukti × kebaruan)
  S   = 50 + 50 · Σ w_i s_i / Σ w_i            (0 = sangat negatif, 50 = netral, 100 = sangat positif)
Bila peristiwa unik < 3, skor tidak ditampilkan ("Data tidak mencukupi").
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .sentimen import label_dari

# ----------------------------------------------------------------------------
# Verifikasi sumber
# ----------------------------------------------------------------------------
DOMAIN_RESMI = ("idx.co.id", "ojk.go.id", "bi.go.id", "bps.go.id", "kemenkeu.go.id", "esdm.go.id", "bumn.go.id",
                "ksei.co.id", "kpei.co.id", "sec.gov", "pefindo.com", "fitchratings.com", "moodys.com",
                "spglobal.com", "lps.go.id", "danantaraindonesia.com")
DOMAIN_KREDIBEL = (
    # nasional
    "kontan.co.id", "bisnis.com", "cnbcindonesia.com", "investor.id", "antaranews.com", "katadata.co.id",
    "kompas.com", "kompas.id", "tempo.co", "detik.com", "idxchannel.com", "emitennews.com", "infobanknews.com",
    "cnnindonesia.com", "liputan6.com", "beritasatu.com", "republika.co.id", "thejakartapost.com", "jakartaglobe.id",
    "bareksa.com", "idnfinancials.com", "mediaindonesia.com", "sindonews.com", "okezone.com", "kumparan.com",
    "fortuneidn.com", "swa.co.id", "wartaekonomi.co.id", "stockbit.com",
    # internasional
    "reuters.com", "bloomberg.com", "ft.com", "cnbc.com", "wsj.com", "apnews.com", "asia.nikkei.com", "nikkei.com",
    "investing.com", "finance.yahoo.com", "yahoo.com", "marketwatch.com", "barrons.com", "economist.com",
    "scmp.com", "straitstimes.com", "businesstimes.com.sg", "theedgemarkets.com", "bbc.com", "bbc.co.uk",
    "cnn.com", "theguardian.com", "forbes.com", "aljazeera.com", "dealstreetasia.com", "spglobal.com")
KANAL_RESMI = ("Sumber resmi (IDX, OJK, BI, website emiten)", "SEC EDGAR (emiten tercatat di AS)",
               "PEFINDO (aksi rating)")

RX_RUMOR = re.compile(
    r"\b(rumor|rumou?rs?|kabar burung|desas-desus|dikabarkan|kabarnya|disebut-sebut|beredar kabar|kabar beredar|"
    r"isu(?:nya)? (?:soal|tentang|terkait|bahwa)|spekulasi|berspekulasi|"
    r"sumber (?:yang )?(?:tidak|enggan|tak) (?:mau |ingin )?disebut|reportedly|sources? (?:said|say|familiar)|"
    r"people familiar|according to (?:people|sources)|unconfirmed|belum (?:di)?konfirmasi|hoaks|hoax)\b", re.I)
RX_OPINI = re.compile(
    r"\b(opini|kolom|analis (?:memperkirakan|menilai|memproyeksikan)|proyeksi|rekomendasi|target harga|"
    r"saham pilihan|cek saham|prediksi|analyst(?:s)? (?:say|expect|see)|price target|outlook for)\b", re.I)

VERIF_Q = {"Resmi": 1.0, "Media kredibel": 0.85, "Opini/analisis": 0.65, "Belum terverifikasi": 0.6,
           "Rumor / belum terkonfirmasi": 0.4}
VERIF_URUT = list(VERIF_Q)  # Resmi paling kuat
VERIF_IKON = {"Resmi": "🛡️", "Media kredibel": "✅", "Opini/analisis": "💬", "Belum terverifikasi": "❔",
              "Rumor / belum terkonfirmasi": "⚠️"}


def _cocok_domain(dom: str, daftar) -> bool:
    d = (dom or "").lower()
    return any(d == x or d.endswith("." + x) for x in daftar)


def verifikasi(r: dict, domain_ir: str = "") -> str:
    dom = str(r.get("domain") or "").lower()
    if r.get("kanal") in KANAL_RESMI or _cocok_domain(dom, DOMAIN_RESMI) or dom.endswith(".go.id") or \
            (domain_ir and _cocok_domain(dom, [domain_ir.lower().removeprefix("www.")])):
        return "Resmi"
    teks = f"{r.get('judul') or ''} {r.get('ringkasan') or ''}"
    if RX_RUMOR.search(teks):
        return "Rumor / belum terkonfirmasi"
    if RX_OPINI.search(r.get("judul") or ""):
        return "Opini/analisis"
    if _cocok_domain(dom, DOMAIN_KREDIBEL) or _cocok_domain(str(r.get("sumber") or "").lower().replace(" ", ""),
                                                            DOMAIN_KREDIBEL):
        return "Media kredibel"
    s = str(r.get("sumber") or "").lower()
    if any(k in s for k in ("reuters", "bloomberg", "financial times", "cnbc", "kontan", "bisnis", "antara",
                            "investor daily", "katadata", "kompas", "tempo", "detik", "nikkei", "wall street",
                            "associated press", "ap news", "investing.com", "yahoo", "stockbit", "idx channel")):
        return "Media kredibel"
    return "Belum terverifikasi"


# ----------------------------------------------------------------------------
# Aspek bisnis & materialitas
# ----------------------------------------------------------------------------
ASPEK = {
    "Pendapatan": r"pendapatan|penjualan|revenue|sales|kontrak|proyek|order|penyaluran kredit|kredit tumbuh|"
                  r"pembiayaan|penyaluran|"
                  r"marketing sales|volume|permintaan|demand|harga jual|tarif|penumpang|pelanggan|ekspor|produksi",
    "Laba": r"laba|rugi|profit|earnings|net income|margin|nim\b|ebitda|dividen|dividend|kinerja",
    "Biaya": r"biaya|beban|cost|expenses?|bahan baku|harga (?:batu bara|minyak|gas|gandum|bbm|avtur)|upah|"
             r"provisi|ckpn|cadangan kerugian|biaya dana|cost of fund|inflasi",
    "Likuiditas": r"utang|hutang|obligasi|sukuk|mtn|likuiditas|jatuh tempo|refinanc\w*|arus kas|cash flow|"
                  r"gagal bayar|default|pkpu|dpk|dana pihak ketiga|pendanaan|pinjaman|debt|bonds?|liquidity|kupon",
    "Reputasi": r"gugat\w*|korupsi|skandal|scandal|fraud|pembobolan|dibobol|keluhan|komplain|boikot|viral|"
                r"kebocoran data|peretas\w*|hack\w*|demo\b|unjuk rasa|kecelakaan|penghargaan|award",
    "Regulasi": r"ojk|bank indonesia|\bbi\b|peraturan|regulasi|kebijakan|pajak|izin|lisensi|sanksi|denda|larangan|"
                r"pemerintah|kementerian|regulator|policy|government|tariff|tarif impor|bea",
}
_ASPEK_RX = {k: re.compile(rf"\b(?:{v})", re.I) for k, v in ASPEK.items()}
ASPEK_PENDORONG = {
    "Aksi rating": ["Likuiditas"], "Gagal bayar & restrukturisasi": ["Likuiditas", "Reputasi"],
    "Hukum & tata kelola": ["Reputasi", "Regulasi"], "Utang & likuiditas": ["Likuiditas"],
    "Kinerja keuangan": ["Laba"], "Kebijakan & regulasi": ["Regulasi"], "Ekspansi & bisnis": ["Pendapatan"],
    "Aksi korporasi & manajemen": ["Likuiditas"], "Pasar saham": [], "Lainnya": []}

M_PENDORONG = {"Aksi rating": 1.0, "Gagal bayar & restrukturisasi": 1.0, "Hukum & tata kelola": 0.85,
               "Utang & likuiditas": 0.85, "Kinerja keuangan": 0.8, "Kebijakan & regulasi": 0.7,
               "Ekspansi & bisnis": 0.6, "Aksi korporasi & manajemen": 0.6, "Pasar saham": 0.35, "Lainnya": 0.45}
RX_ANGKA_BESAR = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:triliun|trillion|tn\b|t\b|miliar dolar|billion)", re.I)


def aspek_dari(teks: str, pendorong: str = "") -> list[str]:
    a = [k for k, rx in _ASPEK_RX.items() if rx.search(teks or "")]
    for x in ASPEK_PENDORONG.get(pendorong, []):
        if x not in a:
            a.append(x)
    return a[:4]


def materialitas(r: dict) -> float:
    m = M_PENDORONG.get(r.get("pendorong") or "Lainnya", 0.45)
    if RX_ANGKA_BESAR.search(f"{r.get('judul') or ''} {r.get('ringkasan') or ''}"):
        m += 0.1
    if r.get("kanal") in KANAL_RESMI:
        m += 0.1
    return round(min(1.0, m), 2)


def label_materialitas(m: float | None) -> str:
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return "—"
    return "Tinggi" if m >= 0.8 else ("Sedang" if m >= 0.55 else "Rendah")


def label_dampak(d: float | None, campuran: bool = False) -> str:
    if campuran:
        return "Campuran / belum pasti"
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return "Belum dapat disimpulkan"
    return {"Positif": "Menguntungkan", "Negatif": "Merugikan", "Netral": "Netral / kecil"}[label_dari(d)]


# ----------------------------------------------------------------------------
# Global & Domestic Impact Radar: faktor eksternal per sektor
# ----------------------------------------------------------------------------
@dataclass
class Faktor:
    nama: str
    kueri_id: str
    kueri_en: str
    kata: str                      # regex penanda faktor di judul
    naik: str = ""                 # regex khusus "naik" (default: kata naik umum)
    turun: str = ""


FAKTOR = {
    "BI_RATE": Faktor("Suku bunga BI", '"BI Rate" OR "suku bunga acuan" Bank Indonesia',
                      '"Bank Indonesia" interest rate', r"bi.?rate|suku bunga|interest rate|rate",
                      r"naik|menaikkan|dinaikkan|kenaikan|hike[sd]?|raise[sd]?|higher",
                      r"turun|menurunkan|diturunkan|pangkas|memangkas|dipangkas|pemangkasan|penurunan|cut[s]?|"
                      r"lower(?:s|ed)?|reduc\w*"),
    "FED": Faktor("Suku bunga The Fed", '"The Fed" suku bunga', '"Federal Reserve" rate decision',
                  r"fed|federal reserve|fomc", r"naik|menaikkan|dinaikkan|kenaikan|hike[sd]?|raise[sd]?|hawkish",
                  r"turun|pangkas|memangkas|dipangkas|pemangkasan|penurunan|cut[s]?|lower(?:s|ed)?|dovish"),
    "RUPIAH": Faktor("Nilai tukar rupiah", 'rupiah kurs dolar', 'Indonesia rupiah dollar', r"rupiah|idr",
                     r"menguat|penguatan|strengthen\w*|appreciat\w*|gain[s]?|rall(?:y|ies)",
                     r"melemah|pelemahan|anjlok|terdepresiasi|weaken\w*|depreciat\w*|slump\w*|fall[s]?|record low"),
    "BATUBARA": Faktor("Harga batu bara", '"harga batu bara"', '"coal price" OR "coal prices"',
                       r"batu ?bara|coal"),
    "MINYAK": Faktor("Harga minyak", '"harga minyak" dunia', '"oil price" OR "crude oil" Brent',
                     r"minyak|oil|brent|crude|wti"),
    "EMAS": Faktor("Harga emas", '"harga emas" dunia', '"gold price" OR "gold prices"', r"emas|gold"),
    "NIKEL": Faktor("Harga nikel", '"harga nikel"', '"nickel price" OR "nickel prices"', r"nikel|nickel"),
    "TEMBAGA": Faktor("Harga tembaga", '"harga tembaga"', '"copper price" OR "copper prices"', r"tembaga|copper"),
    "CPO": Faktor("Harga CPO (sawit)", '"harga CPO" OR "harga sawit"', '"palm oil price"', r"cpo|sawit|palm oil"),
    "GANDUM": Faktor("Harga gandum", '"harga gandum"', '"wheat price" OR "wheat prices"', r"gandum|wheat"),
    "AVTUR": Faktor("Harga avtur & BBM", '"harga avtur" OR "harga BBM"', '"jet fuel price"',
                    r"avtur|bbm|jet fuel|bahan bakar"),
    "INFLASI": Faktor("Inflasi Indonesia", '"inflasi" Indonesia BPS', '"Indonesia inflation"', r"inflasi|inflation"),
    "KREDIT": Faktor("Pertumbuhan kredit perbankan", '"pertumbuhan kredit" perbankan',
                     '"Indonesia loan growth"', r"kredit|loan"),
    "OJK": Faktor("Kebijakan OJK & regulasi keuangan", 'OJK aturan baru perbankan', 'Indonesia OJK regulation',
                  r"ojk|regulasi|aturan|regulation"),
    "INFRA": Faktor("Belanja infrastruktur pemerintah", '"anggaran infrastruktur" OR "belanja infrastruktur"',
                    '"Indonesia infrastructure" budget spending', r"infrastruktur|infrastructure|anggaran|apbn"),
    "PROPERTI": Faktor("Sektor properti & konstruksi", '"penjualan properti" OR "sektor properti"',
                       '"Indonesia property" market', r"properti|property|perumahan"),
    "MOBIL": Faktor("Penjualan mobil & motor", '"penjualan mobil" OR "penjualan motor"', '"Indonesia car sales"',
                    r"penjualan (?:mobil|motor|kendaraan)|car sales|vehicle sales"),
    "DAYABELI": Faktor("Daya beli & konsumsi", '"daya beli" OR "konsumsi rumah tangga"',
                       '"Indonesia consumer spending"', r"daya beli|konsumsi|consumer|ritel|retail"),
    "WISATA": Faktor("Kunjungan wisatawan & penumpang", '"kunjungan wisman" OR "jumlah penumpang"',
                     '"Indonesia tourism" arrivals', r"wisman|wisatawan|penumpang|tourism|tourist|arrivals|passenger"),
    "TARIF_AS": Faktor("Kebijakan dagang & tarif AS", 'tarif impor Amerika Indonesia', '"US tariffs" Indonesia',
                       r"tarif|tariff|perang dagang|trade war"),
    "GEO": Faktor("Geopolitik global", 'geopolitik konflik ekonomi global', 'geopolitical tensions markets Asia',
                  r"geopolit\w*|konflik|perang|war|sanksi|sanctions"),
    "CHINA": Faktor("Ekonomi & permintaan China", '"ekonomi China" OR "permintaan China"',
                    'China economy demand commodities', r"china|tiongkok|cina"),
    "IHSG": Faktor("Pasar saham (IHSG)", '"IHSG" ditutup', '"Jakarta Composite Index"', r"ihsg|composite|jci"),
}

# (kode faktor, sensitivitas, mekanisme). sensitivitas: +1 = faktor NAIK menguntungkan, −1 = merugikan, 0 = campuran
SEKTOR_FAKTOR: dict[str, list[tuple[str, int, str]]] = {
    "Perbankan": [
        ("BI_RATE", 0, "Penurunan suku bunga bisa menurunkan biaya dana, tetapi juga menekan imbal hasil kredit. "
                       "Dampak bersih ke NIM tergantung repricing kredit vs simpanan dan komposisi neraca."),
        ("FED", 0, "Suku bunga AS memengaruhi arus modal, kurs, dan likuiditas valas; arah dampaknya campuran."),
        ("RUPIAH", 1, "Rupiah yang menguat meredakan tekanan kualitas kredit debitur berutang valas."),
        ("KREDIT", 1, "Pertumbuhan kredit industri yang lebih tinggi mendorong pendapatan bunga."),
        ("OJK", 0, "Aturan baru dapat menambah biaya kepatuhan atau membuka peluang; perlu dibaca detailnya."),
        ("INFLASI", -1, "Inflasi tinggi menekan daya bayar debitur dan berpotensi menaikkan suku bunga."),
    ],
    "Bank Daerah": [
        ("BI_RATE", 0, "Biaya dana vs imbal hasil kredit (dominan kredit konsumer ASN) bergerak berlawanan; "
                       "dampak bersih ke NIM belum pasti."),
        ("KREDIT", 1, "Pertumbuhan kredit industri mendorong pendapatan bunga."),
        ("OJK", 0, "Aturan modal inti minimum/konsolidasi BPD dapat berdampak besar; perlu dibaca detailnya."),
        ("INFLASI", -1, "Inflasi tinggi menekan daya bayar debitur."),
    ],
    "Pembiayaan BUMN": [
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya pendanaan obligasi/pinjaman."),
        ("RUPIAH", 1, "Rupiah menguat mengurangi beban utang valas."),
        ("INFRA", 1, "Belanja infrastruktur yang besar menambah kebutuhan pembiayaan proyek."),
        ("PROPERTI", 1, "Sektor perumahan yang tumbuh menambah volume pembiayaan perumahan."),
    ],
    "Multifinance": [
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya dana dan menekan permintaan kredit kendaraan."),
        ("MOBIL", 1, "Penjualan kendaraan naik menambah volume pembiayaan baru."),
        ("DAYABELI", 1, "Daya beli kuat menurunkan risiko kredit macet."),
    ],
    "Konstruksi BUMN": [
        ("INFRA", 1, "Anggaran infrastruktur yang lebih besar menambah kontrak baru."),
        ("BI_RATE", -1, "Suku bunga naik memperberat beban bunga utang yang tinggi."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya material impor dan utang valas."),
        ("PROPERTI", 1, "Sektor properti yang tumbuh menambah proyek gedung."),
    ],
    "Infrastruktur": [
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya refinancing utang jalan tol."),
        ("INFRA", 1, "Belanja infrastruktur mendukung proyek & konsesi baru."),
        ("INFLASI", 0, "Inflasi menjadi dasar penyesuaian tarif tol, tetapi juga menaikkan biaya."),
    ],
    "Telekomunikasi": [
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya capex & sewa jaringan berdenominasi dolar."),
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya pendanaan capex."),
        ("DAYABELI", 1, "Daya beli kuat mendukung ARPU dan pelanggan data."),
        ("OJK", 0, "Kebijakan regulator (frekuensi, tarif) dapat berdampak dua arah."),
    ],
    "Energi & Utilitas": [
        ("BATUBARA", -1, "Harga batu bara naik menaikkan biaya bahan bakar pembangkit (tergantung DMO)."),
        ("MINYAK", -1, "Harga minyak naik menaikkan biaya pembangkit BBM dan kebutuhan kompensasi."),
        ("RUPIAH", 1, "Rupiah menguat mengurangi beban utang & pembelian energi berdenominasi dolar."),
        ("INFLASI", 0, "Inflasi memengaruhi biaya & keputusan tarif listrik; arah dampak campuran."),
    ],
    "Energi & Petrokimia": [
        ("MINYAK", 0, "Minyak naik menaikkan biaya nafta, tetapi bisa ikut menaikkan harga produk petrokimia; "
                      "dampak ke margin campuran."),
        ("RUPIAH", 1, "Rupiah menguat mengurangi beban utang valas."),
        ("BATUBARA", 0, "Harga energi alternatif memengaruhi daya saing panas bumi; dampak tidak langsung."),
        ("DAYABELI", 1, "Permintaan domestik yang kuat menopang volume penjualan produk."),
    ],
    "Pertambangan": [
        ("EMAS", 1, "Harga emas naik menaikkan harga jual → pendapatan & laba."),
        ("TEMBAGA", 1, "Harga tembaga naik menaikkan harga jual konsentrat."),
        ("NIKEL", 1, "Harga nikel naik menaikkan pendapatan bisnis nikel & baterai."),
        ("RUPIAH", -1, "Rupiah menguat menurunkan nilai pendapatan ekspor dalam rupiah (eksportir)."),
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya utang ekspansi."),
    ],
    "Industri Dasar": [
        ("BATUBARA", -1, "Batu bara adalah biaya energi utama produksi semen."),
        ("INFRA", 1, "Belanja infrastruktur menaikkan permintaan semen."),
        ("PROPERTI", 1, "Sektor properti yang tumbuh menaikkan permintaan semen ritel."),
        ("BI_RATE", -1, "Suku bunga naik menekan permintaan properti dan menaikkan biaya utang."),
    ],
    "Konsumer": [
        ("GANDUM", -1, "Gandum adalah bahan baku utama mi instan & tepung."),
        ("CPO", 0, "CPO naik menguntungkan bisnis perkebunan tetapi menaikkan biaya minyak goreng; campuran."),
        ("DAYABELI", 1, "Daya beli kuat menaikkan volume penjualan."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya bahan baku impor."),
    ],
    "Konglomerasi": [
        ("MOBIL", 1, "Penjualan kendaraan naik menopang bisnis otomotif & pembiayaan."),
        ("BATUBARA", 1, "Harga batu bara naik menopang bisnis tambang & alat berat grup."),
        ("CPO", 1, "Harga CPO naik menopang bisnis perkebunan grup."),
        ("BI_RATE", -1, "Suku bunga naik menekan permintaan kredit kendaraan dan menaikkan biaya utang."),
    ],
    "Transportasi & Pariwisata": [
        ("AVTUR", -1, "Harga avtur/BBM naik menaikkan biaya operasional."),
        ("WISATA", 1, "Jumlah wisatawan & penumpang naik menaikkan pendapatan."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya sewa pesawat & suku cadang berdenominasi dolar."),
        ("DAYABELI", 1, "Daya beli kuat mendukung perjalanan domestik."),
    ],
    "Batu Bara": [
        ("BATUBARA", 1, "Harga batu bara naik menaikkan harga jual → pendapatan & laba."),
        ("CHINA", 1, "Permintaan China yang kuat menopang volume & harga ekspor batu bara."),
        ("RUPIAH", -1, "Rupiah menguat menurunkan nilai pendapatan ekspor (dolar) dalam rupiah."),
        ("AVTUR", -1, "Harga BBM naik menaikkan biaya penambangan & angkutan."),
    ],
    "Minyak & Gas": [
        ("MINYAK", 1, "Harga minyak naik menaikkan harga jual minyak & gas → pendapatan."),
        ("RUPIAH", -1, "Rupiah menguat menurunkan nilai pendapatan dolar dalam rupiah."),
        ("GEO", 0, "Geopolitik mendorong harga minyak naik tetapi juga menambah ketidakpastian pasokan."),
        ("BI_RATE", -1, "Suku bunga naik menaikkan biaya pendanaan proyek hulu."),
    ],
    "Perkebunan": [
        ("CPO", 1, "Harga CPO naik menaikkan harga jual → pendapatan & laba."),
        ("RUPIAH", -1, "Rupiah menguat menurunkan nilai pendapatan ekspor dalam rupiah."),
        ("CHINA", 1, "Permintaan China/India yang kuat menopang ekspor CPO."),
        ("TARIF_AS", 0, "Kebijakan dagang & pungutan ekspor dapat berdampak dua arah."),
    ],
    "Properti & Real Estat": [
        ("BI_RATE", -1, "Suku bunga naik membuat KPR lebih mahal → permintaan rumah turun; beban bunga naik."),
        ("PROPERTI", 1, "Penjualan properti naik menaikkan marketing sales."),
        ("DAYABELI", 1, "Daya beli kuat mendukung penjualan rumah & sewa."),
        ("INFLASI", -1, "Inflasi menaikkan biaya material konstruksi."),
    ],
    "Konstruksi": [
        ("INFRA", 1, "Anggaran infrastruktur yang lebih besar menambah kontrak baru."),
        ("BI_RATE", -1, "Suku bunga naik memperberat beban bunga utang."),
        ("PROPERTI", 1, "Sektor properti yang tumbuh menambah proyek gedung."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya material impor."),
    ],
    "Kesehatan": [
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya bahan baku obat & alat kesehatan impor."),
        ("DAYABELI", 1, "Daya beli kuat mendukung belanja kesehatan."),
        ("INFLASI", -1, "Inflasi menaikkan biaya operasional."),
        ("OJK", 0, "Kebijakan pemerintah (BPJS, regulasi obat) dapat berdampak dua arah."),
    ],
    "Teknologi": [
        ("BI_RATE", -1, "Suku bunga naik menekan pendanaan & valuasi perusahaan teknologi."),
        ("DAYABELI", 1, "Daya beli kuat menaikkan transaksi digital."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya server/perangkat impor."),
        ("IHSG", 1, "Sentimen pasar yang membaik memudahkan pendanaan."),
    ],
    "Konsumer Siklikal": [
        ("DAYABELI", 1, "Daya beli kuat menaikkan penjualan barang non-primer."),
        ("BI_RATE", -1, "Suku bunga naik menekan belanja kredit konsumen."),
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya barang impor."),
        ("INFLASI", -1, "Inflasi menggerus daya beli."),
    ],
    "Asuransi & Keuangan": [
        ("IHSG", 1, "Pasar saham naik menaikkan hasil investasi & aktivitas transaksi."),
        ("BI_RATE", 0, "Suku bunga naik menaikkan imbal hasil investasi tetapi menekan nilai obligasi; campuran."),
        ("OJK", 0, "Aturan OJK baru dapat menambah biaya atau membuka peluang."),
        ("INFLASI", -1, "Inflasi menaikkan klaim & biaya."),
    ],
    "Kimia & Kertas": [
        ("MINYAK", -1, "Harga minyak naik menaikkan biaya bahan baku petrokimia & energi."),
        ("RUPIAH", 0, "Kurs memengaruhi biaya bahan baku impor dan pendapatan ekspor; campuran."),
        ("CHINA", 0, "Ekonomi China memengaruhi harga produk & persaingan impor."),
        ("DAYABELI", 1, "Permintaan domestik kuat menopang volume penjualan."),
    ],
    "Industri & Manufaktur": [
        ("RUPIAH", 1, "Rupiah menguat menurunkan biaya komponen impor."),
        ("INFRA", 1, "Belanja infrastruktur menaikkan permintaan alat & mesin."),
        ("BI_RATE", -1, "Suku bunga naik menekan investasi barang modal."),
        ("MOBIL", 1, "Penjualan kendaraan naik menopang industri komponen."),
    ],
    "Logistik & Pelayaran": [
        ("AVTUR", -1, "Harga BBM naik menaikkan biaya operasional armada."),
        ("BATUBARA", 1, "Harga & volume batu bara tinggi menaikkan permintaan angkutan laut."),
        ("DAYABELI", 1, "Konsumsi kuat menaikkan volume pengiriman barang."),
        ("RUPIAH", 0, "Kurs memengaruhi tarif dolar dan biaya kapal; campuran."),
    ],
    "Lainnya": [
        ("BI_RATE", -1, "Suku bunga naik umumnya menaikkan biaya pendanaan."),
        ("RUPIAH", 0, "Dampak kurs tergantung porsi pendapatan & utang valas."),
        ("DAYABELI", 1, "Daya beli kuat umumnya mendukung pendapatan."),
        ("GEO", 0, "Ketegangan geopolitik memengaruhi pasar secara tidak langsung."),
    ],
}
SEKTOR_LIST = list(SEKTOR_FAKTOR)

_NAIK_UMUM = (r"naik|meningkat|melonjak|melesat|meroket|menguat|tertinggi|rekor|melambung|terkerek|kenaikan|"
              r"peningkatan|lonjakan|percepatan|dinaikkan|tumbuh|accelerat\w*|"
              r"rise[sd]?|rising|rose|jump\w*|surg\w*|soar\w*|climb\w*|gain[s]?|rall\w*|higher|record high|spike\w*")
_TURUN_UMUM = (r"turun|menurun|anjlok|merosot|melemah|ambles|amblas|terkoreksi|terendah|longsor|melambat|"
               r"perlambatan|penurunan|pelemahan|dipangkas|diturunkan|lesu|slow\w*|"
               r"fall[s]?|fell|drop\w*|slump\w*|plung\w*|tumbl\w*|declin\w*|slid\w*|sink\w*|lower|weaken\w*|"
               r"record low|slip\w*")
RX_STABIL = re.compile(r"\b(tetap|ditahan|menahan|tahan|stabil|unchanged|hold[s]?|holds steady|steady|flat)\b", re.I)


def faktor_sektor(sektor: str) -> list[dict]:
    """Daftar faktor (dengan kueri) untuk sektor emiten."""
    out = []
    for kode, sens, mek in SEKTOR_FAKTOR.get(sektor) or SEKTOR_FAKTOR["Lainnya"]:
        f = FAKTOR[kode]
        out.append({"kode": kode, "faktor": f.nama, "kueri_id": f.kueri_id, "kueri_en": f.kueri_en,
                    "sensitivitas": sens, "mekanisme": mek})
    return out


def gerak_faktor(judul: str, kode: str) -> int:
    """+1 faktor naik/menguat, −1 turun/melemah, 0 stabil/tidak jelas (dibaca dari judul)."""
    f = FAKTOR.get(kode)
    t = judul or ""
    if not f:
        return 0
    rx_n = re.compile(rf"\b(?:{f.naik or _NAIK_UMUM})\b", re.I)
    rx_t = re.compile(rf"\b(?:{f.turun or _TURUN_UMUM})\b", re.I)
    n, d = rx_n.search(t), rx_t.search(t)
    if n and not d:
        return 1
    if d and not n:
        return -1
    if n and d:  # keduanya ada: ambil yang paling dekat dengan nama faktor
        k = re.search(rf"\b(?:{f.kata})", t, re.I)
        if k:
            return 1 if abs(n.start() - k.start()) <= abs(d.start() - k.start()) else -1
    return 0


def _kode_faktor(nama: str) -> str | None:
    for k, f in FAKTOR.items():
        if f.nama == nama:
            return k
    return None


# ----------------------------------------------------------------------------
# Pengayaan per artikel
# ----------------------------------------------------------------------------
KOLOM_INTEL = ["verifikasi", "Q", "materialitas", "aspek", "dampak", "dampak_label", "penjelasan"]


def perkaya(df: pd.DataFrame, sektor: str = "Lainnya", domain_ir: str = "", pola: dict | None = None) -> pd.DataFrame:
    """Tambahkan kolom verifikasi, Q, materialitas, aspek, dampak, dampak_label, penjelasan, kaitan.
    Kolom yang sudah terisi (mis. dari Claude) dipertahankan. `pola` (sumber.pola_emiten) dipakai untuk
    menjelaskan KENAPA berita dikaitkan dengan emiten. Artikel lama berelasi 'Grup usaha' (fitur yang sudah dihapus)
    diabaikan."""
    from .sumber import alasan_relevan
    if df is None or df.empty:
        d = pd.DataFrame(columns=list(df.columns if df is not None else []) + KOLOM_INTEL)
        return d
    d = df.copy()
    if "relasi" in d.columns:
        d = d.loc[~d["relasi"].fillna("").astype(str).isin(("Grup usaha", "Pencarian"))].copy()
        if d.empty:
            return pd.DataFrame(columns=list(dict.fromkeys(list(df.columns) + KOLOM_INTEL + ["kaitan"])))
        from .sumber import faktor_terbukti, relevansi as cek_relevansi
        yang_boleh = set(f["faktor"] for f in faktor_sektor(sektor))
        def bukti_benar(row):
            art = row.to_dict()
            if art.get("relasi") == "Tidak langsung":
                return art.get("faktor") in yang_boleh and faktor_terbukti(art, art.get("faktor") or "")
            if pola is None or art.get("kanal") in ("PEFINDO (aksi rating)",):
                return True
            if art.get("kanal") in ("SEC EDGAR (emiten tercatat di AS)",) and \
                    str(art.get("relasi")) == "Langsung":
                return True
            skor_, _, hubungan = cek_relevansi(art, pola, False)
            return skor_ > 0 and hubungan == art.get("relasi")
        d = d.loc[d.apply(bukti_benar, axis=1).astype(bool)].copy()
        if d.empty:
            return pd.DataFrame(columns=list(dict.fromkeys(list(df.columns) + KOLOM_INTEL + ["kaitan"])))
    d = d.reset_index(drop=True)
    for k in ("relasi", "faktor", "dampak", "aspek", "materialitas", "penjelasan", "dampak_label"):
        if k not in d.columns:
            d[k] = None
    d["relasi"] = d["relasi"].where(d["relasi"].notna() & (d["relasi"].astype(str) != ""),
                                    np.where(d["relevansi"].fillna(1) >= 0.6, "Langsung", "Pencarian"))
    peta = {f["faktor"]: f for f in faktor_sektor(sektor)}
    ver, q, mat, asp, dmp, dlab, pen = [], [], [], [], [], [], []
    for _, r in d.iterrows():
        r = r.to_dict()
        v = verifikasi(r, domain_ir)
        ver.append(v)
        q.append(VERIF_Q[v])
        m = r.get("materialitas")
        m = materialitas(r) if m is None or pd.isna(m) else float(m)
        teks = f"{r.get('judul') or ''} {r.get('ringkasan') or ''}"
        a = r.get("aspek")
        a = ", ".join(aspek_dari(teks, r.get("pendorong") or "")) if not a or pd.isna(a) else a
        s = float(r["skor"]) if r.get("skor") is not None and not pd.isna(r.get("skor")) else 0.0
        dm, dl, pj = r.get("dampak"), r.get("dampak_label"), r.get("penjelasan")
        if r.get("relasi") == "Pencarian":
            # Sentimen berita pihak lain bukan otomatis dampak bagi emiten terpilih.
            dm, dl = 0.0, "Belum dapat disimpulkan"
            pj = ("Berita ditemukan melalui kueri pencarian, tetapi tidak ada penyebutan "
                  "emiten atau entitas terkait yang dapat diverifikasi. "
                  "Sentimen artikel tidak boleh dianggap sebagai dampak bagi emiten.")
            m = 0.0
            a = ""
        elif r.get("relasi") == "Tidak langsung":
            f = peta.get(r.get("faktor") or "")
            kode = _kode_faktor(r.get("faktor") or "")
            g = gerak_faktor(r.get("judul") or "", kode) if kode else 0
            sens = f["sensitivitas"] if f else 0
            m = min(m, 0.6)
            if dm is None or pd.isna(dm):
                dm = float(sens * g) * 0.6
                kata = {1: "naik/menguat", -1: "turun/melemah", 0: "stabil / arahnya belum jelas"}[g]
                if f is None:
                    dl, pj = "Belum dapat disimpulkan", "Faktor ini tidak dipetakan untuk sektor emiten."
                elif sens == 0:
                    dl = "Campuran / belum pasti"
                    pj = f"{r.get('faktor')} {kata}. {f['mekanisme']}"
                elif g == 0:
                    dl = "Belum dapat disimpulkan"
                    pj = (f"{r.get('faktor')} {kata}. Bagi emiten sektor {sektor}, faktor ini "
                          f"{'menguntungkan' if sens > 0 else 'merugikan'} bila naik: {f['mekanisme']}")
                else:
                    dl = label_dampak(dm)
                    pj = (f"{r.get('faktor')} {kata} → cenderung {'menguntungkan' if dm > 0 else 'merugikan'} "
                          f"emiten. {f['mekanisme']}")
                a = a or ", ".join(aspek_dari(f["mekanisme"] if f else "", ""))
        else:
            if dm is None or pd.isna(dm):
                dm = s
            if not dl or pd.isna(dl):
                dl = label_dampak(dm)
            if not pj or pd.isna(pj):
                al = str(r.get("alasan") or "").strip()
                arah = {"Menguntungkan": "berpotensi positif", "Merugikan": "berpotensi negatif"}.get(
                    dl, "dampaknya kecil/netral")
                pj = (f"{r.get('pendorong') or 'Lainnya'}: {arah} bagi emiten"
                      + (f" — terutama pada {a.lower()}" if a else "") + (f". Penanda: {al}." if al else "."))
                if r.get("relasi") == "Entitas terkait":
                    pj += " Berita tentang anak usaha/merek/induk (dampak tidak langsung ke emiten)."
        mat.append(round(m, 2))
        asp.append(a or "")
        dmp.append(round(float(dm), 3))
        dlab.append(dl)
        pen.append(pj)
    d["verifikasi"], d["Q"], d["materialitas"], d["aspek"] = ver, q, mat, asp
    if pola:
        d["kaitan"] = [alasan_relevan(r, pola) for r in d.to_dict("records")]
    elif "kaitan" not in d.columns:
        d["kaitan"] = ""
    d["dampak"], d["dampak_label"], d["penjelasan"] = dmp, dlab, pen
    return d


# ----------------------------------------------------------------------------
# Penggabungan peristiwa (event aggregation)
# ----------------------------------------------------------------------------
_STOP = set("""yang dan di ke dari untuk dengan ini itu pada dalam oleh atau juga akan telah sudah jadi menjadi
hingga sebesar tahun bulan hari per para atas bagi serta karena saat usai setelah lagi masih bisa dapat ada
tbk pt persero the of to in for on with as at by from and its a an is are was were be after over amid says
said will new berita terbaru simak""".split())
RELASI_URUT = {"Langsung": 0, "Entitas terkait": 1, "Pencarian": 2, "Tidak langsung": 3}


def _token(judul: str, buang: list[re.Pattern]) -> frozenset:
    t = judul or ""
    for rx in buang:
        t = rx.sub(" ", t)
    t = re.sub(r"(?<=\d)[.,](?=\d)", "", t.lower())
    t = re.sub(r"\brp\s?", " ", t)
    w = re.findall(r"[a-z]+|\d+", t)
    return frozenset(x for x in w if x not in _STOP and (len(x) >= 3 or x.isdigit()))


def _mirip(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return False
    i = len(a & b)
    if i < 2:
        return False
    return i / min(len(a), len(b)) >= 0.6 or i / len(a | b) >= 0.45


def gabung_peristiwa(df: pd.DataFrame, pola_nama: list[str] | None = None, jendela_hari: float = 3) -> pd.Series:
    """Kembalikan id peristiwa per artikel. Artikel dengan judul mirip (≥ 2 kata kunci sama & tumpang tindih tinggi)
    dalam ±3 hari dianggap peristiwa yang sama. Nama/alias emiten dibuang dulu agar tidak menyamakan semua berita."""
    if df.empty:
        return pd.Series([], dtype="Int64")
    buang = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(x)}(?![A-Za-z0-9])", re.I)
             for x in sorted(set(pola_nama or []), key=len, reverse=True) if x]
    urut = list(df["terbit"].sort_values(kind="stable", na_position="last").index)
    tok = {i: _token(df.at[i, "judul"], buang) for i in urut}
    t = {i: df.at[i, "terbit"] for i in urut}
    faktor = (df["faktor"].fillna("").astype(str) if "faktor" in df.columns
              else pd.Series("", index=df.index))
    induk = {i: i for i in urut}
    t0 = dict(t)                       # waktu paling awal tiap kelompok (agar rantai tidak melebar > jendela)

    def akar(i):
        while induk[i] != i:
            induk[i] = induk[induk[i]]
            i = induk[i]
        return i
    batas = jendela_hari * 86400
    for k, i in enumerate(urut):            # single-link: gabungkan semua pasangan mirip dalam jendela waktu
        for j in reversed(urut[max(0, k - 400):k]):
            if pd.notna(t[i]) and pd.notna(t[j]) and (t[i] - t[j]).total_seconds() > batas:
                break
            if faktor.get(i) == faktor.get(j) and _mirip(tok[i], tok[j]):
                ri, rj = akar(i), akar(j)
                if ri == rj:
                    continue
                a0, b0 = t0[ri], t0[rj]
                if pd.notna(t[i]) and pd.notna(b0) and (t[i] - b0).total_seconds() > batas:
                    continue                    # kelompok j dimulai > 3 hari sebelum artikel ini
                induk[ri] = rj
                t0[rj] = min(x for x in (a0, b0) if pd.notna(x)) if (pd.notna(a0) or pd.notna(b0)) else b0
    ids, grup = {}, {}
    for i in urut:
        grup[i] = ids.setdefault(akar(i), len(ids))
    return pd.Series(grup).reindex(df.index).astype("Int64")


# ----------------------------------------------------------------------------
# Independensi sumber & konflik informasi dalam satu peristiwa
# ----------------------------------------------------------------------------
RX_RILIS = re.compile(
    r"siaran pers|press release|keterangan (?:tertulis|resmi)|dalam keterangan(?:nya)?|rilis (?:resmi|pers|yang diterima)|"
    r"said in a (?:statement|press release|filing)|in a (?:statement|press release)|according to a (?:statement|release)|"
    r"prnewswire|globe ?newswire|business ?wire|accesswire", re.I)
RX_KUTIP = re.compile(
    r"\b(?:dilansir|melansir|dikutip dari|mengutip|seperti dikutip|sebagaimana dikutip|seperti diberitakan|"
    r"as reported by|reported by (?:reuters|bloomberg)|according to (?:reuters|bloomberg|a report))\b", re.I)
RX_BANTAH = re.compile(
    r"\b(?:membantah|bantah|dibantah|menampik|ditampik|mengklarifikasi|meluruskan|hoaks|hoax|tidak benar|"
    r"denies|denied|deny|refutes?|refuted|dismiss(?:es|ed)? (?:the )?(?:report|rumou?r)s?|clarif(?:y|ies|ied))\b",
    re.I)
RX_ANGKA = re.compile(
    r"\b(laba|rugi|pendapatan|penjualan|kredit|dividen|npl|utang|profit|revenue|sales|loan|dividend|earnings|"
    r"net income)\b\D{0,28}?(\d+(?:[.,]\d+)?)\s?(%|persen|triliun|miliar|trillion|billion)", re.I)
ASAL_IKON = {"Liputan sendiri": "📰", "Siaran pers": "📣", "Salinan": "📋", "Resmi": "🛡️"}


def _norm_judul(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", str(t or "").lower())).strip()


def independensi(a: pd.DataFrame) -> dict:
    """Asal tiap artikel dalam satu peristiwa & jumlah sumber yang benar-benar independen.
    - Siaran pers: menyebut 'siaran pers / keterangan tertulis / said in a statement / PRNewswire' → semua artikel
      jenis ini dihitung SATU sumber asal (mengutip rilis yang sama), berapa pun medianya.
    - Salinan: 'dilansir / mengutip / as reported by', konten ANTARA yang dimuat ulang, atau judul/ringkasan hampir
      identik dengan artikel media lain → tidak menambah konfirmasi.
    - Liputan sendiri: selain itu (tiap media dihitung satu sumber independen). Dokumen resmi = sumber asal sendiri.
    Pembacaan memakai judul + ringkasan (isi lengkap artikel tidak diambil), jadi penanda di badan berita bisa
    terlewat."""
    txt = (a["judul"].fillna("") + " " + a["ringkasan"].fillna("")).astype(str)
    src = a["sumber"].fillna(a["domain"]).fillna("").astype(str)
    dom = a["domain"].fillna("").astype(str)
    resmi = (a["verifikasi"] == "Resmi").to_numpy()
    rilis = txt.str.contains(RX_RILIS).to_numpy()
    kutip = (txt.str.contains(RX_KUTIP) | (txt.str.contains(r"\(ANTARA\)", regex=True)
                                            & ~dom.str.contains("antaranews"))).to_numpy()
    nj = [_norm_judul(t) for t in a["judul"]]
    tok = [set(re.findall(r"[a-z0-9]{3,}", str(r).lower())) for r in a["ringkasan"].fillna("")]
    dup = np.zeros(len(a), dtype=bool)
    for k in range(len(a)):
        for m in range(k):
            if src.iloc[k] == src.iloc[m]:
                continue
            sama_judul = nj[k] and nj[k] == nj[m]
            sama_isi = len(tok[k]) >= 12 and len(tok[m]) >= 12 and len(tok[k] & tok[m]) / len(tok[k] | tok[m]) >= 0.7
            if sama_judul or sama_isi:
                dup[k] = True
                break
    asal = np.where(resmi, "Resmi", np.where(rilis, "Siaran pers", np.where(kutip | dup, "Salinan", "Liputan sendiri")))
    sendiri = asal == "Liputan sendiri"
    n_ind = int(src[sendiri].nunique()) + int(src[resmi].nunique()) + int(bool(rilis[~resmi].any()))
    if n_ind == 0 and len(a):
        n_ind = 1                                   # semuanya salinan: tetap ada satu sumber asal
    kred = a["verifikasi"].isin(["Resmi", "Media kredibel"]).to_numpy()
    n_kred = int(src[sendiri & kred].nunique()) + int(src[resmi].nunique()) + int(bool((rilis & kred & ~resmi).any()))
    hit = pd.Series(asal).value_counts()
    teks = " · ".join(f"{ASAL_IKON[k]} {v} {k.lower()}" for k, v in hit.items())
    info = [{"sumber": src.iloc[k], "url": str(a["url"].iloc[k]), "verifikasi": str(a["verifikasi"].iloc[k]),
             "asal": str(asal[k])} for k in range(min(len(a), 12))]
    return {"n_independen": n_ind, "n_kred_independen": n_kred, "asal": list(asal), "asal_teks": teks,
            "rilis": bool(rilis.any()), "salinan": bool((kutip | dup).any()), "sumber_info": info}


def _angka_utama(t: str) -> dict:
    out = {}
    for m in RX_ANGKA.finditer(str(t or "")):
        kw = m.group(1).lower()
        kw = {"profit": "laba", "earnings": "laba", "net income": "laba", "revenue": "pendapatan", "sales": "penjualan",
              "loan": "kredit", "dividend": "dividen"}.get(kw, kw)
        sat = m.group(3).lower()
        sat = {"persen": "%", "trillion": "triliun", "billion": "miliar"}.get(sat, sat)
        try:
            out.setdefault((kw, sat), float(m.group(2).replace(",", ".")))
        except ValueError:
            pass
    return out


def konflik(a: pd.DataFrame) -> str:
    """Tanda informasi yang saling bertentangan dalam satu peristiwa: arah dampak berlawanan antarsumber,
    bantahan/klarifikasi, atau angka utama (laba/pendapatan/kredit/dividen …) yang berbeda antarsumber."""
    if len(a) < 2:
        return ""
    src = a["sumber"].fillna(a["domain"]).fillna("").astype(str)
    out = []
    dm = pd.to_numeric(a["dampak"], errors="coerce").fillna(0)
    pos, neg = dm >= 0.15, dm <= -0.15
    if pos.any() and neg.any() and src[pos].nunique() >= 1 and src[neg].nunique() >= 1 and \
            src[pos | neg].nunique() >= 2:
        out.append(f"arah berbeda: {src[pos].nunique()} sumber positif vs {src[neg].nunique()} sumber negatif")
    txt = (a["judul"].fillna("") + " " + a["ringkasan"].fillna("")).astype(str)
    bantah = txt.str.contains(RX_BANTAH)
    if bantah.any() and (~bantah).any():
        out.append(f"ada bantahan/klarifikasi ({src[bantah].iloc[0]})")
    angka: dict = {}
    for t, sr in zip(a["judul"].fillna(""), src):
        for k, v in _angka_utama(t).items():
            angka.setdefault(k, {}).setdefault(v, sr)
    for (kw, sat), nilai in angka.items():
        vs = sorted(nilai)
        if len(vs) >= 2 and (vs[-1] - vs[0]) / max(abs(vs[-1]), 1e-9) > 0.1:
            f = lambda v: f"{v:g}{'%' if sat == '%' else ' ' + sat}"  # noqa: E731
            out.append(f"angka {kw} berbeda: {f(vs[0])} ({nilai[vs[0]]}) vs {f(vs[-1])} ({nilai[vs[-1]]})")
            break
    return "; ".join(out)


def ringkas_independensi(ev: pd.DataFrame) -> str:
    """Kalimat ringkas: berapa peristiwa multi-sumber yang benar-benar dikonfirmasi sumber independen, berapa yang
    hanya satu siaran pers / salinan, dan berapa yang informasinya bertentangan."""
    e = langsung(ev) if ev is not None and not ev.empty else ev
    if e is None or e.empty or "n_independen" not in e.columns:
        return ""
    multi = e[e["n_sumber"] >= 2]
    k = e["konfirmasi"].astype(str)
    n_ind = int((multi["n_independen"] >= 2).sum())
    n_ril = int(k.str.startswith("1 siaran pers").sum())
    n_sal = int(k.str.startswith("1 sumber asal").sum())
    n_kf = int((e["konflik"].fillna("") != "").sum())
    if multi.empty and not n_kf:
        return "semua peristiwa hanya dari satu sumber"
    teks = (f"{len(multi)} peristiwa diberitakan ≥ 2 media: {n_ind} dikonfirmasi ≥ 2 sumber independen"
            + (f", {n_ril} hanya mengutip 1 siaran pers" if n_ril else "")
            + (f", {n_sal} salinan dari 1 sumber" if n_sal else ""))
    return teks + (f" · ⚠️ {n_kf} peristiwa dengan informasi bertentangan" if n_kf else "")


def konfirmasi(ver: list[str], n_sumber: int, n_independen: int | None = None, n_kred_independen: int | None = None,
               rilis: bool = False) -> str:
    """Status konfirmasi peristiwa. Banyak media yang hanya mengutip satu siaran pers / menyalin satu laporan TIDAK
    dihitung sebagai konfirmasi independen."""
    n_ind = n_sumber if n_independen is None else n_independen
    n_kred = sum(v == "Media kredibel" for v in ver) if n_kred_independen is None else n_kred_independen
    if "Resmi" in ver:
        return "Terkonfirmasi sumber resmi"
    if all(v == "Rumor / belum terkonfirmasi" for v in ver):
        return "Rumor — belum terkonfirmasi"
    if n_ind >= 2 and n_kred >= 2:
        return f"Dikonfirmasi {n_ind} sumber independen"
    if n_ind >= 2:
        return f"Diberitakan {n_ind} sumber independen"
    if n_sumber >= 2 and rilis:
        return f"1 siaran pers, dikutip {n_sumber} media"
    if n_sumber >= 2:
        return f"1 sumber asal, disalin {n_sumber} media"
    return "Satu sumber"


def peristiwa(d: pd.DataFrame, pola_nama: list[str] | None = None, paruh: float = 14,
              acuan: pd.Timestamp | None = None) -> pd.DataFrame:
    """Artikel (sudah diperkaya) → tabel peristiwa unik dengan bobot w = R × M × Q × D."""
    kol = ["peristiwa", "judul", "url", "sumber", "terbit", "terbit_akhir", "n_artikel", "n_sumber", "sumber_list",
           "relasi", "R", "M", "Q", "D", "w", "skor", "label", "dampak", "dampak_label", "pendorong", "aspek",
           "verifikasi", "konfirmasi", "penjelasan", "faktor", "cakupan", "ringkasan", "artikel", "kaitan",
           "n_independen", "asal_sumber", "sumber_info", "konflik"]
    if d is None or d.empty:
        return pd.DataFrame(columns=kol)
    acuan = acuan or pd.Timestamp.now(tz="UTC")
    # Artikel dengan relasi 'Pencarian' tidak punya bukti kaitan; jangan ikut agregasi,
    # skor sentimen, peringatan dini, atau analisis reaksi harga.
    x = d[d["relasi"].fillna("") != "Pencarian"].copy()
    if x.empty:
        return pd.DataFrame(columns=kol)
    x["_g"] = gabung_peristiwa(x, pola_nama)
    x["_vr"] = x["verifikasi"].map({v: i for i, v in enumerate(VERIF_URUT)}).fillna(9)
    x["_rr"] = x["relasi"].map(RELASI_URUT).fillna(9)
    x["_google"] = x["url"].astype(str).str.contains("news.google.com", na=False)
    rows = []
    for g, a in x.groupby("_g", sort=False):
        a = a.sort_values(["_vr", "_rr", "relevansi", "_google", "terbit"],
                          ascending=[True, True, False, True, True], kind="stable")
        rep = a.iloc[0]
        q = a["Q"].astype(float)
        n_sumber = a["sumber"].fillna(a["domain"]).nunique()
        ind = independensi(a)
        kf = konflik(a)
        # bonus kualitas bukti hanya dari sumber kredibel yang INDEPENDEN (bukan salinan / siaran pers yang sama)
        Q = min(1.0, float(q.max()) + 0.05 * max(0, min(ind["n_kred_independen"], 4) - 1))
        if kf:
            Q *= 0.85                                  # informasi bertentangan → bukti kurang meyakinkan
        R = float(a["relevansi"].fillna(1).max())
        M = float(a["materialitas"].max())
        t0 = a["terbit"].min()
        umur = max(0.0, (acuan - t0).total_seconds() / 86400) if pd.notna(t0) else 0.0
        D = 0.5 ** (umur / max(paruh, 1))
        s = float(np.average(a["skor"].fillna(0).astype(float), weights=q))
        dm = float(np.average(a["dampak"].fillna(0).astype(float), weights=q))
        ver = list(a["verifikasi"])
        campuran = (a["dampak_label"] == "Campuran / belum pasti").all() or kf.startswith("arah berbeda")
        cak = sorted(set(a["cakupan"].dropna()))
        rows.append({
            "peristiwa": int(g), "judul": rep["judul"], "url": rep["url"], "sumber": rep["sumber"], "terbit": t0,
            "terbit_akhir": a["terbit"].max(), "n_artikel": len(a), "n_sumber": int(n_sumber),
            "sumber_list": [(r["sumber"], r["url"], r["verifikasi"]) for _, r in a.head(8).iterrows()],
            "relasi": rep["relasi"], "R": R, "M": M, "Q": round(Q, 2), "D": round(D, 3),
            "w": R * M * Q * D, "skor": round(s, 3), "label": label_dari(s), "dampak": round(dm, 3),
            "dampak_label": "Campuran / belum pasti" if campuran else label_dampak(dm),
            "pendorong": a["pendorong"].mode().iloc[0] if a["pendorong"].notna().any() else "Lainnya",
            "aspek": ", ".join(dict.fromkeys(x2.strip() for v in a["aspek"].fillna("") for x2 in str(v).split(",")
                                             if x2.strip()))[:80],
            "verifikasi": rep["verifikasi"],
            "konfirmasi": konfirmasi(ver, int(n_sumber), ind["n_independen"], ind["n_kred_independen"], ind["rilis"]),
            "penjelasan": rep["penjelasan"], "faktor": rep.get("faktor"), "cakupan": " & ".join(cak),
            "ringkasan": rep.get("ringkasan") or "", "artikel": list(a["id"]) if "id" in a.columns else [],
            "kaitan": rep.get("kaitan") or "", "n_independen": ind["n_independen"], "asal_sumber": ind["asal_teks"],
            "sumber_info": ind["sumber_info"], "konflik": kf})
    ev = pd.DataFrame(rows, columns=kol)
    return ev.sort_values("terbit", ascending=False, na_position="last").reset_index(drop=True)


# ----------------------------------------------------------------------------
# Skor, keyakinan, cakupan, kesegaran, risiko
# ----------------------------------------------------------------------------
BAND = [(20, "Sangat negatif", "#c0392b"), (40, "Negatif", "#e34948"), (60, "Netral", "#8a8a80"),
        (80, "Positif", "#2a78d6"), (101, "Sangat positif", "#1f5fae")]
MIN_PERISTIWA = 3


def band(s: float | None) -> tuple[str, str]:
    if s is None:
        return "Data tidak mencukupi", "#8a8a80"
    for batas, nama, warna in BAND:
        if s < batas:
            return nama, warna
    return BAND[-1][1], BAND[-1][2]


def langsung(ev: pd.DataFrame) -> pd.DataFrame:
    return ev[ev["relasi"].isin(["Langsung", "Entitas terkait"])] if not ev.empty else ev


def inti_risiko(ev: pd.DataFrame) -> pd.DataFrame:
    """Peristiwa yang cukup dekat untuk risiko & peringatan: menyebut emiten / entitas terkait (anak usaha, merek,
    induk), atau relevansi ≥ 0,55. Hasil pencarian lemah dan faktor eksternal tidak memicu peringatan."""
    e = langsung(ev)
    if e.empty:
        return e
    return e[e["relasi"].isin(["Langsung", "Entitas terkait"]) | (e["R"] >= 0.55)]


def skor_0_100(ev: pd.DataFrame) -> float | None:
    e = langsung(ev)
    if len(e) < MIN_PERISTIWA or e["w"].sum() <= 1e-6:
        return None
    return float(50 + 50 * (e["w"] * e["dampak"]).sum() / e["w"].sum())


def keyakinan(ev: pd.DataFrame) -> tuple[float | None, str, str]:
    e = langsung(ev)
    if e.empty:
        return None, "—", "Belum ada peristiwa."
    w = e["w"].clip(lower=1e-9)
    c_n = min(1.0, len(e) / 12)
    c_q = float(np.average(e["Q"], weights=w))
    mu = float(np.average(e["dampak"], weights=w))
    sd = float(np.sqrt(np.average((e["dampak"] - mu) ** 2, weights=w)))
    c_s = max(0.0, 1 - sd)
    c_v = float(w[(e["n_independen"] >= 2) | (e["verifikasi"] == "Resmi")].sum() / w.sum())
    c = 100 * (0.35 * c_n + 0.25 * c_q + 0.2 * c_s + 0.2 * c_v)
    lab = "Tinggi" if c >= 70 else ("Sedang" if c >= 45 else "Rendah")
    alasan = (f"{len(e)} peristiwa unik · kualitas bukti rata-rata {c_q:.0%} · kesepakatan arah {c_s:.0%} · "
              f"{c_v:.0%} bobot dari peristiwa resmi/multi-sumber")
    return round(c, 0), lab, alasan


def cakupan_sumber(d: pd.DataFrame, log: pd.DataFrame | None = None) -> dict:
    if d is None or d.empty:
        return {"label": "—", "penerbit": 0, "nasional": 0, "internasional": 0, "resmi": 0, "kanal_ok": 0,
                "kanal_gagal": 0, "teks": "Belum ada berita."}
    pen = d["sumber"].fillna(d["domain"])
    nas = pen[d["cakupan"] == "Nasional"].nunique()
    intl = pen[d["cakupan"] == "Internasional"].nunique()
    resmi = int((d.get("verifikasi") == "Resmi").sum()) if "verifikasi" in d.columns else 0
    ok = gagal = 0
    if log is not None and not log.empty:
        ok, gagal = int((log["Status"] == "OK").sum()), int((log["Status"] == "Gagal").sum())
    n = pen.nunique()
    lab = "Luas" if (n >= 10 and nas and intl) else ("Sedang" if n >= 4 else "Sempit")
    teks = f"{n} penerbit ({nas} nasional, {intl} internasional), {resmi} dokumen resmi"
    if ok or gagal:
        teks += f" · {ok} permintaan berhasil, {gagal} gagal"
    return {"label": lab, "penerbit": int(n), "nasional": int(nas), "internasional": int(intl), "resmi": resmi,
            "kanal_ok": ok, "kanal_gagal": gagal, "teks": teks}


def _umur_teks(detik: float) -> str:
    if detik < 90:
        return "baru saja"
    if detik < 3600:
        return f"{detik / 60:.0f} menit lalu"
    if detik < 86400 * 2:
        return f"{detik / 3600:.0f} jam lalu"
    return f"{detik / 86400:.0f} hari lalu"


def kesegaran(d: pd.DataFrame, waktu_refresh: pd.Timestamp | None) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    if waktu_refresh is None or pd.isna(waktu_refresh):
        return {"label": "Belum diambil", "teks": "Klik Refresh untuk mengambil berita.", "detik": None}
    t = pd.Timestamp(waktu_refresh)
    t = t.tz_localize("Asia/Jakarta").tz_convert("UTC") if t.tzinfo is None else t
    det = (now - t).total_seconds()
    lab = "Segar" if det <= 3600 else ("Cukup" if det <= 6 * 3600 else "Usang")
    teks = f"diperbarui {_umur_teks(det)}"
    if d is not None and not d.empty and d["terbit"].notna().any():
        teks += f" · berita terbaru {_umur_teks((now - d['terbit'].max()).total_seconds())}"
    return {"label": lab, "teks": teks, "detik": det}


RISIKO_URUT = ["Rendah", "Sedang", "Tinggi", "Kritis"]


def _p(t: str, n: int = 90) -> str:
    t = str(t or "")
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def tingkat_risiko(ev: pd.DataFrame, s: float | None) -> tuple[str, list[str]]:
    e = inti_risiko(ev)
    level, alasan = 0, []

    def naik(n, teks):
        nonlocal level
        level = max(level, n)
        alasan.append(teks)
    if e.empty:
        return "—", ["Belum ada peristiwa langsung."]
    kuat = e["verifikasi"].isin(["Resmi", "Media kredibel"]) | (e["n_independen"] >= 2)
    kredit = e[(e["pendorong"] == "Gagal bayar & restrukturisasi") & (e["dampak"] <= -0.4)]
    baru90 = e["terbit"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)
    k_kuat = kredit[kuat.loc[kredit.index]]
    if not k_kuat[baru90.loc[k_kuat.index]].empty:
        r0 = k_kuat[baru90.loc[k_kuat.index]].iloc[0]
        naik(3, f"Peristiwa gagal bayar/restrukturisasi terverifikasi ({_tgl(r0['terbit'])}): “{_p(r0['judul'])}”")
    elif not k_kuat.empty:
        r0 = k_kuat.iloc[0]
        naik(2, f"Pernah ada peristiwa gagal bayar/restrukturisasi ({_tgl(r0['terbit'])}): “{_p(r0['judul'])}”")
    elif not kredit.empty:
        naik(2, f"Ada kabar gagal bayar/restrukturisasi (belum terverifikasi): “{_p(kredit.iloc[0]['judul'])}”")
    rating = e[(e["pendorong"] == "Aksi rating") & (e["dampak"] <= -0.4)]
    if not rating.empty:
        naik(2, f"Aksi rating negatif: “{_p(rating.iloc[0]['judul'])}”")
    mat = e[(e["M"] >= 0.8) & (e["dampak"] <= -0.4) & kuat]
    if len(mat) >= 3 or (len(mat) >= 2 and s is not None and s < 45):
        naik(2, f"{len(mat)} peristiwa material negatif terverifikasi")
    elif len(mat) >= 1:
        naik(1, f"{len(mat)} peristiwa material negatif terverifikasi")
    hukum = e[e["pendorong"].isin(["Hukum & tata kelola", "Kebijakan & regulasi"]) & (e["dampak"] <= -0.3)]
    if len(hukum) >= 1:
        naik(1, f"{len(hukum)} isu hukum/regulasi bernada negatif")
    if s is not None:
        if s < 30:
            naik(2, f"Skor sentimen rendah ({s:.0f}/100)")
        elif s < 45:
            naik(1, f"Skor sentimen di bawah netral ({s:.0f}/100)")
    rumor = e[(e["konfirmasi"].str.startswith("Rumor")) & (e["M"] >= 0.8) & (e["dampak"] < 0)]
    if not rumor.empty:
        naik(1, "Ada rumor material negatif yang perlu diverifikasi")
    if not alasan:
        alasan.append("Tidak ada peristiwa material negatif; sentimen netral/positif.")
    return RISIKO_URUT[level], alasan


# ----------------------------------------------------------------------------
# Tren skor harian (untuk dibandingkan dengan harga)
# ----------------------------------------------------------------------------
def tren_skor(ev: pd.DataFrame, hari: int, paruh: float = 14) -> pd.DataFrame:
    """Skor 0–100 harian dari peristiwa dalam jendela bergulir (14 hari untuk periode ≤ 60 hari, 30 hari s.d. ±1 tahun,
    60 hari bila lebih panjang), plus jumlah peristiwa positif/negatif (menurut dampak) per hari."""
    e = langsung(ev)
    akhir = pd.Timestamp.now(tz="Asia/Jakarta").normalize()
    hari_idx = pd.date_range(akhir - pd.Timedelta(days=hari - 1), akhir, freq="D")
    kol = ["Tanggal", "Skor", "Peristiwa", "Positif", "Negatif", "Netral"]
    if e.empty:
        return pd.DataFrame({"Tanggal": hari_idx.tz_localize(None), "Skor": np.nan, "Peristiwa": 0, "Positif": 0,
                             "Negatif": 0, "Netral": 0})[kol]
    jd = 14 if hari <= 60 else (30 if hari <= 400 else 60)
    tl = e["terbit"].dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    tt = tl.to_numpy("datetime64[ns]")
    base = (e["R"] * e["M"] * e["Q"]).to_numpy(float)
    s = e["dampak"].to_numpy(float)
    lab = e["dampak"].map(label_dari).to_numpy()
    tgl = tl.dt.normalize().to_numpy("datetime64[ns]")
    out = []
    for d in hari_idx.tz_localize(None):
        ujung = (d + pd.Timedelta(days=1)).to_datetime64()
        m = (tt < ujung) & (tt >= ujung - np.timedelta64(jd, "D"))
        if m.sum() >= 1:
            umur = (ujung - tt[m]) / np.timedelta64(1, "D")
            w = base[m] * 0.5 ** (umur / paruh)
            sk = 50 + 50 * float((w * s[m]).sum() / w.sum()) if w.sum() > 0 else np.nan
        else:
            sk = np.nan
        h = tgl == d.to_datetime64()
        out.append({"Tanggal": d, "Skor": sk, "Peristiwa": int(h.sum()), "Positif": int((h & (lab == "Positif")).sum()),
                    "Negatif": int((h & (lab == "Negatif")).sum()), "Netral": int((h & (lab == "Netral")).sum())})
    return pd.DataFrame(out)[kol]


# ----------------------------------------------------------------------------
# Peringatan dini
# ----------------------------------------------------------------------------
@dataclass
class Peringatan:
    tingkat: str        # Kritis / Tinggi / Sedang / Info
    jenis: str
    judul: str
    detail: str
    url: str = ""
    waktu: object = None
    kunci: str = ""     # untuk mencegah notifikasi ganda
    extra: dict = field(default_factory=dict)
    berita: list = field(default_factory=list)   # berita/peristiwa pemicu: [{judul, sumber, waktu, url, ...}]


def _jkt(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return (t.tz_convert("Asia/Jakarta") if t.tzinfo else t.tz_localize("UTC").tz_convert("Asia/Jakarta"))


def item_berita(r) -> dict:
    """Satu peristiwa → baris rincian peringatan (dipakai di dashboard, database, dan notifikasi)."""
    lain = r.get("sumber_list") if isinstance(r.get("sumber_list"), list) else []
    t = r.get("terbit")
    return {"judul": str(r.get("judul") or ""), "sumber": str(r.get("sumber") or ""), "url": str(r.get("url") or ""),
            "waktu": pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None and not pd.isna(t) else "",
            "dampak": str(r.get("dampak_label") or ""), "skor": round(float(r.get("dampak") or 0), 2),
            "kategori": str(r.get("pendorong") or ""), "verifikasi": str(r.get("konfirmasi") or ""),
            "relasi": str(r.get("relasi") or ""), "n_sumber": int(r.get("n_sumber") or 1),
            "n_independen": int(r.get("n_independen") or 1), "konflik": str(r.get("konflik") or ""),
            "lain": [{"sumber": str(a[0]), "url": str(a[1])} for a in lain[1:6]]}


def _negatif(e: pd.DataFrame) -> pd.Series:
    return e["dampak"].map(label_dari) == "Negatif"


def pemicu(jenis: str, ev: pd.DataFrame, waktu=None, url: str = "", judul: str = "", maks: int = 60) -> list[dict]:
    """Berita/peristiwa yang memicu sebuah peringatan (juga untuk merekonstruksi rincian peringatan lama).
    Lonjakan berita negatif → semua peristiwa negatif 3 hari kalender (WIB) sampai `waktu`;
    Sentimen turun tajam → peristiwa negatif 7 hari terakhir, yang bobot × dampaknya terbesar dulu;
    jenis lain → peristiwa itu sendiri (dicari lewat URL/judul) beserta sumber lain yang memberitakannya."""
    e = inti_risiko(ev)
    if e.empty:
        return []
    akhir = _jkt(waktu if waktu is not None else pd.Timestamp.now(tz="UTC"))
    tj = e["terbit"].map(_jkt)
    if jenis == "Lonjakan berita negatif":
        m = _negatif(e) & (tj.dt.normalize() >= akhir.normalize() - pd.Timedelta(days=2)) & (tj <= akhir + pd.Timedelta(hours=1))
        x = e[m].sort_values("terbit", ascending=False)
    elif jenis == "Sentimen turun tajam":
        m = _negatif(e) & (tj > akhir - pd.Timedelta(days=7)) & (tj <= akhir + pd.Timedelta(hours=1))
        x = e[m].assign(_b=lambda d: d["w"] * d["dampak"].abs()).sort_values("_b", ascending=False)
    else:
        x = e[(e["url"] == url)] if url else e.iloc[0:0]
        if x.empty and judul:
            x = e[e["judul"] == judul]
    return [item_berita(r) for r in x.head(maks).to_dict("records")]


def peringatan(nama: str, ev: pd.DataFrame, tren: pd.DataFrame | None = None, jam_baru: float = 72) -> list[Peringatan]:
    """Peringatan dini dari peristiwa yang cukup dekat dengan emiten (inti_risiko). Setiap peringatan membawa daftar
    berita pemicunya (`berita`), jadi "27 peristiwa negatif" selalu bisa dibuka satu per satu."""
    e = inti_risiko(ev)
    out: list[Peringatan] = []
    if e.empty:
        return out
    now = pd.Timestamp.now(tz="UTC")
    baru = e[e["terbit"] >= now - pd.Timedelta(hours=jam_baru)]
    for r in baru.to_dict("records"):
        kuat = r["verifikasi"] in ("Resmi", "Media kredibel") or r["n_independen"] >= 2
        isi = [item_berita(r)]
        if r["pendorong"] == "Gagal bayar & restrukturisasi" and r["dampak"] <= -0.4:
            out.append(Peringatan("Kritis" if kuat else "Tinggi", "Peristiwa kredit", r["judul"],
                                  f"{r['konfirmasi']} · {r['sumber']}", r["url"], r["terbit"],
                                  f"{nama}|kredit|{r['peristiwa']}|{r['judul'][:60]}", berita=isi))
        elif r["M"] >= 0.8 and r["dampak"] <= -0.4:
            out.append(Peringatan("Tinggi" if kuat else "Sedang", "Berita material negatif", r["judul"],
                                  f"{r['pendorong']} · {r['konfirmasi']} · {r['sumber']}", r["url"], r["terbit"],
                                  f"{nama}|material|{r['judul'][:60]}", berita=isi))
        elif r["pendorong"] in ("Hukum & tata kelola", "Kebijakan & regulasi") and r["dampak"] <= -0.3:
            out.append(Peringatan("Sedang", "Hukum / regulasi", r["judul"],
                                  f"{r['pendorong']} · {r['konfirmasi']} · {r['sumber']}", r["url"], r["terbit"],
                                  f"{nama}|hukum|{r['judul'][:60]}", berita=isi))
        if str(r["konfirmasi"]).startswith("Rumor") and r["M"] >= 0.8:
            out.append(Peringatan("Info", "Rumor material", r["judul"], "Belum terkonfirmasi — cek sumber resmi.",
                                  r["url"], r["terbit"], f"{nama}|rumor|{r['judul'][:60]}", berita=isi))
    if tren is not None and not tren.empty and tren["Skor"].notna().sum() >= 2:
        sk = tren.dropna(subset=["Skor"])
        kini = sk.iloc[-1]
        lalu = sk[sk["Tanggal"] <= kini["Tanggal"] - pd.Timedelta(days=7)]
        if not lalu.empty and kini["Skor"] - lalu.iloc[-1]["Skor"] <= -15:
            pm = pemicu("Sentimen turun tajam", ev, now, maks=20)
            out.append(Peringatan("Tinggi", "Sentimen turun tajam",
                                  f"Skor sentimen turun {lalu.iloc[-1]['Skor'] - kini['Skor']:.0f} poin dalam 7 hari",
                                  f"{lalu.iloc[-1]['Skor']:.0f} → {kini['Skor']:.0f} (skala 0–100) · "
                                  f"{len(pm)} peristiwa negatif dalam 7 hari", "",
                                  now, f"{nama}|turun|{kini['Tanggal']:%Y-%m-%d}", berita=pm))
    # lonjakan berita negatif: dihitung dari peristiwa yang sama dengan daftar pemicunya (jumlahnya selalu cocok)
    pm = pemicu("Lonjakan berita negatif", ev, now)
    hari_p = len(tren) if tren is not None and not tren.empty else \
        max(1, int((now - e["terbit"].min()).total_seconds() // 86400) + 1)
    n_neg = int(_negatif(e).sum())
    rata = n_neg / max(hari_p, 1) * 3
    if len(pm) >= 3 and len(pm) >= 2 * max(rata, 0.5):
        n_kuat = sum(1 for b in pm if b.get("n_independen", 1) >= 2 or
                     b["verifikasi"].startswith(("Terkonfirmasi", "Dikonfirmasi")))
        out.append(Peringatan("Sedang", "Lonjakan berita negatif",
                              f"{len(pm)} peristiwa negatif dalam 3 hari terakhir",
                              f"Rata-rata periode ≈ {rata:.1f} per 3 hari · {n_kuat} dikonfirmasi resmi / ≥ 2 sumber "
                              "independen",
                              "", now, f"{nama}|lonjakan|{_jkt(now):%Y-%m-%d}", berita=pm))
    urut = {"Kritis": 0, "Tinggi": 1, "Sedang": 2, "Info": 3}
    out.sort(key=lambda p: (urut.get(p.tingkat, 9), -(pd.Timestamp(p.waktu).value if p.waktu is not None else 0)))
    return out


# ----------------------------------------------------------------------------
# Global Impact Radar
# ----------------------------------------------------------------------------
def radar_faktor(ev_faktor: pd.DataFrame, sektor: str) -> pd.DataFrame:
    """Ringkasan per faktor: arah terbaru, sensitivitas, dampak bersih, penjelasan."""
    rows = []
    for f in faktor_sektor(sektor):
        g = ev_faktor[ev_faktor["faktor"] == f["faktor"]] if not ev_faktor.empty else ev_faktor
        sens_txt = {1: "Menguntungkan bila naik", -1: "Merugikan bila naik", 0: "Campuran"}[f["sensitivitas"]]
        if g is None or g.empty:
            rows.append({"Faktor": f["faktor"], "Sensitivitas": sens_txt, "Peristiwa": 0, "Arah terbaru": "—",
                         "Dampak": None, "Dampak emiten": "Belum ada berita", "Mekanisme": f["mekanisme"],
                         "Berita terbaru": "", "URL": ""})
            continue
        top = g.sort_values("terbit", ascending=False).iloc[0]
        kode = _kode_faktor(f["faktor"])
        arah = gerak_faktor(top["judul"], kode)
        w = g["w"].clip(lower=1e-9)
        dm = float(np.average(g["dampak"], weights=w))
        lab = "Campuran / belum pasti" if f["sensitivitas"] == 0 else label_dampak(dm)
        rows.append({"Faktor": f["faktor"], "Sensitivitas": sens_txt, "Peristiwa": len(g),
                     "Arah terbaru": {1: "▲ naik/menguat", -1: "▼ turun/melemah", 0: "■ stabil/tidak jelas"}[arah],
                     "Dampak": round(dm, 2), "Dampak emiten": lab, "Mekanisme": f["mekanisme"],
                     "Berita terbaru": top["judul"], "URL": top["url"]})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Ringkasan berbasis aturan & Ask AI lokal
# ----------------------------------------------------------------------------
def _tgl(t) -> str:
    bln = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    if t is None or pd.isna(t):
        return "-"
    t = pd.Timestamp(t)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Jakarta")
    return f"{t.day} {bln[t.month - 1]} {t.year}"


def referensi(ev: pd.DataFrame, n: int = 40) -> list[dict]:
    """Daftar referensi bernomor (peristiwa terpenting dulu) untuk AI & laporan."""
    if ev.empty:
        return []
    e = ev.assign(_p=ev["w"] * (0.3 + ev["dampak"].abs())).sort_values("_p", ascending=False).head(n)
    out = []
    for i, (_, r) in enumerate(e.iterrows(), start=1):
        out.append({"no": i, "judul": r["judul"], "url": r["url"], "sumber": r["sumber"], "tanggal": _tgl(r["terbit"]),
                    "label": r["label"], "dampak": r["dampak_label"], "pendorong": r["pendorong"],
                    "relasi": r["relasi"], "verifikasi": r["konfirmasi"], "ringkasan": r.get("ringkasan") or "",
                    "penjelasan": r.get("penjelasan") or "", "faktor": r.get("faktor") or ""})
    return out


def ringkasan_aturan(nama: str, ev: pd.DataFrame, s: float | None, risiko: tuple[str, list[str]],
                     periode: str) -> str:
    e = langsung(ev)
    if e.empty:
        return f"Belum ada peristiwa tentang {nama} dalam {periode}."
    pos = e[e["dampak"] >= 0.15].sort_values("w", ascending=False)
    neg = e[e["dampak"] <= -0.15].sort_values("w", ascending=False)
    b = band(s)[0]
    teks = [f"Dalam {periode} terdapat **{len(e)} peristiwa unik** tentang {nama} "
            f"({int(e['n_artikel'].sum())} artikel). Skor sentimen "
            + (f"**{s:.0f}/100 ({b.lower()})**" if s is not None else "**belum dapat disimpulkan** (data sedikit)")
            + f", tingkat risiko pemberitaan **{risiko[0]}**."]
    if not neg.empty:
        k = neg.groupby("pendorong")["w"].sum().sort_values(ascending=False).index[:2]
        teks.append(f"Penekan utama: **{', '.join(k)}** — mis. “{neg.iloc[0]['judul']}” ({neg.iloc[0]['sumber']}).")
    if not pos.empty:
        k = pos.groupby("pendorong")["w"].sum().sort_values(ascending=False).index[:2]
        teks.append(f"Pendukung utama: **{', '.join(k)}** — mis. “{pos.iloc[0]['judul']}” ({pos.iloc[0]['sumber']}).")
    return " ".join(teks)


_KATA_TANYA = set("apa apakah bagaimana kenapa mengapa siapa kapan berapa yang dan di ke dari untuk dengan ini itu "
                  "saham emiten berita tentang soal terkait ada tolong jelaskan dong sih kah the what why how is are "
                  "of about any".split())


def jawab_lokal(pertanyaan: str, ref: list[dict]) -> str:
    """Jawaban tanpa LLM: cari peristiwa tersimpan yang paling cocok dengan pertanyaan. Tidak mengarang fakta."""
    if not ref:
        return "Belum ada data berita yang terkumpul untuk emiten ini. Klik **Refresh** dulu."
    q = pertanyaan.lower()
    kata = {w for w in re.findall(r"[a-z0-9]+", q) if w not in _KATA_TANYA and len(w) >= 3}
    want = None
    if re.search(r"negatif|buruk|risiko|masalah|turun|ancam|bahaya|kasus|gugat", q):
        want = "neg"
    elif re.search(r"positif|bagus|baik|naik|peluang|dukung", q):
        want = "pos"
    skor = []
    for r in ref:
        teks = f"{r['judul']} {r['ringkasan']} {r['pendorong']} {r['penjelasan']} {r['faktor']}".lower()
        cocok = sum(w in teks for w in kata)
        if want == "neg" and r["label"] == "Negatif" or want == "neg" and r["dampak"] == "Merugikan":
            cocok += 1.5
        if want == "pos" and (r["label"] == "Positif" or r["dampak"] == "Menguntungkan"):
            cocok += 1.5
        skor.append((cocok, -r["no"], r))
    skor.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = [r for c, _, r in skor if c > 0][:6]
    if not top:
        return ("Tidak ada berita terkumpul yang menjawab pertanyaan itu. Coba kata kunci lain, perpanjang periode, "
                "atau klik Refresh. (Jawaban hanya disusun dari data yang dikumpulkan aplikasi.)")
    baris = [f"Ditemukan {len(top)} peristiwa terkumpul yang paling relevan:"]
    for r in top:
        baris.append(f"- **[{r['no']}]** {r['tanggal']} · {r['sumber']} — {r['judul']} "
                     f"*(sentimen {r['label'].lower()}, dampak: {r['dampak'].lower()}; {r['verifikasi'].lower()})*. "
                     f"{r['penjelasan']}")
    baris.append("\n_Mode tanpa AI: daftar di atas dipilih berdasarkan kecocokan kata. Isi kunci Claude API di "
                 "Pengaturan untuk jawaban naratif (tetap hanya dari data ini)._")
    return "\n".join(baris)
