"""
Pengumpul berita dari banyak sumber + penyaring relevansi per emiten.

Sumber tanpa kunci (gratis):
  - Google News RSS            : edisi Indonesia (bahasa Indonesia), Indonesia (Inggris), global (AS) & Asia (SG)
  - Google News · situs pilihan: kueri "site:" ke situs tertentu (Stockbit, Investing.com, Kontan, Bisnis, CNBC,
                                 IDX Channel, Reuters, Bloomberg, ...) — daftar bisa diubah
  - Bing News RSS              : pasar Indonesia dan internasional
  - Yahoo Finance              : RSS berita per kode saham (KODE.JK)
  - Stockbit Snips             : RSS berita saham harian Stockbit (kode ditulis $BBRI; isi lengkap dibaca)
  - Investing.com              : RSS resmi berita saham / perusahaan / rating analis (edisi Indonesia & global)
  - GDELT DOC 2.0 API          : berita global 65+ bahasa, 3 bulan terakhir (dibatasi 1 permintaan / 5 detik)
  - RSS media nasional         : daftar feed bisa diubah (CNBC Indonesia, Antara, Republika, ...)
Sumber dengan kunci API (opsional): NewsAPI.org, GNews.io, NewsData.io

Semua sumber dibaca lewat feed/API publiknya dengan permintaan HTTP biasa. Bila sebuah situs menolak
permintaan otomatis, kanal itu dicatat "Gagal" di log dan dilewati.

Setiap artikel: judul, url, sumber (penerbit), domain, terbit (UTC), ringkasan/cuplikan, bahasa, cakupan, kanal.
"""
from __future__ import annotations

import hashlib
import html
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote_plus, urlparse

import pandas as pd

from .emiten import pisah

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
TIMEOUT = 20

EDISI_GOOGLE = {
    "Google News · Indonesia": ("id", "ID", "ID:id"),
    "Google News · Indonesia (EN)": ("en-ID", "ID", "ID:en"),
    "Google News · Global (EN)": ("en-US", "US", "US:en"),
    "Google News · Asia (EN)": ("en-SG", "SG", "SG:en"),
}
PASAR_BING = {"Bing News · Indonesia": "id-ID", "Bing News · Global (EN)": "en-US"}

K_GOOGLE_SITUS = "Google News · Situs pilihan"
K_YAHOO = "Yahoo Finance"
K_STOCKBIT = "Stockbit Snips"
K_INVESTING = "Investing.com"
K_RSS = "RSS media nasional"
K_GDELT = "GDELT (global)"
K_RESMI = "Sumber resmi (IDX, OJK, BI, website emiten)"
K_SEC = "SEC EDGAR (emiten tercatat di AS)"
K_FAKTOR = "Global Impact (faktor sektor)"

# (domain, bahasa edisi Google, nama tampilan)
SITUS_BAWAAN = [
    ("stockbit.com", "id", "Stockbit"),
    ("id.investing.com", "id", "Investing.com Indonesia"),
    ("investing.com", "en", "Investing.com"),
    ("cnbcindonesia.com", "id", "CNBC Indonesia"),
    ("kontan.co.id", "id", "Kontan"),
    ("bisnis.com", "id", "Bisnis.com"),
    ("idxchannel.com", "id", "IDX Channel"),
    ("emitennews.com", "id", "EmitenNews"),
    ("investor.id", "id", "Investor Daily"),
    ("katadata.co.id", "id", "Katadata"),
    ("kompas.com", "id", "Kompas"),
    ("bareksa.com", "id", "Bareksa"),
    ("reuters.com", "en", "Reuters"),
    ("bloomberg.com", "en", "Bloomberg"),
    ("thejakartapost.com", "en", "The Jakarta Post"),
    ("asia.nikkei.com", "en", "Nikkei Asia"),
    ("ft.com", "en", "Financial Times"),
    ("cnbc.com", "en", "CNBC International"),
    ("wsj.com", "en", "The Wall Street Journal"),
    ("apnews.com", "en", "AP News"),
    ("antaranews.com", "id", "Antara"),
    ("tempo.co", "id", "Tempo"),
    ("finance.detik.com", "id", "Detik Finance"),
]
SITUS_RESMI = ["idx.co.id", "ojk.go.id", "bi.go.id"]
FEED_STOCKBIT = [
    ("Stockbit Snips · Terbaru", "https://snips.stockbit.com/snips-terbaru?format=rss"),
    ("Stockbit Snips · Research", "https://snips.stockbit.com/stockbit-research?format=rss"),
]
FEED_INVESTING = [
    ("Investing.com ID · Berita Saham", "https://id.investing.com/rss/news_25.rss"),
    ("Investing.com ID · Berita Perusahaan", "https://id.investing.com/rss/news_356.rss"),
    ("Investing.com ID · Seluruh Berita", "https://id.investing.com/rss/news.rss"),
    ("Investing.com ID · Analisa Pasar Saham", "https://id.investing.com/rss/stock.rss"),
    ("Investing.com · Stock Market News", "https://www.investing.com/rss/news_25.rss"),
    ("Investing.com · Company News", "https://www.investing.com/rss/news_356.rss"),
    ("Investing.com · Analyst Ratings", "https://www.investing.com/rss/news_1061.rss"),
]

RSS_BAWAAN = [
    ("CNBC Indonesia · Market", "https://www.cnbcindonesia.com/market/rss"),
    ("CNBC Indonesia · News", "https://www.cnbcindonesia.com/news/rss"),
    ("Antara · Ekonomi", "https://www.antaranews.com/rss/ekonomi.xml"),
    ("Antara · English", "https://en.antaranews.com/rss/news.xml"),
    ("Republika · Ekonomi", "https://www.republika.co.id/rss/ekonomi"),
    ("Okezone · Economy", "https://sindikasi.okezone.com/index.php/rss/11/RSS2.0"),
    ("Tempo · Bisnis", "https://rss.tempo.co/bisnis"),
    ("Detik Finance", "https://finance.detik.com/rss"),
]

