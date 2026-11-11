"""
Monitor cakupan & kesegaran data (data quality):

1. Kesehatan kanal  — dari log pengambilan: tingkat keberhasilan, gagal berturut-turut, kapan terakhir berhasil,
   pesan galat terakhir. Kanal yang gagal berkepanjangan ditandai agar tidak diam-diam membuat data bolong.
2. Kewajaran jumlah berita — jumlah artikel per kanal pada pengambilan terakhir dibanding median riwayatnya, dan
   jumlah artikel 7 hari terakhir dibanding pola mingguan sebelumnya (turun drastis = kemungkinan pengambilan gagal;
   melonjak = peristiwa besar atau alias terlalu umum).
3. Laporan resmi yang seharusnya ada — laporan keuangan berkala menurut tenggat POJK 14/POJK.04/2022 (tahunan:
   akhir bulan ke-3; tengah tahunan/interim: akhir bulan ke-1 tanpa reviu, ke-2 reviu terbatas, ke-3 diaudit) dan
   kewajiban laporan interim kuartal I & III di BEI. Diperiksa apakah dokumen resminya benar-benar ditemukan.
4. Kelengkapan IDX — apakah semua halaman keterbukaan informasi IDX terambil (ResultCount vs jumlah diambil).
"""
from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

RX_LAPKEU = re.compile(r"laporan keuangan|financial (?:statement|report)|lap\.? ?keu|laporan interim|"
                       r"annual report|laporan tahunan|interim report|kinerja keuangan", re.I)
DOMAIN_RESMI_LK = ("idx.co.id", "ojk.go.id")
KANAL_USANG = {"Google News · Grup usaha"}          # kanal versi lama yang sudah dihapus (masih ada di log lama)


def _kanal_dasar(k: str) -> str:
    """'Google News · Indonesia: 2026-01-01…' / 'Google News · Situs pilihan: kontan.co.id' → nama kanal dasar."""
    k = str(k or "")
    if k.startswith("Sumber resmi") or ": " not in k:      # IDX vs situs resmi = endpoint berbeda, jangan digabung
        return k
    return k.split(": ")[0]


def waktu_log(s: pd.Series) -> pd.Series:
    """Kolom Waktu log ('dd/mm/YYYY HH:MM:SS', jam lokal komputer) → datetime naif."""
    t = pd.to_datetime(s, format="%d/%m/%Y %H:%M:%S", errors="coerce")
    return t.fillna(pd.to_datetime(s, errors="coerce", dayfirst=True))


def kesehatan_kanal(log: pd.DataFrame, emiten: str | None = None, hari: int = 14,
                    sektor: str | None = None) -> pd.DataFrame:
    """Ringkasan kesehatan tiap kanal dari log pengambilan. 'Dilewati' (pemutus sirkuit setelah gagal beruntun)
    dihitung tidak berhasil. `sektor` = ikut sertakan log faktor global sektor emiten."""
    kol = ["Kanal", "Status", "Permintaan", "Berhasil %", "Gagal berturut-turut", "Terakhir berhasil",
           "Artikel / permintaan", "Galat terakhir"]
    if log is None or log.empty:
        return pd.DataFrame(columns=kol)
    d = log.copy()
    d["Waktu"] = waktu_log(d["Waktu"])
    d = d[d["Waktu"] >= pd.Timestamp.now() - pd.Timedelta(days=hari)]
    if emiten:
        d = d[d["Emiten"].fillna("").isin([emiten, sektor or "\x00"])]
    if d.empty:
        return pd.DataFrame(columns=kol)
    d["Kanal"] = d["Kanal"].map(_kanal_dasar)
    d = d[~d["Kanal"].isin(KANAL_USANG)]
    rows = []
    for k, g in d.sort_values("Waktu", ascending=False).groupby("Kanal", sort=False):
        ok = g["Status"] == "OK"
        beruntun = 0
        for v in ok:                                      # dari yang terbaru
            if v:
                break
            beruntun += 1
        t_ok = g.loc[ok, "Waktu"].max() if ok.any() else pd.NaT
        rate = float(ok.mean())
        if beruntun >= 5 or (not ok.any() and len(g) >= 3):
            status = "🔴 Gagal berkepanjangan"
        elif beruntun >= 2 or rate < 0.6:
            status = "🟠 Terganggu"
        else:
            status = "🟢 Sehat"
        galat = g.loc[~ok, "Pesan"].dropna()
        rows.append({"Kanal": k, "Status": status, "Permintaan": len(g), "Berhasil %": round(100 * rate),
                     "Gagal berturut-turut": beruntun, "Terakhir berhasil": t_ok,
                     "Artikel / permintaan": round(float(pd.to_numeric(g.loc[ok, "Jumlah"], errors="coerce")
                                                         .mean()), 1) if ok.any() else 0.0,
                     "Galat terakhir": str(galat.iloc[0])[:140] if not galat.empty else ""})
    out = pd.DataFrame(rows, columns=kol)
    urut = {"🔴 Gagal berkepanjangan": 0, "🟠 Terganggu": 1, "🟢 Sehat": 2}
    return out.sort_values(["Status", "Permintaan"], key=lambda s: s.map(urut) if s.name == "Status" else -s) \
        .reset_index(drop=True)


