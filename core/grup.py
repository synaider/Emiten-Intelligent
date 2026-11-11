"""Label grup korporasi untuk GUI, bukan bukti relasi dalam analisis berita.

Prioritas: mapping Excel pengguna > katalog kepemilikan aplikasi > default direktori.
Tidak menambahkan kata grup ke alias berita, untuk mencegah false positive.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import pandas as pd

DATA_GRUP = Path(__file__).resolve().parent.parent / 'data' / 'grup_excel.csv'
DATA_KATALOG = Path(__file__).with_name('katalog_emiten.csv')

# Ticker yang memiliki nama berbeda antara workbook dan katalog / entitas utama.
KODE_NAMA = {
    'BBCA': 'Bank Central Asia', 'BMRI': 'Bank Mandiri', 'BBRI': 'Bank Rakyat Indonesia',
    'INKP': 'PT Indah Kiat Pulp & Paper Tbk', 'SMAR': 'PT SMART Tbk',
    'BRPT': 'PT Barito Pacific Tbk', 'TPIA': 'PT Chandra Asri Petrochemical Tbk',
    'PNBN': 'Bank Panin', 'BNGA': 'Bank CIMB',
    'BDMN': 'Bank Danamon', 'BTPN': 'Bank SMBC Indonesia', 'BNII': 'Bank Maybank Indonesia',
    'AGRO': 'Bank Raya Indonesia', 'BBTN': 'Bank Tabungan Negara',
    'NISP': 'Bank OCBC', 'BJTM': 'Bank Jatim', 'BJBR': 'Bank BJB',
    'ISAT': 'PT Indosat Tbk', 'SMGR': 'PT Semen Indonesia Tbk',
    'PTPP': 'PT PP (Persero) Tbk', 'PPLN': 'PT PLN (Persero)', 'KAII': 'PT Kereta Api Indonesia (Persero)',
    'WSKT': 'PT Waskita Karya (Persero) Tbk', 'MDKA': 'PT Merdeka Copper Gold Tbk',
    'SDRA': 'Bank Woori Saudara', 'MEGA': 'Bank Mega', 'BSDE': '',
}
# ASII adalah Astra International (bukan Astra Sedaya Finance); hilangkan pencocokan keliru.
KODE_NAMA.pop('ASII', None)


def normal(nama: str) -> str:
    t = str(nama or '').lower()
    t = re.sub(r'\b(pt|tbk|persero|perseroda|perseroan)\b', ' ', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


def rapikan_grup(raw: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9&.\s]', ' ', str(raw or '')).strip()
    s = re.sub(r'\s+', ' ', s).strip()
    aturan = {
        'SINARMAS': 'Sinarmas Group', 'DJARUM': 'Djarum Group',
        'MANDIRI': 'Mandiri Group', 'BRI': 'BRI Group', 'CT CORP': 'CT Corp Group',
        'ASTRA': 'Astra Group', 'BARITO PACIFIC': 'Barito Pacific Group',
        'BANGKOK BANK PC LIMITED': 'Bangkok Bank Group',
        'MITSUBISHI UFJ F.GROUP': 'MUFG Group',
        'PT WOORI FINANCIAL': 'Woori Financial Group',
        'SUMITOMO MITSUI FINANCIAL': 'Sumitomo Mitsui Financial Group',
        'PT METAMORFOSIS EKOSISTEM INDONESIA': 'Metamorfosis Ekosistem Indonesia',
    }
    k = s.upper().replace(' GROUP', '').strip()
    if k in aturan:
        return aturan[k]
    if s.upper().startswith('GRUP '):
        s = s[5:]
    if not s:
        return ''
    result = s.title().replace('Bri ', 'BRI ').replace('Bni ', 'BNI ').replace('Btn ', 'BTN ')
    result = result.replace('Pln ', 'PLN ').replace('Smi ', 'SMI ').replace('Smf ', 'SMF ')
    result = result.replace('Ocbc ', 'OCBC ').replace('Dbs ', 'DBS ').replace('Ptpp ', 'PTPP ')
    result = result.replace('Mufg ', 'MUFG ').replace('Smfg ', 'SMFG ')
    return result if 'Group' in result else result + ' Group'


@lru_cache(maxsize=1)
def _mapping_excel():
    d = pd.read_csv(DATA_GRUP, dtype=str).fillna('')
    lut = {}
    for _, r in d.iterrows():
        k = normal(r['Nama Excel'])
        if not k or k in lut:
            continue
        lut[k] = {'grup': rapikan_grup(r['Group Excel']),
                  'sumber': f"Excel unggahan · {r['Sheet']}", 'bukti': r['Group Excel']}
    return lut


@lru_cache(maxsize=1)
def _mapping_katalog():
    d = pd.read_csv(DATA_KATALOG, dtype=str).fillna('')
    return {str(r['Kode']).upper(): r for _, r in d.iterrows() if str(r.get('Kode', '')).strip()}


def cari(entitas: str, kode: str = '', nama_internal: str = '', override: dict | None = None) -> dict:
    kode = str(kode or '').upper().strip()
    if override and kode in override and override[kode].strip():
        return {'grup': override[kode].strip(), 'sumber': 'Diatur pengguna (sesi ini)', 'bukti': 'Manual'}
    exc = _mapping_excel()
    for calon in [KODE_NAMA.get(kode, ''), entitas]:
        if normal(calon) in exc:
            return dict(exc[normal(calon)])
    cat = _mapping_katalog().get(kode)
    if cat is not None:
        raw = str(cat.get('Grup', '')).strip()
        if raw and raw.lower() not in ('-', 'nan', 'tidak ada', 'tidak diketahui', 'unknown'):
            return {'grup': rapikan_grup(raw), 'sumber': 'Katalog kepemilikan aplikasi (27 Feb 2026)',
                    'bukti': str(cat.get('Dasar grup', '')).strip()}
    n = str(nama_internal or '').strip()
    if n.upper().endswith(' GROUP') and len(n.split()) >= 2:
        return {'grup': rapikan_grup(n), 'sumber': 'Direktori awal aplikasi (belum diverifikasi ulang)', 'bukti': ''}
    return {'grup': 'Belum teridentifikasi', 'sumber': 'Belum ada sumber grup', 'bukti': ''}


def info_emiten(e, override: dict | None = None) -> dict:
    return cari(str(e.get('Entitas') or ''), str(e.get('Kode') or ''),
                str(e.get('Nama') or ''), override)


def tabel_excel() -> pd.DataFrame:
    return pd.read_csv(DATA_GRUP, dtype=str).fillna('')