# media yang dihitung "Nasional" walau berbahasa Inggris / domain non-.id
DOMAIN_NASIONAL = (
    "kontan.co.id", "bisnis.com", "cnbcindonesia.com", "detik.com", "kompas.com", "kompas.id", "tempo.co",
    "liputan6.com", "okezone.com", "sindonews.com", "republika.co.id", "cnnindonesia.com", "idxchannel.com",
    "investor.id", "emitennews.com", "thejakartapost.com", "jakartaglobe.id", "antaranews.com", "tribunnews.com",
    "kumparan.com", "katadata.co.id", "idntimes.com", "merdeka.com", "suara.com", "infobanknews.com",
    "bareksa.com", "idnfinancials.com", "beritasatu.com", "jpnn.com", "viva.co.id", "mediaindonesia.com",
    "inews.id", "wartaekonomi.co.id", "neraca.co.id", "fortuneidn.com", "swa.co.id", "idx.co.id", "ojk.go.id",
    "pefindo.com", "bi.go.id", "indonesiabusinesspost.com", "theinsiderstories.com", "investortrust.id",
    "insight.kontan.co.id", "medcom.id", "metrotvnews.com", "marketeers.com", "dataindonesia.id", "tirto.id",
    "stockbit.com", "snips.stockbit.com", "id.investing.com", "ajaib.co.id", "pluang.com",
)
NEGARA_GDELT_ID = {"indonesia"}

_gdelt_lock = threading.Lock()
_gdelt_terakhir = [0.0]
_cache_feed: dict[str, tuple[float, list]] = {}   # url -> (waktu, artikel) — feed umum disimpan 5 menit
_cache_lock = threading.Lock()
TTL_FEED = 300


# ----------------------------------------------------------------------------
# Utilitas
# ----------------------------------------------------------------------------
def _sesi():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "id,en;q=0.8"})
    return s


