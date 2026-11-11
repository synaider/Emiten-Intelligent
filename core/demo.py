"""
Data simulasi untuk MODE DEMO. Semua perusahaan, berita, dan media di sini FIKTIF — hanya untuk
mencoba tampilan aplikasi tanpa internet. Mode demo memakai database terpisah (data/demo.db).
"""
from __future__ import annotations

import random
import zlib

import pandas as pd

from .emiten import KOLOM
from .rating import arah
from .sumber import id_artikel

EMITEN_DEMO = [
    # nama, kode, entitas, sektor, rating lama, rating baru, tgl berubah (hari lalu), outlook, kecenderungan
    ("DEMO BANK NUSANTARA", "DBNU", "PT Bank Nusantara Contoh Tbk", "Perbankan", "idAA+", "idAAA", 40, "Stable", 0.45),
    ("DEMO KARYA KONSTRUKSI", "DKKR", "PT Karya Konstruksi Contoh (Persero) Tbk", "Konstruksi BUMN", "idBBB",
     "idBB+", 25, "Negative", -0.55),
    ("DEMO ENERGI LISTRIK", "DELN", "PT Energi Listrik Contoh (Persero)", "Energi & Utilitas", "idAAA", "idAAA",
     None, "Stable", 0.15),
    ("DEMO MULTIFINANCE", "DMFN", "PT Multifinance Contoh", "Multifinance", "idA", "idA", None, "Stable", -0.05),
    ("DEMO TELEKOMUNIKASI", "DTLK", "PT Telekomunikasi Contoh Tbk", "Telekomunikasi", "idAA", "idAA+", 70,
     "Stable", 0.3),
    ("DEMO BANK DAERAH", "DBDA", "PT Bank Daerah Contoh", "Bank Daerah", "idA+", "idA", 15, "Negative", -0.35),
    ("DEMO SEMEN", "DSMN", "PT Semen Contoh (Persero) Tbk", "Industri Dasar", "idAA-", "idAA-", None, "Stable", 0.0),
    ("DEMO TAMBANG", "DTMB", "PT Tambang Contoh Tbk", "Pertambangan", "idA-", "idA-", None, "Positive", 0.25),
]

MEDIA = [("Harian Ekonomi (contoh)", "harian-ekonomi.contoh.id", "id", "Nasional"),
         ("Portal Pasar Modal (contoh)", "pasarmodal.contoh.id", "id", "Nasional"),
         ("Kantor Berita Nasional (contoh)", "kantorberita.contoh.id", "id", "Nasional"),
         ("Majalah Bisnis (contoh)", "majalahbisnis.contoh.id", "id", "Nasional"),
         ("Global Wire (example)", "globalwire.example.com", "en", "Internasional"),
         ("Asia Finance Daily (example)", "asiafinance.example.com", "en", "Internasional"),
         ("Jakarta English Daily (example)", "jakartadaily.example.id", "en", "Nasional")]

POS_ID = ["Laba bersih {n} naik 18% pada kuartal III", "{n} raih kontrak baru Rp2,1 triliun",
          "{n} lunasi obligasi jatuh tempo tepat waktu", "Penerbitan sukuk {n} oversubscribed 2,4 kali",
          "{n} bagikan dividen interim, kinerja solid", "NPL {n} turun, kualitas aset membaik",
          "Pendapatan {n} tumbuh dua digit sepanjang 9 bulan"]
NEG_ID = ["Laba {n} anjlok 35% tertekan beban bunga", "{n} digugat PKPU oleh vendor",
          "Kejagung periksa direksi {n} terkait dugaan korupsi proyek", "Utang jatuh tempo {n} membengkak, "
          "likuiditas ketat", "{n} ajukan restrukturisasi utang ke kreditur", "Rugi bersih {n} melebar",
          "Proyek {n} mangkrak, arus kas tertekan"]
NET_ID = ["{n} gelar RUPS luar biasa pekan depan", "{n} tunjuk direktur keuangan baru",
          "{n} buka kantor cabang di Makassar", "Jadwal paparan publik {n}"]
POS_EN = ["{n} profit rises 15% on strong loan growth", "{n} secures $300 million syndicated loan",
          "{n} wins contract for new toll road"]
NEG_EN = ["{n} shares slump as debt concerns mount", "{n} faces lawsuit over missed payment",
          "Fitch places {n} on negative outlook amid liquidity stress"]
NET_EN = ["{n} appoints new chief executive", "{n} to hold investor day in Jakarta"]


ANAK = {"DBNU": "Nusantara Syariah", "DKKR": "Karya Beton Contoh", "DELN": "Listrik Hijau Contoh",
        "DMFN": "Multifinance Syariah Contoh", "DTLK": "Seluler Contoh", "DBDA": "Daerah Syariah Contoh",
        "DSMN": "Semen Timur Contoh", "DTMB": "Emas Tambang Contoh"}


def _pendek(ent: str) -> str:
    return ent.replace("PT ", "").replace(" Tbk", "").replace(" (Persero)", "")


