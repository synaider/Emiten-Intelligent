"""Penyimpanan SEMENTARA per sesi browser (Pandas, tanpa SQL/database/file).

Berita, label, rating, peringatan dan log hilang saat sesi Streamlit berakhir.
Objek dibuat sekali di st.session_state oleh app.py. Ekspor PDF/Excel tetap tersedia.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import pandas as pd

from .rating import KOLOM_RATING, kosong_rating, rapikan_rating

KOLOM_BERITA = ["id", "emiten", "judul", "ringkasan", "url", "sumber", "domain", "bahasa", "cakupan", "kanal",
                "terbit", "diambil", "relevansi", "skor", "label", "pendorong", "alasan", "mesin",
                "relasi", "faktor", "dampak", "aspek", "materialitas", "penjelasan"]
LOG_COLS = ["Waktu", "Emiten", "Kanal", "Jumlah", "Status", "Pesan", "Detik"]
LABEL_COLS = ["id", "emiten", "judul", "sentimen", "dampak", "catatan", "pelabel", "waktu"]
ALERT_COLS = ["kunci", "emiten", "tingkat", "jenis", "judul", "detail", "url", "waktu", "dibuat", "terkirim", "rincian"]


class SessionStore:
    def __init__(self, _legacy_path=None):
        self.berita = pd.DataFrame(columns=KOLOM_BERITA)
        self.rating = kosong_rating()
        self.log = pd.DataFrame(columns=LOG_COLS)
        self.meta = {}
        self.label = pd.DataFrame(columns=LABEL_COLS)
        self.alert = pd.DataFrame(columns=ALERT_COLS)
        self.versi = 0

    def set_meta(self, k, v):
        self.meta[k] = v

    def get_meta(self, k, default=None):
        return self.meta.get(k, default)

    def id_ada(self):
        # Artikel lama berlabel Pencarian bukan bukti relevansi dan boleh diganti hasil valid.
        valid = self.berita[self.berita['relasi'].fillna('') != 'Pencarian']
        return set(zip(valid['id'], valid['emiten']))

    def simpan_berita(self, df, timpa=False):
        if df is None or df.empty:
            return 0
        d = df.reindex(columns=KOLOM_BERITA).copy()
        # Hasil pencarian tanpa bukti kaitan emiten tidak boleh menjadi berita/sinyal portofolio.
        d = d[d['relasi'].fillna('') != 'Pencarian'].copy()
        if d.empty:
            return 0
        d['terbit'] = pd.to_datetime(d['terbit'], utc=True, errors='coerce')
        d['diambil'] = pd.to_datetime(d['diambil'], utc=True, errors='coerce').fillna(pd.Timestamp.now(tz='UTC'))
        d = d.drop_duplicates(['id', 'emiten'], keep='last')
        keys = set(zip(d['id'], d['emiten']))
        # Hapus entri lama berelasi lemah bila artikel yang sama kini terverifikasi.
        if not self.berita.empty:
            lama_lemah = self.berita['relasi'].fillna('').eq('Pencarian')
            lama_sama = pd.Series(list(zip(self.berita['id'], self.berita['emiten'])),
                                   index=self.berita.index).isin(keys)
            self.berita = self.berita.loc[~(lama_lemah & lama_sama)].copy()
        if timpa:
            keep = ~pd.Series(list(zip(self.berita['id'], self.berita['emiten'])), dtype=object).isin(keys)
            self.berita = self.berita.loc[keep.to_numpy()].copy()
        else:
            ada = self.id_ada()
            d = d.loc[[(i, e) not in ada for i, e in zip(d['id'], d['emiten'])]]
        if not d.empty:
            self.berita = (d.reset_index(drop=True) if self.berita.empty else
                           pd.concat([self.berita, d], ignore_index=True))
            self.versi += 1
        return len(d)

    def baca_berita(self, hari=None, emiten=None):
        d = self.berita.copy()
        # Lindungi juga sesi lama yang masih berisi data label relevansi Pencarian.
        d = d[d['relasi'].fillna('') != 'Pencarian'].copy()
        d['terbit'] = pd.to_datetime(d['terbit'], utc=True, errors='coerce')
        d['diambil'] = pd.to_datetime(d['diambil'], utc=True, errors='coerce')
        d['terbit'] = d['terbit'].fillna(d['diambil'])
        if emiten:
            d = d[d['emiten'].isin(emiten)]
        if hari:
            batas = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=hari)
            d = d[d['terbit'] >= batas]
        return d.sort_values('terbit', ascending=False).reset_index(drop=True)

    def jejak(self, emiten):
        return f"{self.versi}|{len(self.berita[self.berita['emiten'] == emiten])}"

    def emiten_tersimpan(self, hari=None):
        d = self.baca_berita(hari)
        return d['emiten'].value_counts().index.tolist()

    def perbarui_sentimen(self, df):
        if df is None or df.empty:
            return
        cols = ['skor', 'label', 'pendorong', 'alasan', 'mesin', 'dampak', 'aspek', 'materialitas', 'penjelasan']
        for _, r in df.iterrows():
            mask = (self.berita['id'] == r['id']) & (self.berita['emiten'] == r['emiten'])
            for c in cols:
                if c in df.columns:
                    self.berita.loc[mask, c] = r[c]
        self.versi += 1

    def hapus_berita(self, emiten=None, sebelum_hari=None):
        mask = pd.Series(True, index=self.berita.index)
        if emiten:
            mask &= self.berita['emiten'].eq(emiten)
        if sebelum_hari:
            tanggal = pd.to_datetime(self.berita['terbit'], utc=True, errors='coerce')
            mask &= tanggal < pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=sebelum_hari)
        n = int(mask.sum())
        self.berita = self.berita.loc[~mask].reset_index(drop=True)
        self.versi += 1
        return n

    def ganti_nama_emiten(self, lama, baru):
        self.berita.loc[self.berita['emiten'] == lama, 'emiten'] = baru
        self.rating.loc[self.rating['Nama'] == lama, 'Nama'] = baru
        self.versi += 1

    def baca_rating(self):
        return rapikan_rating(self.rating.copy()) if not self.rating.empty else kosong_rating()

    def simpan_rating(self, df):
        self.rating = rapikan_rating(df)
        self.versi += 1

    def tambah_rating(self, baru, ganti_sumber_berisi=None, untuk_nama=None):
        lama = self.baca_rating()
        if ganti_sumber_berisi:
            m = lama['Sumber'].fillna('').str.contains(ganti_sumber_berisi, case=False, regex=False)
            if untuk_nama is not None:
                m &= lama['Nama'].isin(set(untuk_nama))
            lama = lama[~m]
        self.simpan_rating(pd.concat([lama, baru], ignore_index=True))

    def tambah_log(self, log):
        if log is not None and not log.empty:
            rows = log.reindex(columns=LOG_COLS)
            self.log = (rows if self.log.empty else pd.concat([self.log, rows], ignore_index=True)).tail(5000).reset_index(drop=True)

    def baca_log(self, n=500):
        return self.log.iloc[::-1].head(n).reset_index(drop=True).copy()

    def simpan_label(self, d):
        if d is None or d.empty:
            return 0
        rows = d.reindex(columns=LABEL_COLS).drop_duplicates(['id', 'emiten', 'pelabel'], keep='last')
        k = set(zip(rows['id'], rows['emiten'], rows['pelabel']))
        self.label = self.label.loc[[t not in k for t in zip(self.label['id'], self.label['emiten'], self.label['pelabel'])]]
        self.label = (rows.reset_index(drop=True) if self.label.empty else
                      pd.concat([self.label, rows], ignore_index=True))
        return len(rows)

    def baca_label(self):
        return self.label.sort_values('waktu', ascending=False).reset_index(drop=True).copy()

    def hapus_label(self, id_, emiten, pelabel):
        m = (self.label['id'] == id_) & (self.label['emiten'] == emiten) & (self.label['pelabel'] == pelabel)
        self.label = self.label[~m].reset_index(drop=True)

    def simpan_peringatan(self, emiten, daftar):
        baru = []
        for p in daftar:
            rinci = json.dumps(getattr(p, 'berita', None) or [], ensure_ascii=False, default=str)
            m = self.alert['kunci'] == p.kunci
            if m.any():
                self.alert.loc[m, ['judul', 'detail', 'rincian']] = [p.judul, p.detail, rinci]
                continue
            now = datetime.now(timezone.utc).isoformat()
            row = {'kunci': p.kunci, 'emiten': emiten, 'tingkat': p.tingkat, 'jenis': p.jenis,
                   'judul': p.judul, 'detail': p.detail, 'url': p.url,
                   'waktu': pd.Timestamp(p.waktu).isoformat() if p.waktu is not None else now,
                   'dibuat': now, 'terkirim': None, 'rincian': rinci}
            self.alert = (pd.DataFrame([row], columns=ALERT_COLS) if self.alert.empty else
                          pd.concat([self.alert, pd.DataFrame([row])], ignore_index=True))
            baru.append(p)
        return baru

    def isi_rincian(self, kunci, berita):
        self.alert.loc[self.alert['kunci'] == kunci, 'rincian'] = json.dumps(berita, ensure_ascii=False, default=str)

    def tandai_terkirim(self, kunci, kanal):
        self.alert.loc[self.alert['kunci'].isin(kunci), 'terkirim'] = f'{kanal} {datetime.now(timezone.utc).isoformat()}'

    def baca_peringatan(self, emiten=None, n=500, hari=None):
        d = self.alert.copy()
        if emiten:
            d = d[d['emiten'].isin(emiten)]
        if hari:
            d = d[pd.to_datetime(d['waktu'], utc=True, errors='coerce') >= pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=hari)]
        d = d.sort_values(['waktu', 'dibuat'], ascending=False).head(n).reset_index(drop=True)
        d['berita'] = d['rincian'].map(lambda x: json.loads(x) if isinstance(x, str) else None)
        return d