def bersih(teks) -> str:
    t = html.unescape(str(teks or ""))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def domain_dari(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    return d[4:] if d.startswith("www.") else d


def cakupan(domain: str, bahasa: str, negara: str = "") -> str:
    d = (domain or "").lower()
    if negara.lower() in NEGARA_GDELT_ID or bahasa == "id":
        return "Nasional"
    if d.endswith(".id") or any(d == x or d.endswith("." + x) for x in DOMAIN_NASIONAL):
        return "Nasional"
    return "Internasional"


def kunci_judul(judul: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", "", (judul or "").lower())
    return re.sub(r"\s+", " ", t).strip()[:90]


def id_artikel(judul: str, url: str) -> str:
    k = kunci_judul(judul) or url
    return hashlib.sha1(k.encode("utf-8")).hexdigest()[:16]


def _waktu(entry) -> datetime | None:
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            return datetime(*v[:6], tzinfo=timezone.utc)
    for k in ("published", "updated"):  # mis. Investing.com: '2026-11-09 08:15:00' (GMT)
        v = entry.get(k)
        if v:
            t = pd.to_datetime(v, utc=True, errors="coerce")
            if not pd.isna(t):
                return t.to_pydatetime()
    return None


def _artikel(judul, url, sumber, terbit, ringkasan, bahasa, kanal, negara="", isi="", target=None) -> dict:
    """isi = teks lengkap (tidak disimpan; dipakai untuk mencari cuplikan yang menyebut emiten).
    target = nama emiten bila artikel didapat dari pencarian khusus emiten itu (Google, Yahoo)."""
    judul, ringkasan = bersih(judul), bersih(ringkasan)
    dom = domain_dari(url)
    if ringkasan and (kunci_judul(ringkasan).startswith(kunci_judul(judul)[:40]) or len(ringkasan) < 25):
        ringkasan = ""  # ringkasan hanya mengulang judul (Google News) atau terlalu pendek untuk berguna
    return {"judul": judul, "url": url, "sumber": sumber or dom, "domain": dom, "terbit": terbit,
            "ringkasan": ringkasan[:600], "bahasa": bahasa, "cakupan": cakupan(dom, bahasa, negara), "kanal": kanal,
            "isi": bersih(isi)[:30000] if isi else "", "target": target}


def _bahasa_dari_teks(t: str) -> str:
    from .sentimen import bahasa
    return bahasa(t)


# ----------------------------------------------------------------------------
# RSS
# ----------------------------------------------------------------------------
def _parse_feed(isi: bytes | str):
    import feedparser
    return feedparser.parse(isi)


def jendela_waktu(hari: int, maks: int = 12) -> list[tuple[str, str]]:
    """Bagi periode panjang menjadi beberapa jendela (after:/before:) agar berita lama ikut terambil.
    ≤ 31 hari = 1 jendela. Maks. `maks` jendela (paling baru)."""
    akhir = datetime.now(timezone.utc).date() + timedelta(days=1)
    if hari <= 31:
        return [((akhir - timedelta(days=hari)).isoformat(), akhir.isoformat())]
    lebar = max(30, -(-hari // maks))
    out, b = [], akhir
    while len(out) < maks and (akhir - b).days < hari:
        a = max(b - timedelta(days=lebar), akhir - timedelta(days=hari))
        out.append((a.isoformat(), b.isoformat()))
        b = a
    return out


def google_news(kueri: str, edisi: str, hari: int = 30, target: str | None = None, situs: str | None = None,
                jendela: tuple[str, str] | None = None, kanal: str | None = None, sesi=None) -> list[dict]:
    hl, gl, ceid = EDISI_GOOGLE[edisi]
    q = f"({kueri}) {situs}" if situs and " " in situs else (f"({kueri}) site:{situs}" if situs else kueri)
    if jendela:
        q = f"{q} after:{jendela[0]} before:{jendela[1]}"
    elif hari:
        q = f"{q} when:{hari}d" if hari <= 31 else \
            f"{q} after:{(datetime.now(timezone.utc) - timedelta(days=hari)).date().isoformat()}"
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={quote_plus(ceid)}"
    r = (sesi or _sesi()).get(url, timeout=TIMEOUT)
    r.raise_for_status()
    f = _parse_feed(r.content)
    out = []
    for e in f.entries:
        src = e.get("source") or {}
        penerbit = src.get("title") if isinstance(src, dict) else None
        judul = e.get("title", "")
        if penerbit and judul.endswith(" - " + penerbit):
            judul = judul[: -len(penerbit) - 3]
        elif " - " in judul and not penerbit:
            judul, penerbit = judul.rsplit(" - ", 1)
        href = src.get("href") if isinstance(src, dict) else ""
        a = _artikel(judul, e.get("link", ""), penerbit, _waktu(e), e.get("summary", ""),
                     "id" if hl == "id" else "en", kanal or (K_GOOGLE_SITUS if situs else edisi), target=target)
        if href:  # pakai domain penerbit asli (link Google adalah redirect)
            a["domain"] = domain_dari(href)
            a["cakupan"] = cakupan(a["domain"], a["bahasa"])
        out.append(a)
    return out


def _url_bing(link: str) -> str:
    try:
        q = parse_qs(urlparse(link).query)
        return q.get("url", [link])[0]
    except Exception:  # noqa: BLE001
        return link


def bing_news(kueri: str, pasar: str, sesi=None) -> list[dict]:
    url = f"https://www.bing.com/news/search?q={quote_plus(kueri)}&format=rss&mkt={pasar}&qft=sortbydate%3d%221%22"
    r = (sesi or _sesi()).get(url, timeout=TIMEOUT)
    r.raise_for_status()
    f = _parse_feed(r.content)
    kanal = next(k for k, v in PASAR_BING.items() if v == pasar)
    out = []
    for e in f.entries:
        link = _url_bing(e.get("link", ""))
        src = e.get("source")
        penerbit = e.get("news_source") or (src.get("title") if isinstance(src, dict) else None)
        teks = f"{e.get('title', '')} {e.get('summary', '')}"
        out.append(_artikel(e.get("title", ""), link, penerbit, _waktu(e), e.get("summary", ""),
                            _bahasa_dari_teks(teks), kanal))
    return out


def rss_media(nama: str, url: str, kanal: str = K_RSS, sesi=None) -> list[dict]:
    with _cache_lock:
        c = _cache_feed.get(url)
        if c and time.time() - c[0] < TTL_FEED:
            return [dict(a) for a in c[1]]
    r = (sesi or _sesi()).get(url, timeout=TIMEOUT)
    r.raise_for_status()
    f = _parse_feed(r.content)
    out = []
    penerbit = nama.split(" · ")[0]
    for e in f.entries:
        isi = ""
        if e.get("content"):
            isi = " ".join(c.get("value", "") for c in e["content"])
        isi = isi or e.get("summary", "")
        teks = f"{e.get('title', '')} {bersih(isi)[:400]}"
        out.append(_artikel(e.get("title", ""), e.get("link", ""), penerbit, _waktu(e), e.get("summary", ""),
                            _bahasa_dari_teks(teks), kanal, isi=isi))
    with _cache_lock:
        _cache_feed[url] = (time.time(), [dict(a) for a in out])
    return out


URL_IDX = "https://www.idx.co.id/primary/ListedCompany/GetAnnouncement"


def _ambil_kunci(d: dict, *nama):
    low = {k.lower(): v for k, v in d.items()} if isinstance(d, dict) else {}
    for n in nama:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return low[n.lower()]
    return None


INFO_IDX: dict = {}   # kode → {"total", "diambil", "halaman", "terpotong"} dari pengambilan terakhir (monitor cakupan)


def _idx_item(it: dict, kode: str, target: str | None) -> dict | None:
    p = _ambil_kunci(it, "pengumuman") or it
    judul = _ambil_kunci(p, "JudulPengumuman", "Judul", "Title", "PerihalPengumuman")
    if not judul:
        return None
    tgl = pd.to_datetime(_ambil_kunci(p, "TglPengumuman", "PublishDate", "CreatedDate"), errors="coerce")
    url = None
    for a in _ambil_kunci(it, "attachments", "Attachments") or []:
        url = _ambil_kunci(a, "FullSavePath", "Url", "PDFFilename")
        if url:
            break
    url = url or f"https://www.idx.co.id/id/perusahaan-tercatat/keterbukaan-informasi/?kodeEmiten={kode}"
    t = None if pd.isna(tgl) else (tgl.tz_localize("Asia/Jakarta") if tgl.tzinfo is None else tgl).tz_convert("UTC")
    a = _artikel(f"[Keterbukaan Informasi] {judul}", url, "IDX – Keterbukaan Informasi",
                 None if t is None else t.to_pydatetime(), _ambil_kunci(p, "JenisPengumuman") or "", "id", K_RESMI,
                 target=target)
    a["domain"], a["cakupan"], a["milik"] = "idx.co.id", "Nasional", True
    a["_kunci_idx"] = f"{judul}|{tgl}|{url}"
    return a


def idx_pengumuman(kode: str, hari: int = 30, target: str | None = None, sesi=None, ukuran: int = 50,
                   maks_halaman: int = 20) -> list[dict]:
    """Keterbukaan informasi IDX per kode emiten, SEMUA halaman (permintaan biasa; situs IDX bisa menolak akses
    otomatis). Halaman berikutnya diminta sampai jumlah dokumen = ResultCount, halaman terakhir tidak penuh, atau
    tidak ada dokumen baru. `indexFrom` dipakai sebagai offset; bila IDX ternyata memakai nomor halaman (offset kedua
    kosong padahal ResultCount lebih besar), otomatis beralih ke nomor halaman. Hasil pemeriksaan disimpan di
    INFO_IDX[kode] (dipakai monitor cakupan: apakah ada dokumen yang terlewat)."""
    kode = (kode or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{4}", kode):
        return []
    s = sesi or _sesi()
    dari = (datetime.now(timezone.utc) - timedelta(days=hari)).strftime("%Y%m%d")
    sampai = datetime.now(timezone.utc).strftime("%Y%m%d")

    def minta(idx_from: int) -> tuple[list, int | None]:
        r = s.get(URL_IDX, timeout=TIMEOUT, params={
            "kodeEmiten": kode, "emitenType": "*", "indexFrom": idx_from, "pageSize": ukuran, "dateFrom": dari,
            "dateTo": sampai, "lang": "id", "keyword": ""},
            headers={"Accept": "application/json", "Referer": "https://www.idx.co.id/"})
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError("IDX tidak mengembalikan data JSON (kemungkinan akses otomatis ditolak)") from None
        tot = _ambil_kunci(data, "ResultCount", "resultCount", "TotalCount")
        try:
            tot = int(tot) if tot is not None else None
        except (TypeError, ValueError):
            tot = None
        return list(_ambil_kunci(data, "Replies", "replies", "data", "Results") or []), tot

    out, ada = [], set()

    def tambah(items: list) -> int:
        n = 0
        for it in items:
            a = _idx_item(it, kode, target)
            if a is None or a["_kunci_idx"] in ada:
                continue
            ada.add(a.pop("_kunci_idx"))
            out.append(a)
            n += 1
        return n

    items, total = minta(0)
    tambah(items)
    mode, halaman, n_hal, nomor = "offset", 1, len(items), 1
    while halaman < maks_halaman:
        if total is not None and len(ada) >= total:
            break
        if total is None and n_hal < ukuran:
            break
        items, t2 = minta(len(ada) if mode == "offset" else nomor)
        total = total if total is not None else t2
        n_hal, baru = len(items), tambah(items)
        if baru == 0 and mode == "offset" and halaman == 1 and (total or 0) > len(ada):
            mode = "halaman"                      # indexFrom ternyata nomor halaman (0- atau 1-based)
            for nomor in (1, 2):                  # 1-based: halaman 1 = halaman pertama (duplikat) → coba 2
                items, _ = minta(nomor)
                n_hal, baru = len(items), tambah(items)
                if baru or not items:
                    break
        halaman += 1
        nomor += 1
        if baru == 0:
            break
    INFO_IDX[kode] = {"total": total, "diambil": len(out), "halaman": halaman, "mode": mode,
                      "terpotong": bool(total is not None and len(out) < total),
                      "waktu": datetime.now(timezone.utc).isoformat()}
    return out


_sec_tickers: dict = {}


def sec_edgar(kode_as: str, email: str, target: str | None = None, sesi=None) -> list[dict]:
    """Pengajuan terbaru di SEC EDGAR (mis. 20-F, 6-K) untuk emiten yang tercatat di AS. SEC mewajibkan User-Agent
    berisi nama aplikasi + email kontak pengguna."""
    kode_as = (kode_as or "").strip().upper()
    if not kode_as or not email:
        return []
    s = sesi or _sesi()
    hdr = {"User-Agent": f"EmitenIntelligence/1.0 {email}", "Accept-Encoding": "gzip, deflate"}
    if not _sec_tickers:
        r = s.get("https://www.sec.gov/files/company_tickers.json", headers=hdr, timeout=TIMEOUT)
        r.raise_for_status()
        for v in r.json().values():
            _sec_tickers[str(v.get("ticker", "")).upper()] = (int(v["cik_str"]), v.get("title", ""))
    if kode_as not in _sec_tickers:
        return []
    cik, nama = _sec_tickers[kode_as]
    r = s.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=hdr, timeout=TIMEOUT)
    r.raise_for_status()
    rec = r.json().get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])[:40]):
        acc = rec["accessionNumber"][i].replace("-", "")
        doc = rec.get("primaryDocument", [""] * 40)[i]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
        desc = rec.get("primaryDocDescription", [""] * 40)[i] or form
        t = pd.to_datetime(rec["filingDate"][i], utc=True, errors="coerce")
        a = _artikel(f"[SEC {form}] {nama}: {desc}", url, "SEC EDGAR", None if pd.isna(t) else t.to_pydatetime(),
                     "", "en", K_SEC, target=target)
        a["cakupan"], a["milik"] = "Internasional", True
        out.append(a)
    return out


def yahoo_finance(kode: str, target: str | None = None, sesi=None) -> list[dict]:
    """RSS berita Yahoo Finance per kode saham BEI (KODE.JK). Kode non-saham (mis. PPLN) dilewati."""
    kode = (kode or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{4}", kode):
        return []
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={kode}.JK&region=US&lang=en-US"
    r = (sesi or _sesi()).get(url, timeout=TIMEOUT)
    r.raise_for_status()
    f = _parse_feed(r.content)
    out = []
    for e in f.entries:
        teks = f"{e.get('title', '')} {e.get('summary', '')}"
        a = _artikel(e.get("title", ""), e.get("link", ""), None, _waktu(e), e.get("summary", ""),
                     _bahasa_dari_teks(teks), K_YAHOO, target=target)
        if a["domain"] in ("finance.yahoo.com", ""):
            a["sumber"] = "Yahoo Finance"
        out.append(a)
    return out


# ----------------------------------------------------------------------------
# GDELT
# ----------------------------------------------------------------------------
def _gdelt_term(q: str) -> str | None:
    q = q.strip()
    inti = q.strip('"')
    if len(re.sub(r"\W", "", inti)) < 4:
        return None
    return f'"{inti}"' if " " in inti else inti


def gdelt(kueri_list: list[str], hari: int = 30, maks: int = 250, sesi=None) -> list[dict]:
    terms = [t for t in (_gdelt_term(q) for q in kueri_list) if t]
    if not terms:
        return []
    q = "(" + " OR ".join(terms) + ")" if len(terms) > 1 else terms[0]
    params = {"query": q, "mode": "artlist", "maxrecords": str(maks), "format": "json",
              "timespan": f"{min(hari, 90)}d", "sort": "datedesc"}
    with _gdelt_lock:  # GDELT meminta jeda >= 5 detik antar permintaan
        tunggu = 5.5 - (time.time() - _gdelt_terakhir[0])
        if tunggu > 0:
            time.sleep(tunggu)
        r = (sesi or _sesi()).get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=40)
        _gdelt_terakhir[0] = time.time()
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"GDELT: {r.text[:150]}") from None
    out = []
    for a in data.get("articles", []) or []:
        try:
            t = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            t = None
        lang = (a.get("language") or "").lower()
        bhs = "id" if lang.startswith("indones") else ("en" if lang.startswith("engl") else lang[:2])
        art = _artikel(a.get("title", ""), a.get("url", ""), a.get("domain", ""), t, "", bhs, "GDELT (global)",
                       a.get("sourcecountry", ""))
        art["negara"] = a.get("sourcecountry", "")
        out.append(art)
    return out