def emiten_demo() -> pd.DataFrame:
    rows = []
    for nama, kode, ent, sek, *_ in EMITEN_DEMO:
        pendek = _pendek(ent)
        rows.append({"Aktif": True, "Nama": nama, "Kode": kode, "Entitas": ent, "Sektor": sek,
                     "Lembaga Utama": "PEFINDO", "Alias": f"{pendek}; {kode}", "Terkait": ANAK.get(kode, ""),
                     "Kueri": f'"{pendek}"; {kode}', "Pengecualian": "", "Website IR": "", "Kode AS": ""})
    return pd.DataFrame(rows, columns=KOLOM)


def rating_demo() -> pd.DataFrame:
    hari_ini = pd.Timestamp.now().normalize()
    rows = []
    for nama, kode, ent, sek, lama, baru, h, ol, _ in EMITEN_DEMO:
        rows.append({"Nama": nama, "Lembaga": "PEFINDO", "Tanggal": hari_ini - pd.Timedelta(days=400),
                     "Rating": lama, "Outlook": "Stable", "Aksi": "Afirmasi", "Keterangan": "Data demo",
                     "Sumber": "DEMO"})
        if h is not None:
            aksi = arah(lama, baru)
            rows.append({"Nama": nama, "Lembaga": "PEFINDO", "Tanggal": hari_ini - pd.Timedelta(days=h),
                         "Rating": baru, "Outlook": ol, "Aksi": aksi, "Keterangan": "Data demo", "Sumber": "DEMO"})
        else:
            rows.append({"Nama": nama, "Lembaga": "PEFINDO", "Tanggal": hari_ini - pd.Timedelta(days=60),
                         "Rating": baru, "Outlook": ol, "Aksi": "Afirmasi", "Keterangan": "Data demo",
                         "Sumber": "DEMO"})
    return pd.DataFrame(rows)