def kewajaran_jumlah(log: pd.DataFrame, berita: pd.DataFrame, emiten: str) -> list[dict]:
    """Daftar temuan {tingkat, teks} tentang jumlah berita yang tidak wajar untuk satu emiten."""
    out = []
    # (a) per kanal: pengambilan terakhir vs median riwayat kanal itu untuk emiten ini
    if log is not None and not log.empty:
        d = log[(log["Emiten"] == emiten) & (log["Status"] == "OK")].copy()
        if not d.empty:
            d["Kanal"] = d["Kanal"].map(_kanal_dasar)
            d["Waktu"] = waktu_log(d["Waktu"])
            d["Jumlah"] = pd.to_numeric(d["Jumlah"], errors="coerce").fillna(0)
            # satu "pengambilan" = semua permintaan kanal itu dalam 10 menit yang sama
            d["sesi"] = d["Waktu"].dt.floor("10min")
            per = d.groupby(["Kanal", "sesi"])["Jumlah"].sum().reset_index().sort_values("sesi")
            for k, g in per.groupby("Kanal"):
                if len(g) < 4:
                    continue
                akhir, riwayat = g["Jumlah"].iloc[-1], g["Jumlah"].iloc[:-1].tail(12)
                med = float(riwayat.median())
                if med >= 5 and akhir <= 0.25 * med:
                    out.append({"tingkat": "🟠", "teks": f"{k}: pengambilan terakhir hanya {int(akhir)} artikel, "
                                                         f"biasanya ±{med:.0f} — sumber mungkin berubah/memblokir."})
    # (b) jumlah artikel 7 hari terakhir vs pola mingguan 8 minggu sebelumnya (berdasarkan tanggal terbit)
    if berita is not None and not berita.empty:
        b = berita[berita["relasi"].fillna("") != "Tidak langsung"]
        if not b.empty:
            now = pd.Timestamp.now(tz="UTC")
            t = b["terbit"]
            n7 = int((t >= now - pd.Timedelta(days=7)).sum())
            lalu = t[(t < now - pd.Timedelta(days=7)) & (t >= now - pd.Timedelta(days=63))]
            if len(lalu) >= 8:
                mingguan = lalu.dt.floor("D").map(lambda x: (now - x).days // 7).value_counts() \
                    .reindex(range(1, 9), fill_value=0)
                med = float(np.median(mingguan))
                if med >= 4 and n7 <= 0.3 * med:
                    out.append({"tingkat": "🟠", "teks": f"Hanya {n7} artikel dalam 7 hari terakhir, padahal biasanya "
                                                         f"±{med:.0f} per minggu — cek kesehatan kanal / lakukan "
                                                         "Refresh."})
                elif med >= 2 and n7 >= 3 * med and n7 >= 10:
                    out.append({"tingkat": "🔵", "teks": f"{n7} artikel dalam 7 hari terakhir, ±{n7 / max(med, 1):.0f}× "
                                                         "biasanya — ada peristiwa besar, atau alias/kata kunci "
                                                         "terlalu umum (cek relevansi)."})
            elif n7 == 0 and len(b) == 0:
                out.append({"tingkat": "🔵", "teks": "Belum ada artikel tersimpan untuk emiten ini."})
    return out


def _akhir_bulan(y: int, m: int) -> pd.Timestamp:
    return pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)