# ----------------------------------------------------------------------------
# API berkunci (opsional)
# ----------------------------------------------------------------------------
def newsapi(kueri: str, key: str, hari: int = 30, sesi=None) -> list[dict]:
    dari = (datetime.now(timezone.utc) - timedelta(days=min(hari, 30))).strftime("%Y-%m-%d")
    r = (sesi or _sesi()).get("https://newsapi.org/v2/everything", timeout=TIMEOUT, params={
        "q": kueri, "from": dari, "sortBy": "publishedAt", "pageSize": 50, "apiKey": key})
    r.raise_for_status()
    out = []
    for a in r.json().get("articles", []):
        t = pd.to_datetime(a.get("publishedAt"), utc=True, errors="coerce")
        teks = f"{a.get('title', '')} {a.get('description', '')}"
        out.append(_artikel(a.get("title", ""), a.get("url", ""), (a.get("source") or {}).get("name"),
                            None if pd.isna(t) else t.to_pydatetime(), a.get("description", ""),
                            _bahasa_dari_teks(teks), "NewsAPI"))
    return out


def gnews(kueri: str, key: str, bahasa: str = "id", sesi=None) -> list[dict]:
    r = (sesi or _sesi()).get("https://gnews.io/api/v4/search", timeout=TIMEOUT, params={
        "q": kueri, "lang": bahasa, "max": 25, "sortby": "publishedAt", "apikey": key})
    r.raise_for_status()
    out = []
    for a in r.json().get("articles", []):
        t = pd.to_datetime(a.get("publishedAt"), utc=True, errors="coerce")
        out.append(_artikel(a.get("title", ""), a.get("url", ""), (a.get("source") or {}).get("name"),
                            None if pd.isna(t) else t.to_pydatetime(), a.get("description", ""), bahasa,
                            f"GNews ({bahasa})"))
    return out


