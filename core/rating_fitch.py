"""Penelusuran publik Fitch pada saat diminta pengguna, tanpa API berbayar atau database.

Hanya tautan HTTPS fitchratings.com yang dapat diklaim sebagai rilis Fitch resmi.
Berita perantara / URL Google News tidak dihitung sebagai pengumuman terkonfirmasi.
Akses Fitch dapat dibatasi dan hasil publik tidak dijamin lengkap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit
import re
import pandas as pd

from . import rating, sumber

FITCH_CARI = 'https://www.fitchratings.com/latest-rating-actions/'
FITCH_INDONESIA = 'https://www.fitchratings.com/region/indonesia'
LEVEL = r'(?:AAA|AA\+|AA-|AA|A\+|A-|A|BBB\+|BBB-|BBB|BB\+|BB-|BB|B\+|B-|B|CCC|CC|C|RD|D)'
_RATING = re.compile(rf"(?<![A-Za-z0-9])({LEVEL}(?:\(idn\))?)(?![A-Za-z0-9])", re.I)
_INSTRUMEN = re.compile(r'\b(?:bond|bonds|notes|sukuk|obligasi|commercial paper|tranche|series|seri|MTN)\b', re.I)
_ISSUER = re.compile(r'\b(?:issuer default rating|issuer rating|corporate rating|national long.term rating|bank rating|long.term idr|lt idr|idr)\b', re.I)


def domain_fitch(url: str) -> bool:
    try:
        u = urlsplit(url or '')
        return u.scheme == 'https' and (u.hostname == 'fitchratings.com' or
                                         str(u.hostname).endswith('.fitchratings.com'))
    except (TypeError, ValueError):
        return False


def nama_kunci(nama: str) -> str:
    t = str(nama or '')
    t = re.sub(r'\b(?:PT|Persero|Tbk|Perseroan)\b', ' ', t, flags=re.I)
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.lower().split())


def menyebut_entitas(judul: str, nama: str) -> bool:
    n, t = nama_kunci(nama), nama_kunci(judul)
    if len(n) < 8 or len(n.split()) < 2:
        return False
    return bool(re.search(r'(?<!\w)' + re.escape(n) + r'(?!\w)', t))


def parse_rilis(judul: str, url: str, nama_entitas: str, tanggal=None) -> dict | None:
    """Klaim resmi hanya dari Fitch + judul dengan nama issuer yang jelas."""
    if not domain_fitch(url) or not menyebut_entitas(judul, nama_entitas):
        return None
    t = str(judul or '')
    # Hindari menafsir rating obligasi/sukuk sebagai rating perusahaan.
    if _INSTRUMEN.search(t) and not _ISSUER.search(t):
        return None
    a = ''
    if re.search(r'\b(?:downgrad\w*|lower\w*)\b', t, re.I):
        a = 'Turun'
    elif re.search(r'\b(?:upgrad\w*|rais\w*)\b', t, re.I):
        a = 'Naik'
    elif re.search(r'\b(?:affirm\w*|reaffirm\w*)\b', t, re.I):
        a = 'Afirmasi'
    elif re.search(r'\b(?:outlook|rating watch|creditwatch)\b', t, re.I):
        a = 'Watch'
    if not a:
        return None
    mt = _RATING.search(t)
    score = mt.group(1) if mt else None
    if score and not rating.inti(score):
        score = None
    outlook = None
    mo = re.search(r'\b(?:outlook\s+(?:revised\s+to\s+)?|with\s+)(stable|negative|positive|developing)\b', t, re.I)
    if mo:
        outlook = mo.group(1).capitalize()
    ts = pd.to_datetime(tanggal, utc=True, errors='coerce')
    if pd.isna(ts):
        return None  # tanggal tak diketahui: jangan mengklaim aksi terjadi pada periode yang dipilih
    return {'tanggal': ts.date(),
            'judul': t, 'url': url, 'aksi': a, 'rating': score, 'tingkat': 'perusahaan',
            'outlook': outlook, 'lembaga': 'Fitch'}


def cari(entitas: str, hari: int = 365, sesi=None) -> dict:
    """Cari tautan resmi Fitch lewat Bing News RSS yang mengarah ke domain Fitch.

    Tidak melakukan scraping halaman login atau mengarang rating saat rilis tidak ditemukan.
    """
    hasil, masalah, ditemukan, total_link = [], [], set(), 0
    kata_nama = nama_kunci(entitas).title()
    kueri = f'site:fitchratings.com "{kata_nama}" rating Fitch' 
    for pasar in ('en-US', 'id-ID'):
        try:
            artikel = sumber.bing_news(kueri, pasar, sesi=sesi)
            total_link += len(artikel)
            for a in artikel:
                link = str(a.get('url') or '')
                if not domain_fitch(link) or link in ditemukan:
                    continue
                ditemukan.add(link)
                row = parse_rilis(a.get('judul', ''), link, entitas, a.get('terbit'))
                if row:
                    hasil.append(row)
        except Exception as exc:
            masalah.append(f'{pasar}: {str(exc)[:110]}')
    now = pd.Timestamp.now(tz='UTC')
    filtered = [r for r in hasil if 0 <= (now - pd.Timestamp(r['tanggal'], tz='UTC')).days <= int(hari)]
    filtered.sort(key=lambda r: r['tanggal'], reverse=True)
    if filtered:
        st = f'{len(filtered)} rilis Fitch resmi ditemukan lewat pencarian publik'
    elif masalah and len(masalah) == 2:
        st = 'Fitch belum bisa diperiksa: kedua kanal pencarian gagal'
    else:
        st = ('Belum ditemukan rilis Fitch terverifikasi pada hasil pencarian publik; '
              'tidak berarti emiten tidak memiliki rating')
    return {'rilis': filtered, 'status': st, 'jumlah_ditemukan': total_link, 'galat': masalah,
            'url': FITCH_CARI, 'url_indonesia': FITCH_INDONESIA}


def ke_rating(rilis: list[dict], nama: str) -> pd.DataFrame:
    rows = []
    for r in rilis:
        if not r.get('rating') or not rating.inti(r['rating']):
            continue
        rows.append({'Nama': nama, 'Lembaga': 'Fitch', 'Tanggal': r['tanggal'],
                     'Rating': r['rating'], 'Outlook': r.get('outlook'), 'Aksi': r.get('aksi'),
                     'Keterangan': r['judul'][:220], 'Sumber': r['url']})
    return rating.rapikan_rating(pd.DataFrame(rows)) if rows else rating.kosong_rating()