def periode_wajib(hari_ini: date | None = None, n: int = 4) -> list[dict]:
    """Laporan keuangan berkala terbaru yang tenggatnya sudah lewat / sedang berjalan.
    Interim (Q1, semester I, Q3): tanpa reviu → akhir bulan ke-1; reviu terbatas → ke-2; diaudit → ke-3.
    Tahunan (31 Des): akhir bulan ke-3 (31 Maret)."""
    h = pd.Timestamp(hari_ini or date.today())
    out = []
    for y in (h.year, h.year - 1):
        for m, nama in ((12, "Tahunan"), (9, "Kuartal III"), (6, "Semester I"), (3, "Kuartal I")):
            akhir = _akhir_bulan(y, m)
            if akhir >= h:
                continue
            if nama == "Tahunan":
                t1 = t3 = _akhir_bulan(y + 1, 3)
            else:
                t1 = akhir + pd.offsets.MonthEnd(1)
                t3 = akhir + pd.offsets.MonthEnd(3)
            out.append({"Laporan": f"{nama} {y}", "periode": akhir, "tenggat_awal": t1, "tenggat_akhir": t3})
    out.sort(key=lambda r: r["periode"], reverse=True)
    return out[:n]


def _penanda_periode(nama: str, y: int) -> re.Pattern:
    if nama.startswith("Tahunan"):
        p = rf"tahunan|annual|audited|diaudit|31 desember {y}|december 31,? {y}|tahun (?:buku )?{y}|fy ?{y}|\b{y}\b"
    elif nama.startswith("Kuartal III"):
        p = rf"kuartal iii|triwulan iii|kuartal 3\b|\bq3\b|\b3q\b|\b9m\b|sembilan bulan|30 september {y}|september 30,? {y}|" \
            rf"september {y}"
    elif nama.startswith("Semester"):
        p = rf"semester i\b|semester 1\b|tengah tahun|kuartal ii\b|triwulan ii\b|\bq2\b|\b1h\b|\bh1\b|\b6m\b|30 juni {y}|june 30,? {y}|" \
            rf"juni {y}"
    else:
        p = rf"kuartal i\b|triwulan i\b|kuartal 1\b|\bq1\b|\b1q\b|\b3m\b|31 maret {y}|march 31,? {y}|maret {y}"
    return re.compile(p, re.I)