def newsdata(kueri: str, key: str, sesi=None) -> list[dict]:
    r = (sesi or _sesi()).get("https://newsdata.io/api/1/latest", timeout=TIMEOUT, params={
        "q": kueri[:100], "apikey": key, "language": "id,en"})
    r.raise_for_status()
    out = []
    for a in r.json().get("results", []) or []:
        t = pd.to_datetime(a.get("pubDate"), utc=True, errors="coerce")
        bhs = "id" if (a.get("language") or "").startswith("indones") else "en"
        out.append(_artikel(a.get("title", ""), a.get("link", ""), a.get("source_name") or a.get("source_id"),
                            None if pd.isna(t) else t.to_pydatetime(), a.get("description", ""), bhs, "NewsData"))
    return out


# ----------------------------------------------------------------------------
# Relevansi: artikel -> emiten
# ----------------------------------------------------------------------------
_RE_PT = re.compile(r"\b(PT|Tbk\.?|\(Persero\)|Persero|Perseroda)\b", re.I)


def pola_emiten(e: pd.Series) -> dict:
    alias = pisah(e["Alias"])
    ent = re.sub(r"\s+", " ", _RE_PT.sub(" ", str(e.get("Entitas") or ""))).strip(" .,")
    if len(ent) >= 6:
        alias.append(ent)
    pola = []
    for a in dict.fromkeys(alias):
        a = a.strip().strip('"')
        if not a:
            continue
        if a.isupper() and len(a) <= 5:  # singkatan: harus huruf besar persis (BRI, PLN, KAI, BBRI)
            pola.append(re.compile(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])"))
        else:
            pola.append(re.compile(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", re.I))
    kecuali = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(x)}(?![A-Za-z0-9])", re.I) for x in pisah(e["Pengecualian"])]
    terkait = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(x.strip(chr(34)))}(?![A-Za-z0-9])",
                          0 if (x.isupper() and len(x) <= 5) else re.I)
               for x in pisah(e.get("Terkait", "")) if len(x.strip('"')) >= 3]
    return {"nama": e["Nama"], "pola": pola, "kecuali": kecuali, "terkait": terkait,
            "label": str(e.get("Kode") or e["Nama"])}


def _kode_kata():
    try:
        from .katalog import KODE_KATA
        return KODE_KATA
    except Exception:  # noqa: BLE001
        return set()


_KODE_KATA = _kode_kata()


_RE_KALIMAT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[$])")


def _cocok(t: str, p: dict) -> bool:
    """Disebut LANGSUNG (nama entitas terkait & pengecualian dihapus dulu, mis. 'BRI Life' bukan 'BRI',
    'Merdeka Gold Resources' bukan 'Merdeka')."""
    for x in p["kecuali"] + p.get("terkait", []):
        t = x.sub(" ", t)
    return any(rx.search(t) for rx in p["pola"])


def _temukan(t: str, p: dict, jenis: str) -> str:
    """Teks nama yang cocok (untuk menjelaskan kenapa berita dianggap terkait)."""
    t = t or ""
    buang = p["kecuali"] + (p.get("terkait", []) if jenis == "pola" else [])
    for x in buang:
        t = x.sub(" ", t)
    for rx in p.get(jenis, []):
        m = rx.search(t)
        if m:
            return m.group(0).strip()
    return ""


def alasan_relevan(art: dict, p: dict) -> str:
    """Penjelasan singkat kenapa sebuah berita dikaitkan dengan emiten."""
    rel = art.get("relasi") or ""
    if rel == "Tidak langsung":
        return f"Faktor eksternal sektor “{art.get('faktor') or '-'}” — berita tidak menyebut emiten"
    judul, ring = art.get("judul") or "", art.get("ringkasan") or ""
    m = _temukan(judul, p, "pola")
    if m:
        return f"Judul menyebut “{m}”"
    m = _temukan(ring, p, "pola")
    if m:
        return f"Isi berita menyebut “{m}”"
    m = _temukan(judul, p, "terkait") or _temukan(ring, p, "terkait")
    if m:
        return f"Menyebut entitas terkait “{m}” (anak usaha / merek / induk), bukan emiten itu sendiri"
    if art.get("kanal") in (K_RESMI, K_SEC):
        return "Dokumen resmi yang diambil berdasarkan kode emiten"
    if rel == "Pencarian":
        return "Hanya muncul di hasil pencarian khusus emiten; nama emiten tidak tertulis — keterkaitan lemah"
    return "Keterkaitan tidak dapat dipastikan dari judul/ringkasan"


