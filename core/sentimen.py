"""
Analisis sentimen berita terhadap KUALITAS KREDIT emiten.

Tiga mesin (bisa dipilih di aplikasi):
  1. "Kamus keuangan"  (bawaan, cepat, tanpa instal tambahan)
     Kamus frasa keuangan Indonesia + Inggris: peristiwa kredit (gagal bayar, PKPU, pailit), aksi rating,
     arah metrik (laba naik = positif, NPL naik = negatif, beban turun = positif), hukum, ekspansi, dll.
     Menangani negasi ("membantah gagal bayar", "terhindar dari PKPU").
  2. "IndoBERT + FinBERT (lokal)"  (perlu: pip install -r requirements-ai.txt, unduh model sekali ~1,7 GB)
     - Bahasa Indonesia: apriandito/indobert-sentiment-classifier (context-conditioned: konteks = nama emiten)
     - Bahasa Inggris  : ProsusAI/finbert
     Hasil model digabung dengan kamus (kamus tetap menentukan kategori pendorong).
  3. "Claude API"  (perlu ANTHROPIC_API_KEY; berbayar per pemakaian)
     Menilai sentimen terhadap risiko kredit perusahaan yang disebut, kategori pendorong, alasan singkat,
     dan relevansi berita.

Semua mesin menghasilkan: skor (-1..+1), label (Positif/Netral/Negatif), pendorong, alasan.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

# ----------------------------------------------------------------------------
# Kategori pendorong (driver) + bobot untuk skor risiko kredit
# ----------------------------------------------------------------------------
PENDORONG = {
    "Aksi rating": 2.0,
    "Gagal bayar & restrukturisasi": 2.0,
    "Hukum & tata kelola": 1.3,
    "Utang & likuiditas": 1.5,
    "Kinerja keuangan": 1.3,
    "Kebijakan & regulasi": 1.0,
    "Ekspansi & bisnis": 0.9,
    "Aksi korporasi & manajemen": 0.8,
    "Pasar saham": 0.5,
    "Lainnya": 0.7,
}

_KAT = [  # urutan = prioritas
    ("Aksi rating", r"\b(peringkat|pemeringkat|rating|outlook|pefindo|fitch|moody'?s|s&p|standard & poor|creditwatch|"
                    r"idaaa|idaa|ida\b|idbbb|id[abcd][+-]?\b|\(idn\)|upgrade|downgrade|afirmasi|affirm\w*)"),
    ("Gagal bayar & restrukturisasi", r"\b(gagal bayar|default|pkpu|penundaan kewajiban|pailit|kepailitan|bangkrut|"
                                      r"insolven\w*|bankrupt\w*|restrukturisasi|wanprestasi|tunda bayar|"
                                      r"penundaan pembayaran|missed (coupon|payment)|homologasi|debt restructuring)"),
    ("Hukum & tata kelola", r"\b(korupsi|kpk|kejagung|kejaksaan|tersangka|terdakwa|penyidik\w*|penyelidik\w*|"
                            r"gugat\w*|digugat|menggugat|pembobolan|dibobol|sidang|pengadilan|vonis|fraud|penggelapan|manipulasi|suap|sanksi|denda|"
                            r"pemeriksaan|diperiksa|audit forensik|lawsuit|probe|investigation|scandal|skandal|"
                            r"bareskrim|polisi|tata kelola|gcg|whistleblow\w*)"),
    ("Kinerja keuangan", r"\b(laba|rugi|untung|pendapatan|penjualan|kinerja|margin|ebitda|npl|npf|kredit macet|"
                         r"kredit bermasalah|roe|roa|nim|car\b|bopo|aset|dpk|dana pihak ketiga|penyaluran kredit|"
                         r"kuartal|semester|triwulan|laporan keuangan|earnings|profit|revenue|net income|"
                         r"quarter|marketing sales|prapenjualan|dividen\w*|dividend)"),
    ("Utang & likuiditas", r"\b(utang|hutang|obligasi|sukuk|mtn|medium term notes?|surat utang|pinjaman|kredit sindikasi|"
                           r"refinanc\w*|pembiayaan kembali|likuiditas|jatuh tempo|kupon|leverage|der\b|gearing|"
                           r"arus kas|cash flow|bonds?|notes?|loans?|debt|liquidity|maturit\w*|global bond|"
                           r"penerbitan surat|emisi|pelunasan|melunasi|lunasi)"),
    ("Kebijakan & regulasi", r"\b(pemerintah|kementerian|regulasi|peraturan|kebijakan|ojk|bank indonesia|bi rate|"
                             r"suku bunga acuan|pajak|pmn|penyertaan modal negara|danantara|bp bumn|apbn|subsidi|"
                             r"tarif|regulator|policy|government)"),
    ("Ekspansi & bisnis", r"\b(kontrak|proyek|ekspansi|akuisisi|merger|investasi|pembangunan|kerja sama|kemitraan|"
                          r"produk baru|peluncuran|meluncurkan|tender|digitalisasi|pabrik|smelter|jaringan|cabang|"
                          r"contract|project|expansion|acquisition|partnership|launch\w*)"),
    ("Aksi korporasi & manajemen", r"\b(rups|direksi|direktur|komisaris|dirut|ceo|manajemen|buyback|rights issue|"
                                   r"hmetd|private placement|stock split|tender offer|go private|spin.?off|"
                                   r"management|board)"),
    ("Pasar saham", r"\b(saham|ihsg|harga saham|asing|net (buy|sell)|beli bersih|jual bersih|target harga|ara\b|arb\b|"
                    r"kapitalisasi pasar|bursa|stock|shares?|target price|rekomendasi)"),
]
_KAT_RX = [(k, re.compile(p, re.I)) for k, p in _KAT]

# ----------------------------------------------------------------------------
# Kamus frasa (pola, bobot, label alasan)
# ----------------------------------------------------------------------------
_NEG = r"(?:tidak|tak|belum|bukan|tanpa|nihil|bantah\w*|membantah|menepis|hindari|menghindari|terhindar(?: dari)?|" \
       r"lolos dari|bebas dari|jauh dari|not|no|never|without|avoid\w*|denies|denied)"

FRASA: list[tuple[str, float, str]] = [
    # --- pertumbuhan yang melambat = negatif (dicek sebelum aturan "pertumbuhan ... = naik")
    (r"(?:pertumbuhan|growth)\s+(?:[\w%.,]+\s+){0,3}?(?:melambat|tertahan|melemah|terkontraksi|slow\w*|"
     r"decelerat\w*)", -1.4, "pertumbuhan melambat"),
    (r"\b(?:perlambatan|slowdown)\b", -1.0, "perlambatan"),
    # --- penolakan gugatan / PKPU = positif (dicek paling awal agar kata "PKPU" di dalamnya tidak dihitung negatif)
    (r"(?:pkpu|pailit|gugatan|kepailitan)\W+(?:\w+\W+){0,4}?(?:ditolak|dicabut|dibatalkan|batal|kandas|"
     r"tidak dikabulkan|dismissed|rejected)", 1.5, "gugatan/PKPU ditolak"),
    (r"(?:tolak|menolak|ditolak|batalkan|membatalkan|cabut|mencabut|dismiss\w*|reject\w*)\W+(?:\w+\W+){0,3}?"
     r"(?:pkpu|pailit|gugatan|kepailitan)", 1.5, "gugatan/PKPU ditolak"),
    # --- peristiwa kredit (sangat negatif)
    (r"gagal bayar|default(?:ed)?\b|selective default|missed (?:coupon|payment)s?", -3.0, "gagal bayar"),
    (r"\bpkpu\b|penundaan kewajiban pembayaran utang", -3.0, "PKPU"),
    (r"pailit|kepailitan|bangkrut|kebangkrutan|insolven\w*|bankrupt\w*|insolvency", -3.0, "pailit/bangkrut"),
    (r"wanprestasi|tidak mampu membayar|gagal melunasi|tunggak\w*|menunggak", -2.5, "tunggakan/wanprestasi"),
    (r"\bid(?:sd|d)\b|\b(?:rd|d)\(idn\)", -3.0, "rating gagal bayar"),
    (r"restrukturisasi (?:utang|obligasi|kewajiban|pinjaman)|debt restructuring|homologasi", -2.0,
     "restrukturisasi utang"),
    (r"tunda bayar|penundaan pembayaran|perpanjang\w* jatuh tempo|extend\w* maturit\w*", -2.0, "penundaan pembayaran"),
    # --- aksi rating
    (r"(?:peringkat|rating)\w*\s+(?:\w+\s+){0,6}?(?:dinaikkan|naik|meningkat|diangkat)|menaikkan peringkat|"
     r"kenaikan peringkat|upgrad\w*|raises? (?:the )?(?:corporate )?ratings?|raised (?:the )?(?:corporate )?ratings?",
     3.0, "rating naik"),
    (r"(?:peringkat|rating)\w*\s+(?:\w+\s+){0,6}?(?:diturunkan|turun|dipangkas|merosot)|menurunkan peringkat|"
     r"penurunan peringkat|pemangkasan peringkat|downgrad\w*|lowers? (?:the )?(?:corporate )?ratings?|"
     r"lowered (?:the )?(?:corporate )?ratings?|cuts? (?:\w+ )?ratings?", -3.0, "rating turun"),
    (r"outlook\s+(?:\w+\s+){0,3}?negatif|negative outlook|outlook (?:to |revised to )?negative|"
     r"creditwatch (?:with )?negati\w*|rating watch negative|pengawasan negatif", -2.0, "outlook negatif"),
    (r"outlook\s+(?:\w+\s+){0,3}?positif|positive outlook|outlook (?:to |revised to )?positive|"
     r"creditwatch (?:with )?positi\w*|rating watch positive", 2.0, "outlook positif"),
    (r"outlook\s+(?:\w+\s+){0,2}?stabil|stable outlook|outlook stable", 0.6, "outlook stabil"),
    (r"afirmasi|affirm\w*|mempertahankan peringkat|menegaskan peringkat|peringkat tetap", 0.8, "rating dipertahankan"),
    # --- hukum & tata kelola
    (r"korupsi|tersangka|terdakwa|penyidikan|penyelidikan|kejagung|kejaksaan agung|\bkpk\b|suap|gratifikasi", -2.0,
     "kasus hukum/korupsi"),
    (r"fraud|penggelapan|manipulasi|pemalsuan|skandal|scandal|embezzl\w*|bribery", -2.0, "fraud/manipulasi"),
    (r"gugat\w*|digugat|lawsuit|sued\b|tuntutan hukum", -1.3, "gugatan"),
    (r"sanksi|denda|dibekukan|pembekuan|suspensi|disuspensi|delisting|penalt\w*|fined\b|sanction\w*", -1.6,
     "sanksi/suspensi"),
    (r"\bphk\b|pemutusan hubungan kerja|layoffs?|lay off", -1.3, "PHK"),
    # --- tekanan keuangan
    (r"rugi bersih|merugi|kerugian|tekor|net loss|losses\b|swing to loss|berbalik rugi", -2.0, "rugi"),
    (r"likuiditas (?:ketat|seret|tertekan)|kesulitan likuiditas|krisis likuiditas|kesulitan keuangan|"
     r"kesulitan (?:dana|membayar)|terlilit utang|utang menggunung|beban utang (?:berat|tinggi|membengkak)|"
     r"liquidity (?:crunch|squeeze|stress)|financial distress", -2.2, "tekanan likuiditas"),
    (r"impairment|penurunan nilai|write-?off|hapus buku|writedown", -1.3, "penurunan nilai aset"),
    (r"mangkrak|terbengkalai|molor|tertunda|delayed|terhenti", -1.0, "proyek tertunda"),
    (r"net sell|jual bersih|aksi jual|dilepas asing|target harga (?:dipangkas|diturunkan)|underweight|"
     r"rekomendasi jual|sell rating|downside", -0.8, "tekanan pasar"),
    (r"kekhawatiran|khawatir|waspada|ketidakpastian|tekanan|tertekan|headwinds?|concerns?|pressure", -0.6,
     "kekhawatiran/tekanan"),
    # --- positif
    (r"berbalik (?:untung|laba)|turnaround|swing to profit|kembali (?:untung|mencetak laba)", 2.5, "berbalik untung"),
    (r"(?:laba|keuntungan|profit)\w*\s+(?:\w+\s+){0,3}?(?:rekor|tertinggi|jumbo)|rekor laba|record (?:profit|earnings)",
     2.5, "laba rekor"),
    (r"dividen|dividend|buyback|pembelian kembali saham", 1.2, "dividen/buyback"),
    (r"(?:lampaui|melampaui|melebihi|di atas|atas) (?:ekspektasi|perkiraan|konsensus|estimasi)|"
     r"beats? (?:analyst |market )?(?:estimates|expectations|forecasts|consensus)|above (?:estimates|expectations)",
     1.6, "di atas ekspektasi"),
    (r"(?:di bawah|meleset dari|gagal capai|tak capai) (?:ekspektasi|perkiraan|konsensus|estimasi|target)|"
     r"miss(?:es|ed)? (?:analyst |market )?(?:estimates|expectations|forecasts|consensus)|below (?:estimates|expectations)",
     -1.6, "di bawah ekspektasi"),
    (r"oversubscri\w*|kelebihan permintaan|kelebihan pesanan|diserbu investor", 1.8, "penerbitan diminati"),
    (r"melunasi|pelunasan|dilunasi|lunasi|lunas\b|repaid|repay\w*", 1.4, "pelunasan utang"),
    (r"refinanc\w*|pembiayaan kembali", 0.5, "refinancing"),
    (r"kontrak baru|raih kontrak|meraih kontrak|kantongi kontrak|mengantongi kontrak|menang(?:kan)? tender|"
     r"wins? (?:a |the )?contract|secures? (?:a |the )?contract|awarded", 1.6, "kontrak baru"),
    (r"suntikan modal|penyertaan modal negara|\bpmn\b|capital injection|tambahan modal", 1.0, "suntikan modal"),
    (r"(?:meraih|mendapat|memperoleh|kantongi|teken)\s+(?:\w+\s+){0,2}?(?:pinjaman|fasilitas kredit|kredit sindikasi)|"
     r"secures? (?:a )?(?:loan|financing|funding)", 0.8, "dapat pendanaan"),
    (r"ekspansi|expansion|akuisisi|acquisition|kemitraan strategis|strategic partnership", 0.7, "ekspansi"),
    (r"(?:selesaikan|menyelesaikan|rampungkan|merampungkan|tuntaskan)\s+(?:\w+\s+){0,2}?proyek|proyek\s+(?:\w+\s+){0,4}?"
     r"(?:rampung|selesai|tuntas|beroperasi|diresmikan)|diresmikan|resmi beroperasi|mulai beroperasi|"
     r"completes? (?:the )?(?:construction|project)|inaugurat\w*", 0.9, "proyek selesai/beroperasi"),
    (r"membaik|perbaikan|pulih|pemulihan|recover\w*|improv\w*|rebound", 1.3, "perbaikan"),
    (r"solid|kokoh|kuat|sehat|robust|strong|resilien\w*|terjaga|stabil", 0.6, "fundamental solid"),
    (r"rekomendasi beli|\bbuy\b rating|outperform|overweight|target harga (?:naik|dinaikkan)|upside", 0.8,
     "rekomendasi positif"),
    (r"penghargaan|award\b|terbaik|best bank", 0.4, "penghargaan"),
]
_FRASA_RX = [(re.compile(p, re.I), w, a) for p, w, a in FRASA]

# Arah metrik: naik/turun pada metrik "baik" vs metrik "buruk"
_M_BAIK = (r"laba|keuntungan|profit|pendapatan|penjualan|marketing sales|prapenjualan|penyaluran kredit|kredit(?! macet| bermasalah)|"
           r"pembiayaan|aset|dpk|dana pihak ketiga|ebitda|margin|kinerja|earnings|revenue|net income|income|sales|"
           r"volume|penumpang|produksi|order book|ekuitas|modal|car|nim|roe|roa|arus kas|cash flow")
_M_BURUK = (r"npl|npf|kredit macet|kredit bermasalah|rugi|kerugian|beban|biaya|utang|hutang|liabilitas|leverage|"
            r"gearing|bopo|provisi|cadangan kerugian|tunggakan|defisit|losses|debt|klaim|provisions?|impairments?|"
            r"costs?|expenses?|bad loans?|non-performing loans?|credit costs?")
_NAIK = (r"naik|meningkat|tumbuh|melonjak|melesat|meroket|bertambah|menguat|terkerek|terdongkrak|moncer|melambung|"
         r"rises?|rose|rising|grows?|grew|jump(?:s|ed)?|surg(?:e|es|ed)|climb(?:s|ed)?|soar(?:s|ed)?|"
         r"increas(?:e|es|ed)|higher")
_TURUN = (r"turun|menurun|merosot|anjlok|ambles|amblas|melemah|terkoreksi|tergerus|susut|menyusut|terjun|jatuh|"
          r"tertekan|lesu|terpangkas|declin(?:e|es|ed)|fall(?:s|en)?|fell|drop(?:s|ped)?|slump(?:s|ed)?|"
          r"plung(?:e|es|ed)|tumbl(?:e|es|ed)|lower|shrank|shrinks?")
_NOUN_NAIK = r"kenaikan|peningkatan|pertumbuhan|lonjakan|penguatan"
_NOUN_TURUN = r"penurunan|pelemahan|kemerosotan|anjloknya|turunnya|kontraksi"
# jarak maks. 4 kata antara metrik dan arahnya, tanpa melewati kata penghubung klausa
_PENGHUBUNG = r"(?:as|karena|seiring|meski|meskipun|namun|tetapi|sementara|sedangkan|while|despite|but|amid|after|" \
              r"setelah|usai|di tengah)"
_GAP = rf"(?:\s+(?!{_PENGHUBUNG}\b)[\w%.,()-]+){{0,4}}?\s+"
_RX_METRIK = [
    (re.compile(rf"\b(?:{_M_BURUK})\b{_GAP}(?:{_NAIK})\b", re.I), -1.5, "beban/risiko naik"),
    (re.compile(rf"\b(?:{_M_BURUK})\b{_GAP}(?:{_TURUN})\b(?! tangan)", re.I), 1.2, "beban/risiko turun"),
    (re.compile(rf"\b(?:{_M_BAIK})\b{_GAP}(?:{_NAIK})\b(?! tangan)", re.I), 1.5, "kinerja naik"),
    (re.compile(rf"\b(?:{_M_BAIK})\b{_GAP}(?:{_TURUN})\b(?! tangan)", re.I), -1.5, "kinerja turun"),
    (re.compile(rf"\b(?:{_NOUN_NAIK})\s+(?:\w+\s+){{0,2}}?(?:{_M_BAIK})\b", re.I), 1.5, "kinerja naik"),
    (re.compile(rf"\b(?:{_NOUN_TURUN})\s+(?:\w+\s+){{0,2}}?(?:{_M_BAIK})\b", re.I), -1.5, "kinerja turun"),
    (re.compile(rf"\b(?:{_NOUN_NAIK})\s+(?:\w+\s+){{0,2}}?(?:{_M_BURUK})\b", re.I), -1.5, "beban/risiko naik"),
    (re.compile(rf"\b(?:{_NOUN_TURUN})\s+(?:\w+\s+){{0,2}}?(?:{_M_BURUK})\b", re.I), 1.2, "beban/risiko turun"),
    (re.compile(r"\bsaham\s+(?:\w+\s+){0,2}?(?:menguat|naik|melonjak|terbang|ara\b|hijau)", re.I), 0.5, "saham naik"),
    (re.compile(r"\bsaham\s+(?:\w+\s+){0,2}?(?:melemah|turun|anjlok|ambles|arb\b|merah|longsor)", re.I), -0.5,
     "saham turun"),
    (re.compile(r"\b(?:shares?|stocks?)\s+(?:\w+\s+){0,2}?(?:slump\w*|fall\w*|fell|drop\w*|tumbl\w*|plung\w*|"
                r"sink\w*|slid\w*)", re.I), -0.5, "saham turun"),
    (re.compile(r"\b(?:shares?|stocks?)\s+(?:\w+\s+){0,2}?(?:ris\w*|rose|jump\w*|surg\w*|climb\w*|soar\w*|"
                r"gain\w*)", re.I), 0.5, "saham naik"),
]
_RX_NEGASI = re.compile(rf"\b{_NEG}\b(?:\s+\S+){{0,2}}\s*$", re.I)

_ID_WORDS = set("yang dan di ke dari untuk dengan tidak akan ini itu pada dalam oleh atau juga sebesar tahun "
                "laba saham bank perseroan menjadi hingga sejak masih telah sudah adalah karena".split())
_EN_WORDS = set("the and of to in for with is on by as at from its has have will this that are was were "
                "said shares bank company year".split())


def bahasa(teks: str) -> str:
    w = re.findall(r"[a-z]+", (teks or "").lower())
    i = sum(x in _ID_WORDS for x in w)
    e = sum(x in _EN_WORDS for x in w)
    return "en" if e > i else "id"


@dataclass
class Hasil:
    skor: float           # -1 .. +1  (sentimen TEKS)
    label: str            # Positif / Netral / Negatif
    pendorong: str
    alasan: str
    mesin: str
    # opsional (diisi Claude); bila kosong dihitung oleh core.intel
    dampak: float | None = None        # -1 .. +1  dampak ke emiten
    aspek: str = ""                    # "Pendapatan, Laba, ..."
    materialitas: float | None = None  # 0..1
    penjelasan: str = ""


def label_dari(skor: float, ambang: float = 0.15) -> str:
    return "Positif" if skor >= ambang else ("Negatif" if skor <= -ambang else "Netral")


def pendorong_dari(teks: str) -> str:
    for k, rx in _KAT_RX:
        if rx.search(teks):
            return k
    return "Lainnya"


def nilai_kamus(judul: str, ringkasan: str = "") -> Hasil:
    """Sentimen berbasis kamus. Judul berbobot 2x ringkasan."""
    total, alasan = 0.0, []
    for bagian, bobot in ((judul or "", 1.0), (ringkasan or "", 0.5)):
        t = re.sub(r"\s+", " ", bagian)
        if not t:
            continue
        terpakai: list[tuple[int, int]] = []
        for rx, w, a in _FRASA_RX + _RX_METRIK:
            for m in rx.finditer(t):
                if any(m.start() < e and s < m.end() for s, e in terpakai):
                    continue  # tumpang tindih dengan frasa yang sudah dihitung
                nilai = w
                if _RX_NEGASI.search(t[max(0, m.start() - 30):m.start()]):
                    nilai = -0.5 * w
                    a2 = f"tidak/terhindar {a}"
                else:
                    a2 = a
                total += nilai * bobot
                terpakai.append((m.start(), m.end()))
                if a2 not in alasan:
                    alasan.append(a2)
    skor = math.tanh(total / 2.5)
    teks = f"{judul} {ringkasan}"
    return Hasil(round(skor, 3), label_dari(skor), pendorong_dari(judul) if pendorong_dari(judul) != "Lainnya"
                 else pendorong_dari(teks), ", ".join(alasan[:4]), "Kamus keuangan")


# ----------------------------------------------------------------------------
# Mesin model lokal (opsional)
# ----------------------------------------------------------------------------
MODEL_ID = "AzrilFahmiardi/sdd-sentiment-general"  # 125M IndoBERT; cocok untuk RAM terbatas
MODEL_ID_BESAR = "apriandito/indobert-sentiment-classifier"  # 335M; opsional di laptop
MODEL_EN = "ProsusAI/finbert"

from functools import lru_cache
import gc
import threading

_MODEL_LOCK = threading.RLock()
_MODEL_REPO = None


def _repo_lokal(jenis: str, mode_id: str = "hemat") -> str:
    return (MODEL_ID_BESAR if mode_id == "besar" else MODEL_ID) if jenis == "id" else MODEL_EN


def unduh_model_lokal(progress=None, hanya: str = "id", mode_id: str = "hemat") -> list[str]:
    """Unduh bobot hanya untuk bahasa yang dipilih (bukan dua model sekaligus).

    HF menyimpan cache di runtime Streamlit, bukan data historis/database.
    `hanya='semua'` tersedia bagi pengguna yang ingin menyiapkan dua bahasa.
    """
    from huggingface_hub import snapshot_download
    jenis2 = ("id", "en") if hanya == "semua" else (hanya,)
    if any(j not in ("id", "en") for j in jenis2):
        raise ValueError("Bahasa harus id, en, atau semua")
    status = []
    for jenis in jenis2:
        label = "IndoBERT" if jenis == "id" else "FinBERT"
        if progress:
            progress(f"Memeriksa cache / mengunduh {label} …")
        # Prefer safetensors jika tersedia. FinBERT masih menyediakan .bin pada main.
        # File lain (tf/flax) tidak diperlukan di Streamlit.
        bobot = "*.safetensors" if jenis == "id" else "pytorch_model.bin"
        snapshot_download(repo_id=_repo_lokal(jenis, mode_id),
                          allow_patterns=["*.json", "*.txt", "*.model", bobot,
                                          "vocab.*", "tokenizer.*"],
                          ignore_patterns=["tf_model.*", "flax_model.*", "*.h5", "*.onnx", "*.msgpack", "*.ot", "README*", "*.md"])
        status.append(label)
    return status


@lru_cache(maxsize=1)
def _model_digunakan(repo: str):
    """Satu pasangan model-tokenizer per proses, dipakai ulang lintas Refresh/emiten.

    maxsize=1 mencegah IndoBERT dan FinBERT menumpuk dalam cache RAM; file
    unduhan masing-masing tetap dalam cache Hugging Face selama runtime hidup.
    """
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    import torch
    torch.set_num_threads(min(2, torch.get_num_threads()))
    tok = AutoTokenizer.from_pretrained(repo)
    mod = AutoModelForSequenceClassification.from_pretrained(repo).eval()
    return tok, mod


class MesinLokal:
    """Download otomatis saat dipilih/digunakan, dan RAM satu model bahasa saja."""

    def __init__(self, mode_id: str = "hemat"):
        import torch  # noqa: F401
        import transformers  # noqa: F401
        self.mode_id = mode_id
        self._jenis = None
        self._tok = None
        self._mod = None

    def _pastikan(self, jenis: str):
        if self._jenis == jenis:
            return
        global _MODEL_REPO
        repo = _repo_lokal(jenis, self.mode_id)
        with _MODEL_LOCK:
            # Saat beralih bahasa, lepaskan model lama SEBELUM memuat model baru.
            # Ini menghindari peak RAM dua model sekaligus pada Streamlit gratis.
            if _MODEL_REPO is not None and _MODEL_REPO != repo:
                self._tok, self._mod = None, None
                _model_digunakan.cache_clear()
                gc.collect()
            self._tok, self._mod = _model_digunakan(repo)
            _MODEL_REPO = repo
            self._jenis = jenis

    def _probs(self, a, b=None):
        import torch
        tok, mod = self._tok, self._mod
        enc = tok(a, b, truncation=True, max_length=256, return_tensors="pt") if b else \
            tok(a, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            p = torch.softmax(mod(**enc).logits, dim=-1)[0].tolist()
        lab = {int(k): str(v).lower() for k, v in mod.config.id2label.items()}
        return {lab[i]: p[i] for i in range(len(p))}

    def nilai(self, judul: str, ringkasan: str, entitas: str) -> Hasil:
        k = nilai_kamus(judul, ringkasan)
        teks = f"{judul}. {ringkasan}".strip(". ")[:600]
        jenis = bahasa(teks)
        self._pastikan(jenis)
        if jenis == "id":
            if self.mode_id == "besar":
                p = self._probs(f"Kinerja dan risiko keuangan {entitas}", teks)
            else:
                p = self._probs(teks)
            pos, neg = p.get("positif", p.get("positive", 0)), p.get("negatif", p.get("negative", 0))
            nama = "IndoBERT"
        else:
            p = self._probs(teks)
            pos, neg = p.get("positive", 0), p.get("negative", 0)
            nama = "FinBERT"
        skor = 0.6 * (pos - neg) + 0.4 * k.skor
        if k.skor <= -0.8:
            skor = min(skor, k.skor)
        return Hasil(round(skor, 3), label_dari(skor), k.pendorong,
                     k.alasan or f"{nama}: pos {pos:.0%}, neg {neg:.0%}", f"{nama} + kamus")


# ----------------------------------------------------------------------------
# Claude API (opsional)
# ----------------------------------------------------------------------------
MODEL_CLAUDE = {"Claude Haiku 5.5 (cepat & hemat)": "claude-haiku-5-5",
                "Claude Sonnet 5.5 (lebih teliti)": "claude-sonnet-5-5"}

ASPEK_AI = ["Pendapatan", "Laba", "Biaya", "Likuiditas", "Reputasi", "Regulasi"]
_SYS = ("Anda analis riset emiten di Indonesia (risiko kredit & fundamental). Untuk setiap berita, lakukan "
        "Entity-Specific Financial Sentiment terhadap perusahaan di kolom 'perusahaan' — bukan pasar umum atau "
        "perusahaan lain. Bedakan: (1) sentimen TEKS berita, (2) DAMPAK ke perusahaan itu. Contoh: harga minyak naik "
        "bernada negatif bagi ekonomi tetapi menguntungkan produsen minyak dan merugikan pengguna minyak. Jangan "
        "memprediksi harga saham dan jangan memberi rekomendasi beli/jual. Pergerakan harga saham harian berdampak "
        "kecil. Gagal bayar, PKPU, pailit, penurunan rating, kasus hukum berat, tekanan likuiditas = sangat negatif. "
        "Bila kolom 'konteks' berisi faktor eksternal & sektor, nilai dampaknya lewat mekanisme bisnis sektor itu; "
        "bila arah dampak tergantung data yang tidak ada, beri dampak 0 dan katakan 'campuran/belum pasti'. "
        "Jawab HANYA dengan JSON array, satu objek per berita: "
        '{"id": ..., "sentimen": "positif"|"netral"|"negatif", "skor": -1..1 (nada teks), '
        '"dampak": -1..1 (dampak ke perusahaan), "aspek": subset dari ' + json.dumps(ASPEK_AI) + ', '
        '"materialitas": "tinggi"|"sedang"|"rendah", "status": "fakta"|"rumor"|"opini", "pendorong": salah satu dari '
        + json.dumps(list(PENDORONG), ensure_ascii=False) +
        ', "alasan": "maks 12 kata", "penjelasan": "maks 35 kata: mekanisme dampak ke bisnis perusahaan", '
        '"relevan": true|false}. Bahasa Indonesia. relevan=false bila berita tidak benar-benar membahas perusahaan '
        "itu (kecuali berita faktor eksternal yang diberi konteks).")
_MAT = {"tinggi": 0.9, "sedang": 0.65, "rendah": 0.4}


class MesinClaude:
    def __init__(self, api_key: str, model: str = "claude-haiku-5-5"):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def nilai_batch(self, items: list[dict]) -> dict:
        """items: [{id, perusahaan, judul, ringkasan}] -> {id: (Hasil, relevan)}"""
        if not items:
            return {}
        isi = json.dumps([{k: (str(v)[:400] if k == "ringkasan" else v) for k, v in it.items()} for it in items],
                         ensure_ascii=False)
        msg = self.client.messages.create(model=self.model, max_tokens=6000, system=_SYS,
                                          messages=[{"role": "user", "content": isi}])
        teks = "".join(getattr(b, "text", "") for b in msg.content)
        a, b = teks.find("["), teks.rfind("]")
        data = json.loads(teks[a:b + 1]) if a >= 0 and b > a else []
        out = {}
        for d in data:
            try:
                s = max(-1.0, min(1.0, float(d.get("skor", 0))))
            except (TypeError, ValueError):
                s = 0.0
            lab = {"positif": "Positif", "negatif": "Negatif"}.get(str(d.get("sentimen", "")).lower(), "Netral")
            pd_ = d.get("pendorong") if d.get("pendorong") in PENDORONG else "Lainnya"
            try:
                dm = max(-1.0, min(1.0, float(d.get("dampak"))))
            except (TypeError, ValueError):
                dm = None
            asp = d.get("aspek") or []
            asp = ", ".join(a for a in (asp if isinstance(asp, list) else str(asp).split(",")) if str(a).strip()
                            in ASPEK_AI) if asp else ""
            stt = str(d.get("status", "")).lower()
            alasan = str(d.get("alasan", ""))[:160] + (" (rumor)" if stt == "rumor" else "")
            out[str(d.get("id"))] = (Hasil(round(s, 3), lab, pd_, alasan, f"Claude ({self.model})",
                                           None if dm is None else round(dm, 3), asp,
                                           _MAT.get(str(d.get("materialitas", "")).lower()),
                                           str(d.get("penjelasan", ""))[:300]), bool(d.get("relevan", True)))
        return out

    def _teks(self, prompt: str, sistem: str = "", max_tokens: int = 1800) -> str:
        kw = {"system": sistem} if sistem else {}
        msg = self.client.messages.create(model=self.model, max_tokens=max_tokens,
                                          messages=[{"role": "user", "content": prompt}], **kw)
        return "".join(getattr(b, "text", "") for b in msg.content).strip()

    @staticmethod
    def _daftar(ref: list[dict]) -> str:
        return "\n".join(f"[{r['no']}] {r['tanggal']} | {r['sumber']} | relasi: {r['relasi']} | sentimen "
                         f"{r['label']} | dampak {r['dampak']} | {r['verifikasi']} | {r['judul']}"
                         + (f" — {r['ringkasan'][:220]}" if r.get("ringkasan") else "")
                         + (f" (faktor: {r['faktor']})" if r.get("faktor") else "") for r in ref)

    def tanya(self, perusahaan: str, pertanyaan: str, ref: list[dict], periode: str) -> str:
        """Ask AI About This Stock: jawab HANYA dari referensi yang dikumpulkan aplikasi, dengan sitasi [n]."""
        sistem = ("Anda asisten riset emiten. Jawab HANYA berdasarkan daftar referensi yang diberikan (berita & "
                  "dokumen yang dikumpulkan aplikasi). Setiap klaim wajib diberi nomor sumber [n]. Jika referensi "
                  "tidak cukup untuk menjawab, katakan terus terang 'data yang terkumpul belum cukup' dan sebutkan "
                  "apa yang perlu dicari. Jangan menambah fakta dari pengetahuan sendiri. Jangan memberi rekomendasi "
                  "beli/jual atau prediksi harga. Bedakan fakta resmi, berita media, dan rumor. Bahasa Indonesia, "
                  "ringkas, poin-poin bila perlu.")
        prompt = (f"Emiten: {perusahaan}\nPeriode data: {periode}\n\nReferensi:\n{self._daftar(ref)}\n\n"
                  f"Pertanyaan: {pertanyaan}")
        return self._teks(prompt, sistem)

    def jelaskan_reaksi(self, perusahaan: str, data: list[dict]) -> dict:
        """Penjelasan singkat per peristiwa: kenapa berita ini relevan bagi perusahaan & apakah reaksi harganya
        masuk akal. Hanya dari data yang diberikan; tanpa klaim sebab-akibat pasti."""
        sistem = ("Anda analis pasar modal Indonesia. Untuk tiap peristiwa, jelaskan dalam 2–3 kalimat bahasa "
                  "Indonesia sederhana: (1) kenapa berita ini bisa memengaruhi perusahaan yang dipilih (jalur bisnis: "
                  "pendapatan, laba, biaya, likuiditas, reputasi, regulasi, atau hubungan grup), atau katakan terus "
                  "terang bila hubungannya lemah/jauh; (2) apakah reaksi harga (dibanding IHSG) searah dan cukup besar "
                  "untuk dikaitkan, dengan menyebut faktor lain bila ada. Hanya gunakan data yang diberikan, jangan "
                  "menambah fakta, jangan memberi rekomendasi beli/jual. Jawab HANYA JSON {\"id\": \"teks\", ...}.")
        teks = self._teks(f"Perusahaan: {perusahaan}\nData peristiwa:\n{json.dumps(data, ensure_ascii=False)}",
                          sistem, 2500)
        m = re.search(r"\{.*\}", teks, re.S)
        try:
            out = json.loads(m.group(0)) if m else {}
        except ValueError:
            out = {}
        return {str(k): str(v) for k, v in out.items()}

    def laporan(self, perusahaan: str, periode: str, ref: list[dict], metrik: str) -> str:
        """Narasi AI Research Report (bahasa Indonesia) dengan sitasi [n]."""
        sistem = ("Anda analis riset emiten. Tulis HANYA dari referensi & metrik yang diberikan, cantumkan [n] "
                  "untuk setiap klaim. Tanpa rekomendasi beli/jual, tanpa prediksi harga.")
        prompt = (f"Emiten: {perusahaan}\nPeriode analisis: {periode}\nMetrik aplikasi: {metrik}\n\nReferensi:\n"
                  f"{self._daftar(ref)}\n\nTulis laporan (maks 380 kata) dengan judul bagian persis: "
                  "'Ringkasan perkembangan', 'Peristiwa terpenting', 'Faktor risiko', 'Skenario dampak' "
                  "(skenario positif / dasar / negatif, kualitatif), 'Hal yang perlu dipantau'. Format: judul "
                  "bagian diawali '## ', isi poin '- '.")
        return self._teks(prompt, sistem, 2500)

    def ringkas(self, perusahaan: str, konteks_rating: str, berita: list[dict]) -> str:
        """Narasi singkat 'kenapa rating naik/turun / apa sentimennya' berdasar daftar berita (dengan sitasi [n])."""
        daftar = "\n".join(f"[{i + 1}] {b['tanggal']} | {b['sumber']} | {b['label']} | {b['judul']}"
                           for i, b in enumerate(berita[:30]))
        prompt = (f"Perusahaan: {perusahaan}\nStatus rating: {konteks_rating}\n\nBerita terkait (terbaru dulu):\n"
                  f"{daftar}\n\nTulis analisis singkat (maks 170 kata, bahasa Indonesia, poin-poin) tentang faktor "
                  "yang menjelaskan rating/arah risiko kreditnya: faktor penekan, faktor pendukung, dan hal yang "
                  "perlu dipantau. Hanya gunakan fakta dari daftar berita, cantumkan nomor sumber [n]. Jika berita "
                  "tidak cukup menjelaskan, katakan demikian.")
        msg = self.client.messages.create(model=self.model, max_tokens=1500,
                                          messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in msg.content).strip()