def laporan_resmi(berita: pd.DataFrame, hari_data: int, hari_ini: date | None = None,
                  domain_ir: str = "") -> pd.DataFrame:
    """Apakah laporan keuangan berkala yang seharusnya sudah terbit benar-benar DITEMUKAN di data terkumpul.
    Dokumen resmi = keterbukaan informasi IDX / OJK / website IR emiten; berita media tentang laporan itu dicatat
    terpisah (tanda laporan sudah terbit tetapi dokumen resminya belum terambil)."""
    kol = ["Laporan", "Tenggat", "Status", "Dokumen", "URL"]
    h = pd.Timestamp(hari_ini or date.today()).tz_localize("Asia/Jakarta")
    awal_data = h - pd.Timedelta(days=hari_data)
    rows = []
    b = berita if berita is not None else pd.DataFrame()
    if not b.empty:
        b = b[b["judul"].fillna("").str.contains(RX_LAPKEU)]
    dom = b["domain"].fillna("").astype(str) if not b.empty else pd.Series(dtype=str)
    resmi_m = (dom.str.contains("|".join(DOMAIN_RESMI_LK)) | (b.get("verifikasi", pd.Series("", index=b.index))
                                                                == "Resmi")) if not b.empty else dom
    if domain_ir and not b.empty:
        resmi_m = resmi_m | dom.str.contains(re.escape(domain_ir))
    for p in periode_wajib(hari_ini):
        y = p["periode"].year
        t1 = p["tenggat_awal"].tz_localize("Asia/Jakarta")
        t3 = p["tenggat_akhir"].tz_localize("Asia/Jakarta") + pd.Timedelta(hours=23, minutes=59)
        mulai = p["periode"].tz_localize("Asia/Jakarta")
        tenggat = (f"{p['tenggat_akhir']:%d/%m/%Y}" if p["Laporan"].startswith("Tahunan") else
                   f"{p['tenggat_awal']:%d/%m/%Y} (tanpa reviu) – {p['tenggat_akhir']:%d/%m/%Y} (diaudit)")
        if t3 + pd.Timedelta(days=45) < awal_data:
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat, "Status": "⚪ Di luar periode data",
                         "Dokumen": f"Perpanjang periode berita ke ≥ {(h - mulai).days} hari untuk memeriksa.",
                         "URL": ""})
            continue
        cand = b[(b["terbit"] >= mulai) & (b["terbit"] <= t3 + pd.Timedelta(days=45))] if not b.empty else b
        if not cand.empty:
            jd = cand["judul"].fillna("")
            pen = _penanda_periode(p["Laporan"], y)
            lain = [_penanda_periode(q, y_) for q, y_ in (("Tahunan", y - 1), ("Tahunan", y), ("Kuartal III", y),
                                                           ("Semester I", y), ("Kuartal I", y))
                    if not (q == p["Laporan"].rsplit(" ", 1)[0] and y_ == y)]
            sebut_lain = pd.Series(False, index=cand.index)
            for rx in lain:
                sebut_lain |= jd.str.contains(rx)
            kena = jd.str.contains(pen) | ((cand["terbit"] <= t3) & ~sebut_lain)
            cand = cand[kena]
        res = cand[resmi_m.reindex(cand.index, fill_value=False)] if not cand.empty else cand
        if not res.empty:
            r = res.sort_values("terbit").iloc[0]
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat, "Status": "🟢 Dokumen resmi ditemukan",
                         "Dokumen": f"{r['judul']} ({r['sumber']}, {pd.Timestamp(r['terbit']):%d/%m/%Y})",
                         "URL": r["url"]})
        elif not cand.empty:
            r = cand.sort_values("terbit").iloc[0]
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat,
                         "Status": "🟡 Hanya diberitakan media",
                         "Dokumen": f"Dokumen resmi belum terambil; media: {r['judul']} ({r['sumber']})",
                         "URL": r["url"]})
        elif h > t3:
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat, "Status": "🔴 Belum ditemukan — tenggat lewat",
                         "Dokumen": "Cek keterbukaan informasi IDX (kanal IDX bisa diblokir) atau kemungkinan "
                                    "keterlambatan penyampaian.", "URL": ""})
        elif h > t1:
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat, "Status": "🟠 Belum ditemukan — masa tenggat",
                         "Dokumen": "Tenggat tanpa reviu sudah lewat; laporan direviu/diaudit masih boleh menyusul.",
                         "URL": ""})
        else:
            rows.append({"Laporan": p["Laporan"], "Tenggat": tenggat, "Status": "🔵 Belum jatuh tempo",
                         "Dokumen": "", "URL": ""})
    return pd.DataFrame(rows, columns=kol)


def ringkas(kanal: pd.DataFrame, temuan: list[dict], lap: pd.DataFrame, info_idx: dict | None) -> tuple[str, str]:
    """(ikon status keseluruhan, kalimat ringkas) untuk ditampilkan di Overview."""
    masalah = []
    if not kanal.empty:
        g = kanal[kanal["Status"].str.startswith("🔴")]
        if not g.empty:
            masalah.append(f"{len(g)} kanal gagal berkepanjangan ({', '.join(g['Kanal'].head(3))})")
    masalah += [t["teks"] for t in temuan if t["tingkat"] == "🟠"]
    if not lap.empty:
        hilang = lap[lap["Status"].str.startswith("🔴")]
        if not hilang.empty:
            masalah.append(f"laporan {', '.join(hilang['Laporan'])} belum ditemukan padahal tenggat lewat")
    if info_idx and info_idx.get("terpotong"):
        masalah.append(f"IDX: {info_idx['diambil']} dari {info_idx['total']} dokumen terambil")
    if not masalah:
        return "🟢", "Tidak ada masalah cakupan yang terdeteksi."
    return ("🔴" if any("gagal berkepanjangan" in m or "tenggat lewat" in m for m in masalah) else "🟠"), \
        "; ".join(masalah[:4])