def _cocok_terkait(t: str, p: dict) -> bool:
    for x in p["kecuali"]:
        t = x.sub(" ", t)
    return any(rx.search(t) for rx in p.get("terkait", []))


def cuplikan(teks: str, p: dict, maks: int = 420) -> str:
    """Kalimat-kalimat yang menyebut emiten (untuk dibaca & dinilai sentimennya)."""
    if not teks:
        return ""
    out, n = [], 0
    for k in _RE_KALIMAT.split(teks):
        k = k.strip()
        if 15 <= len(k) <= 600 and _cocok(k, p):
            out.append(k)
            n += len(k)
            if n >= maks or len(out) >= 3:
                break
    s = " … ".join(out)
    return s[:maks].rsplit(" ", 1)[0] + "…" if len(s) > maks else s


def relevansi(art: dict, p: dict, longgar: bool = False) -> tuple[float, str, str]:
    """(nilai, cuplikan, relasi).
    1.0 Langsung (disebut di judul) · 0.6 Langsung (disebut di isi) · 0.7/0.5 Entitas terkait (anak usaha/merek/
    induk dari kolom Terkait, di judul/isi) · 0.4 Pencarian (hasil pencarian khusus emiten, mode longgar) · 0 tidak relevan."""
    teks_isi = art.get("isi") or art.get("ringkasan") or ""
    if _cocok(art.get("judul", ""), p):
        return 1.0, cuplikan(teks_isi, p) if art.get("isi") else art.get("ringkasan", ""), "Langsung"
    c = cuplikan(teks_isi, p)
    if c or _cocok(art.get("ringkasan", ""), p):
        return 0.6, c or art.get("ringkasan", ""), "Langsung"
    if _cocok_terkait(art.get("judul", ""), p):
        return 0.7, art.get("ringkasan", ""), "Entitas terkait"
    if _cocok_terkait(teks_isi, p):
        return 0.5, art.get("ringkasan", ""), "Entitas terkait"
    # Tidak memasukkan hasil kueri saja sebagai bukti relasi, bahkan bila mode longgar diminta.
    return 0.0, "", ""


def kueri_gabung(e: pd.Series) -> str:
    q = pisah(e["Kueri"]) or [f'"{e["Nama"]}"']
    return " OR ".join(q) if len(q) > 1 else q[0]


_RX_INDONESIA = re.compile(r"\b(?:indonesia|indonesian|jakarta|rupiah|\bIDR\b|\bOJK\b|\bBPS\b|\bRI\b|"
                          r"bank indonesia|perekonomian nasional|dalam negeri|tanah air|perbankan nasional)\b", re.I)
_FAKTOR_STRICT = {
    "Suku bunga BI": (r"\b(?:bi[-\s]?rate|suku bunga acuan|bank indonesia|7dr?rr|benchmark interest rate)\b", True),
    "Suku bunga The Fed": (r"\b(?:the fed|federal reserve|fomc|fed funds|fed's)\b", False),
    "Nilai tukar rupiah": (r"\b(?:rupiah|idr|kurs rupiah)\b", False),
    "Pertumbuhan kredit perbankan": (r"\b(?:pertumbuhan kredit|penyaluran kredit|kredit perbankan|"
                                     r"loan growth|bank lending|bank credit|kredit industri)\b", True),
    "Kebijakan OJK & regulasi keuangan": (r"\b(?:ojk|otoritas jasa keuangan|financial services authority)\b", True),
    "Inflasi Indonesia": (r"\b(?:inflasi|inflation|indeks harga konsumen|consumer price index|\bIHK\b)\b", True),
}
_RX_PERBANKAN = re.compile(r"\b(?:bank|banking|perbankan|kredit|loan|likuiditas|liquidity|"
                           r"rasio keuangan|modal|capital|dpk|npl|pembiayaan|financial institution|"
                           r"suku bunga|interest rate)\b", re.I)


def faktor_terbukti(art: dict, faktor: str) -> bool:
    """Reject accidental Google results: source-query attribution is not article evidence.

    Direct/related entity matching is handled separately. Sector impact is only a *potential*
    channel and never claims a specific issuer's earnings are affected without evidence.
    """
    teks = f"{art.get('judul') or ''} {art.get('ringkasan') or ''}".strip()
    if not teks:
        return False
    sp = _FAKTOR_STRICT.get(faktor)
    if sp:
        patt, perlu_indonesia = sp
        if not re.search(patt, teks, flags=re.I):
            return False
        # BI Rate explicitly denotes Indonesia. Also admit domestic economic series from
        # Indonesian publisher domains if no explicit foreign geography dominates title.
        dom = str(art.get("domain") or "").lower().removeprefix("www.")
        kanal_dalam_negeri = (any(dom == x or dom.endswith("." + x) for x in DOMAIN_NASIONAL) and
                              not re.search(r"\b(?:jepang|japan|amerika|us|amerika serikat|singapura|singapore|"
                                            r"malaysia|china|tiongkok|india|korea|eropa|europe|australia)\b",
                                            str(art.get("judul") or ""), re.I))
        if perlu_indonesia and not (_RX_INDONESIA.search(teks) or kanal_dalam_negeri) and not (
                faktor == "Suku bunga BI" and re.search(r"\bBI[-\s]?rate\b", teks, re.I)):
            return False
        if faktor == "Kebijakan OJK & regulasi keuangan" and not _RX_PERBANKAN.search(teks):
            return False
        if faktor == "Suku bunga BI" and not re.search(r"\b(?:suku bunga|interest rate|rate|moneter|policy rate)\b", teks, re.I):
            return False
        if faktor == "Suku bunga The Fed" and not re.search(r"\b(?:suku bunga|interest|rate|moneter|policy|cut|hike|pangkas|keputusan)\b", teks, re.I):
            return False
        return True
    # Commodity, demand and sector indicators: require actual keyword in article text.
    # Hard restriction against identifying articles just by the search query.
    from .intel import FAKTOR
    r = next((x for x in FAKTOR.values() if x.nama == faktor), None)
    if r is None or not re.search(rf"\b(?:{r.kata})\b", teks, flags=re.I):
        return False
    # Region-specific indicators should describe Indonesia, not another country's statistics.
    khusus_id = ("Belanja infrastruktur pemerintah", "Sektor properti & konstruksi",
                 "Penjualan mobil & motor", "Daya beli & konsumsi", "Kunjungan wisatawan & penumpang",
                 "Pasar saham (IHSG)")
    if faktor in khusus_id and not _RX_INDONESIA.search(teks) and "IHSG" not in teks.upper():
        return False
    return True