def berita_demo(seed: int = 7, hari: int = 400) -> pd.DataFrame:
    """Berita fiktif: tiap peristiwa diberitakan 1–3 media (untuk uji penggabungan peristiwa), plus dokumen resmi,
    rumor, berita anak usaha (entitas terkait), dan berita faktor global per sektor."""
    from .intel import faktor_sektor
    from .sumber import K_FAKTOR, K_RESMI
    rnd = random.Random(seed)
    now = pd.Timestamp.now(tz="UTC")
    rows = []

    def tambah(nama, judul, media, t, kanal, rel=1.0, relasi="Langsung", faktor=None, ringkasan=""):
        url = f"https://{media[1]}/berita/{zlib.crc32((judul + media[1] + str(t.date())).encode()) % 10 ** 7}"
        rows.append({"id": id_artikel(judul + str(t.date()), url), "emiten": nama, "judul": judul,
                     "ringkasan": ringkasan, "url": url, "sumber": media[0], "domain": media[1], "bahasa": media[2],
                     "cakupan": media[3], "kanal": kanal, "terbit": t, "relevansi": rel, "relasi": relasi,
                     "faktor": faktor})

    for nama, kode, ent, sek, lama, baru, h, ol, cond in EMITEN_DEMO:
        pendek = _pendek(ent)
        n_ev = rnd.randint(26, 40)
        for _ in range(n_ev):
            umur = rnd.random() ** 1.5 * hari
            c = cond
            if h is not None and h - 5 <= umur <= h + 60:
                c = 0.7 if arah(lama, baru) == "Naik" else (-0.7 if arah(lama, baru) == "Turun" else cond)
            u = rnd.random()
            jenis = "pos" if u < 0.33 + c / 2 else ("neg" if u > 0.67 + c / 2 else "net")
            en = rnd.random() < 0.3
            pool = ({"pos": POS_EN, "neg": NEG_EN, "net": NET_EN} if en else
                    {"pos": POS_ID, "neg": NEG_ID, "net": NET_ID})[jenis]
            judul = rnd.choice(pool).format(n=pendek if rnd.random() < 0.7 else kode)
            t = now - pd.Timedelta(days=umur, hours=rnd.randint(0, 12))
            media_pool = [m for m in MEDIA if (m[2] == "en") == en]
            for k, media in enumerate(rnd.sample(media_pool, k=min(len(media_pool), rnd.choice([1, 1, 2, 3])))):
                j2 = judul if k == 0 else (judul + rnd.choice([", analis cermati", " — simak rinciannya", ""]))
                tambah(nama, j2, media, t + pd.Timedelta(hours=3 * k),
                       rnd.choice(["Google News · Indonesia", "Bing News · Indonesia", "GDELT (global)", "RSS media"]),
                       1.0 if rnd.random() < 0.85 else 0.6)
        # dokumen resmi (fiktif) & rumor & anak usaha
        resmi = ("Keterbukaan Informasi (contoh)", "bursa.contoh.id", "id", "Nasional")
        for umur, j in ((rnd.uniform(2, 20), f"[Keterbukaan Informasi] {kode}: Laporan keuangan interim kuartal III"),
                        (rnd.uniform(30, 120), f"[Keterbukaan Informasi] {kode}: Hasil RUPS tahunan & pembagian dividen")):
            tambah(nama, j, resmi, now - pd.Timedelta(days=umur), K_RESMI, 0.8)
        forum = ("Forum Saham (contoh)", "forumsaham.contoh.id", "id", "Nasional")
        tambah(nama, f"{pendek} dikabarkan akan rights issue besar, kata sumber yang tidak mau disebut namanya",
               forum, now - pd.Timedelta(days=rnd.uniform(1, 6)), "Google News · Indonesia")
        anak = ANAK.get(kode)
        if anak:
            tambah(nama, rnd.choice([f"{anak} catat pertumbuhan pendapatan 14%", f"{anak} raih pendanaan baru",
                                     f"{anak} digugat mitra usaha"]), rnd.choice(MEDIA[:4]),
                   now - pd.Timedelta(days=rnd.uniform(1, 25)), "Google News · Indonesia", 0.7, "Entitas terkait")
        if h is not None:
            aksi = "raised" if arah(lama, baru) == "Naik" else "lowered"
            judul = (f"Rating agency (example) has {aksi} the corporate rating of {ent} ({kode}) to {baru} from {lama}"
                     + (f" with {ol.lower()} outlook" if ol != "Stable" else ""))
            t = now - pd.Timedelta(days=h)
            rows.append({"id": id_artikel(judul, kode), "emiten": nama, "judul": judul,
                         "ringkasan": f"Aksi rating: {arah(lama, baru)} · rating {baru}",
                         "url": f"https://rating.contoh.id/aksi/{kode.lower()}", "sumber": "Lembaga Rating (contoh)",
                         "domain": "rating.contoh.id", "bahasa": "en", "cakupan": "Nasional",
                         "kanal": "PEFINDO (aksi rating)", "terbit": t, "relevansi": 1.0, "relasi": "Langsung",
                         "faktor": None})
        # faktor global sektor
        for f in faktor_sektor(sek):
            for _ in range(rnd.randint(1, 3)):
                naik = rnd.random() < 0.5
                p = rnd.choice([1.2, 2.5, 3.8, 5.1])
                kata = {"BI_RATE": ("BI Rate naik 25 bps menjadi 6%", "BI Rate dipangkas 25 bps menjadi 5,5%"),
                        "FED": ("The Fed naikkan suku bunga 25 bps", "The Fed pangkas suku bunga 25 bps"),
                        "RUPIAH": ("Rupiah menguat ke 15.900 per dolar AS", "Rupiah melemah ke 16.500 per dolar AS"),
                        "KREDIT": ("Pertumbuhan kredit perbankan naik ke 11%", "Pertumbuhan kredit perbankan melambat"),
                        "INFLASI": ("Inflasi naik ke 3,1% yoy", "Inflasi turun ke 2,2% yoy"),
                        }.get(f["kode"], (f"{f['faktor']} naik {p}% dalam sepekan",
                                          f"{f['faktor']} turun {p}% dalam sepekan"))
                judul = (kata[0] if naik else kata[1]) + " (contoh)"
                tambah(nama, judul, rnd.choice(MEDIA), now - pd.Timedelta(days=rnd.uniform(0.5, 28)), K_FAKTOR,
                       0.3, "Tidak langsung", f["faktor"])
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=["id", "emiten"]).reset_index(drop=True)


def indeks_demo(hari: int = 400) -> pd.DataFrame:
    """IHSG fiktif (random walk) untuk mode demo."""
    import numpy as np
    rng = np.random.default_rng(20261110)
    tg = pd.bdate_range(end=pd.Timestamp.now(tz="Asia/Jakarta").tz_localize(None).normalize(), periods=int(hari * 0.7))
    r = rng.normal(0.0002, 0.009, len(tg))
    return pd.DataFrame({"Tanggal": tg, "Close": 7200 * np.cumprod(1 + r), "Volume": np.nan})


def harga_demo(kode: str, hari: int = 400) -> pd.DataFrame:
    """Harga saham fiktif: ikut IHSG fiktif (beta ±1) + gerak khusus emiten."""
    import numpy as np
    cond = next((c for _, k, *rest, c in EMITEN_DEMO if k == kode), 0.0)
    rng = np.random.default_rng(zlib.crc32(kode.encode()))
    idx = indeks_demo(hari)
    r_m = idx["Close"].pct_change().fillna(0).to_numpy()
    beta = 0.7 + 0.6 * rng.random()
    r = beta * r_m + rng.normal(0.0004 * cond * 2, 0.013, len(idx))
    return pd.DataFrame({"Tanggal": idx["Tanggal"], "Close": (2500 + 3000 * rng.random()) * np.cumprod(1 + r),
                         "Volume": rng.integers(5_000_000, 60_000_000, len(idx)).astype(float)})