# ----------------------------------------------------------------------------
# Orkestrasi
# ----------------------------------------------------------------------------
def kumpulkan(emiten: pd.DataFrame, kanal: list[str], hari: int = 30, rss_list: list[tuple] | None = None,
              kunci: dict | None = None, progress=None, maks_paralel: int = 6, situs: list[tuple] | None = None,
              longgar: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Kumpulkan berita untuk emiten aktif dari kanal terpilih.
    situs  = [(domain, bahasa)] untuk kanal 'Google News · Situs pilihan' (default SITUS_BAWAAN)
    longgar= simpan juga hasil pencarian khusus emiten (Google/Yahoo) yang tidak menyebut emiten di judul
    Return (artikel per emiten [kolom: emiten, relevansi, ...], log)."""
    kunci = kunci or {}
    e_aktif = emiten[emiten["Aktif"]].reset_index(drop=True)
    pola = [pola_emiten(e) for _, e in e_aktif.iterrows()]
    situs = situs if situs is not None else [(d, b) for d, b, _ in SITUS_BAWAAN]
    jendela = jendela_waktu(hari)
    tugas = []  # (label, fungsi, args)
    for _, e in e_aktif.iterrows():
        q = kueri_gabung(e)
        for ed in EDISI_GOOGLE:
            if ed in kanal:
                if len(jendela) > 1 and ed in ("Google News · Indonesia", "Google News · Global (EN)"):
                    for jd in jendela:  # periode panjang: per jendela waktu
                        tugas.append((e["Nama"], f"{ed}: {jd[0]}", google_news, (q, ed, hari, e["Nama"], None, jd)))
                else:
                    tugas.append((e["Nama"], ed, google_news, (q, ed, hari, e["Nama"])))
        if K_RESMI in kanal:
            if re.fullmatch(r"[A-Z]{4}", str(e.get("Kode") or "").strip().upper()):
                tugas.append((e["Nama"], f"{K_RESMI}: IDX", idx_pengumuman, (e["Kode"], hari, e["Nama"])))
            resmi = " OR ".join(f"site:{d}" for d in SITUS_RESMI + ([e["Website IR"]] if e.get("Website IR") else []))
            tugas.append((e["Nama"], f"{K_RESMI}: situs resmi", google_news,
                          (q, "Google News · Indonesia", hari, e["Nama"], resmi, None, K_RESMI)))
        if K_SEC in kanal and e.get("Kode AS") and kunci.get("sec_email"):
            tugas.append((e["Nama"], K_SEC, sec_edgar, (e["Kode AS"], kunci["sec_email"], e["Nama"])))
        if K_GOOGLE_SITUS in kanal:
            for dom, bhs in situs:
                ed = "Google News · Indonesia" if bhs == "id" else "Google News · Indonesia (EN)"
                tugas.append((e["Nama"], f"{K_GOOGLE_SITUS}: {dom}", google_news, (q, ed, hari, e["Nama"], dom)))
        if K_YAHOO in kanal and re.fullmatch(r"[A-Z]{4}", str(e.get("Kode") or "").strip().upper()):
            tugas.append((e["Nama"], K_YAHOO, yahoo_finance, (e["Kode"], e["Nama"])))
        for nm, mkt in PASAR_BING.items():
            if nm in kanal:
                tugas.append((e["Nama"], nm, bing_news, (q, mkt)))
        if "NewsAPI" in kanal and kunci.get("newsapi"):
            tugas.append((e["Nama"], "NewsAPI", newsapi, (q, kunci["newsapi"], hari)))
        if "GNews" in kanal and kunci.get("gnews"):
            tugas.append((e["Nama"], "GNews", gnews, (q, kunci["gnews"], "id")))
        if "NewsData" in kanal and kunci.get("newsdata"):
            tugas.append((e["Nama"], "NewsData", newsdata, (q, kunci["newsdata"])))
    if K_RSS in kanal:
        for nm, url in (rss_list or RSS_BAWAAN):
            tugas.append(("(semua)", f"RSS: {nm}", rss_media, (nm, url, K_RSS)))
    if K_STOCKBIT in kanal:
        for nm, url in FEED_STOCKBIT:
            tugas.append(("(semua)", f"{K_STOCKBIT}: {nm}", rss_media, (nm, url, K_STOCKBIT)))
    if K_INVESTING in kanal:
        for nm, url in FEED_INVESTING:
            tugas.append(("(semua)", f"{K_INVESTING}: {nm}", rss_media, (nm, url, K_INVESTING)))
    gd = []
    if K_GDELT in kanal:
        isi = list(e_aktif.iterrows())
        for i in range(0, len(isi), 6):
            kel = isi[i:i + 6]
            q = [x for _, e in kel for x in pisah(e["Kueri"])]
            gd.append((", ".join(e["Nama"] for _, e in kel), "GDELT (global)", gdelt, (q, hari)))

    hasil, log = [], []
    n_total = len(tugas) + len(gd)
    kunci_lock = threading.Lock()
    stat = {"ok": 0, "gagal": 0, "kanal_gagal": {}, "kanal_ok": {}}
    sesi_lokal = threading.local()

    def lewati(nm: str) -> str:
        """Pemutus: kanal gagal >= 3x tanpa satu pun berhasil, atau 12 permintaan pertama gagal semua."""
        with kunci_lock:
            if stat["ok"] == 0 and stat["gagal"] >= 12:
                return "Dihentikan: 12 permintaan pertama gagal semua (koneksi internet / situs diblokir?)"
            k = nm.split(":")[0]   # 'Google News · Situs pilihan: kontan.co.id' -> kanalnya
            if stat["kanal_ok"].get(k, 0) == 0 and stat["kanal_gagal"].get(k, 0) >= 3:
                return "Dilewati: kanal ini gagal 3x berturut-turut"
        return ""

    def jalan(label, nm, fn, args):
        """Dijalankan di thread pekerja. TIDAK memanggil Streamlit (progres dilaporkan dari thread utama)."""
        t0 = time.time()
        alasan = lewati(nm)
        if alasan:
            return [], {"Waktu": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "Emiten": label, "Kanal": nm,
                        "Jumlah": 0, "Status": "Dilewati", "Pesan": alasan, "Detik": 0.0}
        if not hasattr(sesi_lokal, "s"):
            sesi_lokal.s = _sesi()
        try:
            arts = fn(*args, sesi=sesi_lokal.s)  # semua kolektor menerima argumen bernama `sesi`
            st, pesan = "OK", ""
        except Exception as ex:  # noqa: BLE001
            arts, st, pesan = [], "Gagal", str(ex)[:180]
        k = nm.split(":")[0]
        with kunci_lock:
            if st == "OK":
                stat["ok"] += 1
                stat["kanal_ok"][k] = stat["kanal_ok"].get(k, 0) + 1
            else:
                stat["gagal"] += 1
                stat["kanal_gagal"][k] = stat["kanal_gagal"].get(k, 0) + 1
        return arts, {"Waktu": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "Emiten": label, "Kanal": nm,
                      "Jumlah": len(arts), "Status": st, "Pesan": pesan, "Detik": round(time.time() - t0, 1)}

    # GDELT punya jalur sendiri (1 thread, jeda 5 detik) agar tidak menyita slot kanal lain
    with ThreadPoolExecutor(max_workers=maks_paralel) as ex, ThreadPoolExecutor(max_workers=1) as ex_gd:
        semua = [ex_gd.submit(jalan, *t) for t in gd] + [ex.submit(jalan, *t) for t in tugas]
        for i, f in enumerate(as_completed(semua), start=1):
            arts, catat = f.result()
            hasil += arts
            log.append(catat)
            if progress:  # thread utama → aman untuk Streamlit
                progress(i, n_total, f"{catat['Kanal']} · {catat['Emiten']}")

    # --- saring waktu, pasangkan ke emiten, dedup
    batas = datetime.now(timezone.utc) - timedelta(days=hari)
    baris = []
    for a in hasil:
        if not a["judul"] or not a["url"]:
            continue
        if a["terbit"] is not None and a["terbit"] < batas:
            continue
        for p in pola:
            rel, cup, relasi = relevansi(a, p, longgar)
            if a.get("milik") and a.get("target") == p["nama"] and rel < 0.8:
                rel, cup, relasi = 0.8, a.get("ringkasan", ""), "Langsung"   # dokumen resmi milik emiten itu (IDX/SEC)
            if rel > 0:
                b = {k: v for k, v in a.items() if k not in ("isi", "target", "milik")}
                b.update({"emiten": p["nama"], "relevansi": rel, "relasi": relasi,
                          "ringkasan": (cup or b["ringkasan"])[:600], "id": id_artikel(a["judul"], a["url"])})
                baris.append(b)
    df = pd.DataFrame(baris)
    if not df.empty:
        # duplikat (judul sama dari beberapa kanal): utamakan relevansi tertinggi lalu tautan asli (bukan Google)
        df["_google"] = df["url"].str.contains("news.google.com", na=False)
        df = df.sort_values(["relevansi", "_google"], ascending=[False, True], kind="stable")
        df = df.drop_duplicates(subset=["id", "emiten"], keep="first").drop(columns="_google")
        df = df.sort_values("terbit", ascending=False, na_position="last", kind="stable")
    return df.reset_index(drop=True), pd.DataFrame(log)


# ----------------------------------------------------------------------------
# Global Impact: berita faktor sektor (tidak menyebut emiten)
# ----------------------------------------------------------------------------
def kumpulkan_faktor(nama: str, faktor: list[dict], hari: int = 30, progress=None,
                     maks_paralel: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    """faktor: [{"faktor": "Harga emas", "kueri_id": '"harga emas"', "kueri_en": '"gold price"'}, ...].
    Mengambil berita tiap faktor (Indonesia & global) dan menandainya relasi 'Tidak langsung'."""
    hari = min(hari, 31)
    tugas = []
    for f in faktor:
        if f.get("kueri_id"):
            tugas.append((f["faktor"], "Google News · Indonesia", f["kueri_id"]))
        if f.get("kueri_en"):
            tugas.append((f["faktor"], "Google News · Global (EN)", f["kueri_en"]))
    hasil, log = [], []

    def jalan(fk, ed, q):
        t0 = time.time()
        try:
            arts = google_news(q, ed, hari, kanal=K_FAKTOR, sesi=_sesi())
            st_, pesan = "OK", ""
        except Exception as ex:  # noqa: BLE001
            arts, st_, pesan = [], "Gagal", str(ex)[:180]
        for a in arts:
            a["faktor"] = fk
        return arts, {"Waktu": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "Emiten": nama, "Kanal":
                      f"{K_FAKTOR}: {fk}", "Jumlah": len(arts), "Status": st_, "Pesan": pesan,
                      "Detik": round(time.time() - t0, 1)}

    with ThreadPoolExecutor(max_workers=maks_paralel) as ex:
        fut = [ex.submit(jalan, *t) for t in tugas]
        for i, f in enumerate(as_completed(fut), start=1):
            arts, catat = f.result()
            hasil += arts
            log.append(catat)
            if progress:
                progress(i, len(tugas), catat["Kanal"])
    batas = datetime.now(timezone.utc) - timedelta(days=hari)
    rows = []
    for a in hasil:
        if not a["judul"] or (a["terbit"] is not None and a["terbit"] < batas):
            continue
        if not faktor_terbukti(a, a.get("faktor") or ""):
            continue
        b = {k: v for k, v in a.items() if k not in ("isi", "target")}
        b.update({"emiten": nama, "relevansi": 0.3, "relasi": "Tidak langsung",
                  "id": id_artikel(a["judul"] + "|" + a["faktor"], a["url"])})
        rows.append(b)
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["id"]).sort_values("terbit", ascending=False, na_position="last")
    return df.reset_index(drop=True), pd.DataFrame(log)
