"""
Analisis: menilai sentimen berita, skor per emiten, sinyal peringatan, peringkat, dan penjelasan
"kenapa rating naik/turun".

Skor UTAMA di semua halaman (Overview, watchlist, peringkat, penjelasan rating, ekspor) = Sentiment Score 0–100
berbasis PERISTIWA UNIK (core/intel.py): S = 50 + 50 · Σ w·s / Σ w, s = dampak ke emiten (−1…+1),
w = relevansi × materialitas × kualitas bukti × kebaruan. Fungsi `skor()` (−100…+100, rata-rata artikel) hanya
dipertahankan sebagai ukuran bantu internal (memilih contoh berita) dan tidak ditampilkan sebagai skor emiten.
"""
from __future__ import annotations


import pandas as pd

from .rating import inti, kelompok, peringkat, status_rating
from .sentimen import PENDORONG, MesinClaude, MesinLokal, bahasa, label_dari, nilai_kamus

BOBOT_KANAL = {"PEFINDO (aksi rating)": 2.0}
ALASAN_KREDIT = ("gagal bayar", "PKPU", "pailit", "rating gagal bayar", "tunggakan", "penundaan pembayaran")


# ----------------------------------------------------------------------------
# Penilaian sentimen artikel
# ----------------------------------------------------------------------------
def nilai_artikel(df: pd.DataFrame, emiten: pd.DataFrame, mesin: str = "Kamus keuangan", claude_key: str = "",
                  claude_model: str = "claude-haiku-5-5", progress=None, model_id: str = "hemat") -> pd.DataFrame:
    """Isi kolom skor/label/pendorong/alasan/mesin. Baris dengan relevan=False (Claude) dibuang."""
    if df.empty:
        return df
    d = df.copy().reset_index(drop=True)
    ent = dict(zip(emiten["Nama"], emiten["Entitas"]))
    sektor = dict(zip(emiten["Nama"], emiten["Sektor"]))
    hasil = [None] * len(d)

    def teks_nilai(r) -> tuple[str, str]:
        """Bila judul tidak menyebut emiten (mis. rangkuman pasar Stockbit yang membahas banyak saham), yang dinilai
        adalah cuplikan kalimat tentang emiten itu, bukan judulnya."""
        rel = r.get("relevansi")
        ring = r.get("ringkasan") or ""
        if rel is not None and not pd.isna(rel) and rel < 1 and ring:
            return ring, ""
        return r["judul"], ring
    if mesin.startswith("Claude") and claude_key:
        mc = MesinClaude(claude_key, claude_model)
        buang = set()
        for i in range(0, len(d), 20):
            chunk = d.iloc[i:i + 20]
            items = [{"id": str(j), "perusahaan": f"{ent.get(r['emiten']) or r['emiten']} ({r['emiten']})",
                      "judul": r["judul"], "ringkasan": r.get("ringkasan") or "",
                      "catatan": "" if (r.get("relevansi") or 1) >= 1 else
                      "judul tidak menyebut perusahaan; nilai berdasarkan ringkasan/cuplikan",
                      **({"konteks": f"Faktor eksternal: {r.get('faktor')}; sektor emiten: "
                                     f"{sektor.get(r['emiten'], 'Lainnya')}"}
                         if r.get("relasi") == "Tidak langsung" else {})}
                     for j, r in chunk.iterrows()]
            try:
                out = mc.nilai_batch(items)
            except Exception as ex:  # noqa: BLE001  (gagal → pakai kamus untuk batch ini)
                out = {}
                if progress:
                    progress(min(i + 20, len(d)), len(d), f"Claude gagal ({str(ex)[:60]}), pakai kamus")
            for j, r in chunk.iterrows():
                h = out.get(str(j))
                if h:
                    hasil[j] = h[0]
                    if not h[1] and r.get("relasi") != "Tidak langsung":
                        buang.add(j)
                else:
                    hasil[j] = nilai_kamus(*teks_nilai(r))
            if progress:
                progress(min(i + 20, len(d)), len(d), "Menilai sentimen (Claude)")
        d = d.assign(_h=hasil)
        d = d.drop(index=list(buang))
    else:
        ml = None
        if mesin.startswith("IndoBERT"):
            ml = MesinLokal(model_id)
        # Kelompokkan bahasa agar model besar tidak bongkar/pasang di tiap artikel.
        urutan = list(range(len(d)))
        if ml:
            urutan.sort(key=lambda i: bahasa(" ".join(teks_nilai(d.iloc[i]))))
        for urutan_ke, j in enumerate(urutan, 1):
            r = d.iloc[j]
            if ml:
                hasil[j] = ml.nilai(*teks_nilai(r), ent.get(r["emiten"]) or r["emiten"])
            else:
                hasil[j] = nilai_kamus(*teks_nilai(r))
            if progress and (urutan_ke % 25 == 0 or urutan_ke == len(d)):
                progress(urutan_ke, len(d), "Menilai sentimen")
        d = d.assign(_h=hasil)
    d["skor"] = [h.skor for h in d["_h"]]
    d["label"] = [h.label for h in d["_h"]]
    d["pendorong"] = [h.pendorong for h in d["_h"]]
    d["alasan"] = [h.alasan for h in d["_h"]]
    d["mesin"] = [h.mesin for h in d["_h"]]
    for k in ("dampak", "aspek", "materialitas", "penjelasan"):
        v = [getattr(h, k) for h in d["_h"]]
        if any(x not in (None, "") for x in v):          # dari Claude; selain itu dihitung core.intel
            d[k] = [x if x not in ("",) else None for x in v]
    return d.drop(columns="_h").reset_index(drop=True)


def berita_pefindo(rilis: list[dict]) -> pd.DataFrame:
    """Rilis PEFINDO (hasil sinkron) -> baris berita dengan sentimen dari jenis aksi rating."""
    from .sumber import id_artikel

    peta = {"Naik": 0.9, "Turun": -0.9, "Afirmasi": 0.3, "Baru": 0.2, "Ditarik": -0.2, "Watch": -0.5}
    rows = []
    for b in rilis:
        s = peta.get(b["aksi"], 0.0)
        ol = (b.get("outlook") or "").lower()
        if "negative" in ol:
            s = min(s, -0.5) if b["aksi"] != "Naik" else s - 0.3
        elif "positive" in ol:
            s = max(s, 0.5)
        if b.get("rating") and inti(b["rating"]) in ("SD", "D"):
            s = -1.0
        if b["tingkat"] != "perusahaan":
            s *= 0.5
        t = pd.Timestamp(b["tanggal"]).tz_localize("UTC") + pd.Timedelta(hours=3)
        rows.append({"id": id_artikel(b["judul"], b["url"]), "emiten": b["emiten"], "judul": b["judul"],
                     "ringkasan": f"Aksi rating: {b['aksi'] or '-'}" + (f" · rating {b['rating']}" if b.get('rating')
                                                                        else "") +
                     (f" · outlook {b['outlook']}" if b.get("outlook") else ""),
                     "url": b["url"], "sumber": "PEFINDO", "domain": "pefindo.com", "bahasa": "en",
                     "cakupan": "Nasional", "kanal": "PEFINDO (aksi rating)", "terbit": t, "relevansi": 1.0,
                     "skor": round(s, 3), "label": label_dari(s), "pendorong": "Aksi rating",
                     "alasan": f"rilis PEFINDO: {b['aksi'] or 'informasi'}", "mesin": "Aturan aksi rating"})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Skor per emiten
# ----------------------------------------------------------------------------
def _bobot(d: pd.DataFrame, acuan: pd.Timestamp, paruh: float) -> pd.Series:
    umur = ((acuan - d["terbit"]).dt.total_seconds() / 86400).clip(lower=0)
    return (0.5 ** (umur / paruh)) * d["pendorong"].map(PENDORONG).fillna(0.7) * \
        d["kanal"].map(BOBOT_KANAL).fillna(1.0) * d["relevansi"].fillna(1.0)


def skor(d: pd.DataFrame, acuan: pd.Timestamp, paruh: float = 14) -> float | None:
    d = d[d["skor"].notna()]
    if d.empty:
        return None
    w = _bobot(d, acuan, paruh)
    return float(100 * (w * d["skor"]).sum() / w.sum()) if w.sum() > 0 else None


def ringkas_emiten(d: pd.DataFrame, acuan: pd.Timestamp, paruh: float = 14) -> dict:
    """(Lama, berbasis artikel −100…+100) — hanya untuk kompatibilitas; gunakan ringkas_peristiwa."""
    out = {"Skor": skor(d, acuan, paruh), "Berita": len(d), "Positif": int((d["label"] == "Positif").sum()),
           "Netral": int((d["label"] == "Netral").sum()), "Negatif": int((d["label"] == "Negatif").sum()),
           "Pendorong negatif": "", "Pendorong positif": "", "Berita terbaru": "", "Tgl berita terbaru": pd.NaT,
           "Peristiwa kredit": False}
    if d.empty:
        return out
    top = d.sort_values("terbit", ascending=False).iloc[0]
    out["Berita terbaru"], out["Tgl berita terbaru"] = top["judul"], top["terbit"]
    return out


def ringkas_peristiwa(ev: pd.DataFrame, tren: pd.DataFrame | None = None) -> dict:
    """Ringkasan satu emiten dengan metodologi yang SAMA dengan Overview: skor 0–100 dari peristiwa unik,
    perubahan vs 7 hari lalu (dari tren skor harian), jumlah peristiwa & arah dampaknya, pendorong, risiko."""
    from . import intel
    e = intel.langsung(ev) if ev is not None and not ev.empty else pd.DataFrame()
    s = intel.skor_0_100(ev) if not e.empty else None
    s7 = None
    if tren is not None and not tren.empty and tren["Skor"].notna().any():
        t2 = tren.dropna(subset=["Skor"])
        lalu7 = t2[t2["Tanggal"] <= t2["Tanggal"].max() - pd.Timedelta(days=7)]
        s7 = float(lalu7["Skor"].iloc[-1]) if not lalu7.empty else None
    out = {"Skor": s, "Skor 7 hari lalu": s7, "Tren": (s - s7) if s is not None and s7 is not None else None,
           "Kategori": intel.band(s)[0], "Peristiwa": len(e), "Berita": 0, "Positif": 0, "Netral": 0, "Negatif": 0,
           "Pendorong negatif": "", "Pendorong positif": "", "Berita terbaru": "", "Tgl berita terbaru": pd.NaT,
           "Peristiwa kredit": False, "Keyakinan": "—", "Risiko": "—"}
    if e.empty:
        return out
    lab = e["dampak"].map(label_dari)
    out.update({"Berita": int(e["n_artikel"].sum()), "Positif": int((lab == "Positif").sum()),
                "Netral": int((lab == "Netral").sum()), "Negatif": int((lab == "Negatif").sum()),
                "Keyakinan": intel.keyakinan(ev)[1], "Risiko": intel.tingkat_risiko(ev, s)[0]})
    kontr = (e["w"] * e["dampak"]).groupby(e["pendorong"]).sum()
    out["Pendorong negatif"] = ", ".join(kontr[kontr < 0].sort_values().index[:2])
    out["Pendorong positif"] = ", ".join(kontr[kontr > 0].sort_values(ascending=False).index[:2])
    top = e.sort_values("terbit", ascending=False).iloc[0]
    out["Berita terbaru"], out["Tgl berita terbaru"] = top["judul"], top["terbit"]
    ir = intel.inti_risiko(ev)            # peristiwa kredit 90 hari terakhir (gagal bayar, PKPU, restrukturisasi)
    if not ir.empty:
        ir = ir[ir["terbit"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)]
    out["Peristiwa kredit"] = bool(((ir["pendorong"] == "Gagal bayar & restrukturisasi") & (ir["dampak"] <= -0.4)).any()) \
        if not ir.empty else False
    return out


def sinyal(r: dict) -> str:
    """Tanda ringkas per emiten. Skor berskala 0–100 (50 = netral); Tren = perubahan skor vs 7 hari lalu."""
    s, tr = r.get("Skor"), r.get("Tren")
    p = peringkat(r.get("Rating"))
    ol = str(r.get("Outlook") or "").lower()
    tanda = []
    if r.get("Peristiwa kredit"):
        tanda.append("🚨 Peristiwa kredit (90 hari)")
    if r.get("Perubahan") == "Turun" and r.get("Baru berubah"):
        tanda.append("⬇️ Rating baru turun")
    if r.get("Perubahan") == "Naik" and r.get("Baru berubah"):
        tanda.append("⬆️ Rating baru naik")
    if "negat" in ol:
        tanda.append("Outlook negatif")
    if s is not None and not pd.isna(s):
        if s <= 35 and (p is None or p <= 6):
            tanda.append("⚠️ Sentimen negatif kuat")
        elif s < 40:
            tanda.append("Sentimen negatif")
        if tr is not None and not pd.isna(tr) and tr <= -10:
            tanda.append("↘️ Memburuk 7 hari")
        if tr is not None and not pd.isna(tr) and tr >= 10:
            tanda.append("↗️ Membaik 7 hari")
        if s >= 65 and p is not None and p >= 4:
            tanda.append("↗️ Potensi perbaikan")
    if not tanda:
        tanda.append("—" if not r.get("Peristiwa") and not r.get("Berita") else "✅ Stabil")
    return " · ".join(tanda)


def nama_pola(e) -> list[str]:
    """Nama/alias/kode emiten untuk mengenali judul yang mirip saat menggabungkan peristiwa."""
    from .emiten import pisah
    return list(dict.fromkeys([x.strip('"') for x in pisah(e.get("Alias", "") or "") + pisah(e.get("Kueri", "") or "")]
                              + [str(e.get("Kode") or ""), str(e.get("Entitas") or ""), str(e.get("Nama") or "")]))


def peristiwa_emiten(d: pd.DataFrame, e, hari: int, paruh: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Artikel tersimpan satu emiten → (peristiwa unik, tren skor harian), dengan pipeline yang sama seperti Overview."""
    from . import intel
    from .sumber import pola_emiten
    x = intel.perkaya(d, e.get("Sektor") or "Lainnya", e.get("Website IR") or "", pola_emiten(e))
    ev = intel.peristiwa(x, nama_pola(e), paruh)
    return ev, intel.tren_skor(ev, hari, paruh)


def peringkat_emiten(emiten: pd.DataFrame, berita: pd.DataFrame, rating: pd.DataFrame, hari: int = 30,
                     paruh: float = 14, cakupan: list[str] | None = None, hasil=None) -> pd.DataFrame:
    """Peringkat emiten aktif menurut rating, dengan Sentiment Score 0–100 berbasis peristiwa (sama dengan Overview).
    `hasil(e)` opsional → (peristiwa, tren) dari cache aplikasi agar angka identik dengan halaman lain."""
    acuan = pd.Timestamp.now(tz="UTC")
    b = berita[berita["terbit"] >= acuan - pd.Timedelta(days=hari)] if not berita.empty else berita
    if cakupan and not b.empty:
        b = b[b["cakupan"].isin(cakupan) | (b["kanal"] == "PEFINDO (aksi rating)")]
    rows = []
    for _, e in emiten[emiten["Aktif"].astype(bool)].iterrows():
        st = status_rating(rating, e["Nama"], e.get("Lembaga Utama") or "")
        if hasil is not None:
            ev, tren = hasil(e)
        else:
            d = b[b["emiten"] == e["Nama"]] if not b.empty else b
            ev, tren = peristiwa_emiten(d, e, hari, paruh)
        r = {"Emiten": e["Nama"], "Kode": e["Kode"], "Entitas": e["Entitas"], "Sektor": e["Sektor"], **st,
             **ringkas_peristiwa(ev, tren)}
        r["Baru berubah"] = bool(st["Tgl Perubahan"] is not None and pd.notna(st["Tgl Perubahan"]) and
                                 pd.Timestamp(st["Tgl Perubahan"]) >= pd.Timestamp.now() - pd.Timedelta(days=180))
        r["Kelompok"] = kelompok(st["Rating"])
        r["_rank"] = peringkat(st["Rating"]) if peringkat(st["Rating"]) is not None else 99
        r["Sinyal"] = sinyal(r)
        rows.append(r)
    return pd.DataFrame(rows)


def urutkan(df: pd.DataFrame, cara: str) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    d["_s"] = d["Skor"].fillna(0)
    if cara.startswith("Rating"):
        d = d.sort_values(["_rank", "_s"], ascending=[True, False], kind="stable")
    elif cara.startswith("Sentimen terbaik"):
        d = d.sort_values(["_s", "_rank"], ascending=[False, True], kind="stable")
    elif cara.startswith("Sentimen terburuk"):
        d = d.sort_values(["_s", "_rank"], ascending=[True, True], kind="stable")
    else:  # berita terbanyak
        d = d.sort_values(["Berita", "_rank"], ascending=[False, True], kind="stable")
    d = d.drop(columns="_s").reset_index(drop=True)
    d.insert(0, "#", range(1, len(d) + 1))
    return d


# ----------------------------------------------------------------------------
# Tren & pendorong
# ----------------------------------------------------------------------------
def tren_mingguan(d: pd.DataFrame, paruh: float = 14) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame(columns=["Minggu", "Skor", "Positif", "Netral", "Negatif"])
    x = d.copy()
    x["Minggu"] = x["terbit"].dt.tz_convert("Asia/Jakarta").dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    out = []
    for m, g in x.groupby("Minggu"):
        w = g["pendorong"].map(PENDORONG).fillna(0.7) * g["kanal"].map(BOBOT_KANAL).fillna(1.0) * \
            g["relevansi"].fillna(1.0)
        out.append({"Minggu": m, "Skor": float(100 * (w * g["skor"]).sum() / w.sum()) if w.sum() else 0.0,
                    "Positif": int((g["label"] == "Positif").sum()), "Netral": int((g["label"] == "Netral").sum()),
                    "Negatif": int((g["label"] == "Negatif").sum())})
    return pd.DataFrame(out).sort_values("Minggu")


def per_pendorong(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame(columns=["Pendorong", "Label", "Jumlah"])
    g = d.groupby(["pendorong", "label"]).size().reset_index(name="Jumlah")
    return g.rename(columns={"pendorong": "Pendorong", "label": "Label"})


# ----------------------------------------------------------------------------
# Penjelasan "kenapa rating naik/turun"
# ----------------------------------------------------------------------------
def _tgl(t) -> str:
    bln = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    t = pd.Timestamp(t)
    if t.tzinfo is not None:
        t = t.tz_convert("Asia/Jakarta")
    return f"{t.day} {bln[t.month - 1]} {t.year}"


def _contoh(d: pd.DataFrame, n: int = 3) -> list[str]:
    out = []
    for _, r in d.head(n).iterrows():
        out.append(f"[{r['judul']}]({r['url']}) — *{r['sumber']}, {_tgl(r['terbit'])}*")
    return out


def _faktor(d: pd.DataFrame, tanda: int, acuan: pd.Timestamp, paruh: float) -> list[tuple[str, int, pd.DataFrame]]:
    """[(pendorong, jumlah berita, contoh berita terkuat)] untuk sisi negatif (tanda=-1) / positif (+1).
    Memakai DAMPAK ke emiten bila tersedia (sama dengan skor 0–100), selain itu sentimen teks."""
    kol = "dampak" if "dampak" in d.columns and d["dampak"].notna().any() else "skor"
    x = d[(pd.to_numeric(d[kol], errors="coerce") * tanda) > 0.15]
    if x.empty:
        return []
    x = x.assign(_w=_bobot(x, acuan, paruh) * pd.to_numeric(x[kol], errors="coerce").abs())
    out = []
    for p, g in sorted(x.groupby("pendorong"), key=lambda kv: -kv[1]["_w"].sum()):
        out.append((p, len(g), g.sort_values("_w", ascending=False)))
    return out


def penjelasan(nama: str, r: dict, d: pd.DataFrame, hari: int, paruh: float = 14,
               d_riwayat: pd.DataFrame | None = None, e=None) -> str:
    """Penjelasan berbasis aturan (tanpa AI), dengan contoh berita bertaut.
    d = berita periode terpilih; d_riwayat = seluruh berita tersimpan emiten ini (untuk konteks perubahan rating);
    e = baris emiten (alias/sektor) agar skor di sekitar perubahan rating dihitung dengan metodologi 0–100 yang sama.
    r["Skor"] berskala 0–100 (ringkas_peristiwa)."""
    from . import intel
    if d_riwayat is None:
        d_riwayat = d
    acuan = pd.Timestamp.now(tz="UTC")
    baris = []
    if r.get("Rating"):
        lem = f" ({r['Lembaga']})" if r.get("Lembaga") else ""
        ol = f", outlook **{r['Outlook']}**" if r.get("Outlook") else ""
        baris.append(f"**Rating saat ini:** {r['Rating']}{lem}{ol} — per {_tgl(r['Tgl Rating'])}.")
    else:
        baris.append("**Rating:** belum ada data. Isi lewat tab *Emiten & Rating* (impor dari aplikasi Limit "
                     "Counterparty, sinkron PEFINDO, atau input manual).")

    if r.get("Perubahan") in ("Naik", "Turun") and r.get("Tgl Perubahan") is not None:
        t = pd.Timestamp(r["Tgl Perubahan"]).tz_localize("UTC") if pd.Timestamp(r["Tgl Perubahan"]).tzinfo is None \
            else pd.Timestamp(r["Tgl Perubahan"])
        jendela = d_riwayat[(d_riwayat["terbit"] >= t - pd.Timedelta(days=120)) &
                            (d_riwayat["terbit"] <= t + pd.Timedelta(days=10))]
        kata = "naik" if r["Perubahan"] == "Naik" else "turun"
        baris.append(f"\n##### Kenapa rating {kata}?\nRating {kata} dari **{r['Rating Sebelumnya']}** menjadi "
                     f"**{r['Rating']}** pada **{_tgl(t)}**.")
        rilis = jendela[jendela["kanal"] == "PEFINDO (aksi rating)"]
        if not rilis.empty:
            baris.append("\nRilis lembaga rating: " + "; ".join(_contoh(rilis.sort_values("terbit",
                                                                                          ascending=False), 2)) + ".")
            jendela = jendela[jendela["kanal"] != "PEFINDO (aksi rating)"]
        if jendela.empty:
            baris.append("\nBelum ada berita lain tersimpan di sekitar tanggal itu (120 hari sebelum s.d. 10 hari sesudah). "
                         "Ambil berita dengan periode lebih panjang (pilih 90 hari di sidebar) agar konteks perubahan "
                         "rating terbaca. Riwayat berita juga bertambah setiap kali aplikasi diperbarui.")
        else:
            e_ = e if e is not None else pd.Series({"Nama": nama, "Alias": "", "Kueri": "", "Pengecualian": "",
                                                    "Entitas": nama, "Kode": "", "Sektor": "Lainnya"})
            ev_j, _ = peristiwa_emiten(jendela, e_, 130, paruh)
            s_j = intel.skor_0_100(ev_j)
            arah = -1 if r["Perubahan"] == "Turun" else 1
            jendela = intel.perkaya(jendela, e_.get("Sektor") or "Lainnya")
            fak = _faktor(jendela, arah, t + pd.Timedelta(days=10), paruh)
            s_txt = (f"skor sentimen **{s_j:.0f}/100** ({intel.band(s_j)[0].lower()})" if s_j is not None else
                     "skor sentimen belum dapat dihitung (peristiwa unik < 3)")
            baris.append(f"\nDalam 120 hari sebelum perubahan ada **{len(jendela)} berita** "
                         f"({len(intel.langsung(ev_j))} peristiwa unik), {s_txt}. Pendorong yang paling konsisten "
                         "dengan arah rating:")
            if fak:
                for p, n, g in fak[:3]:
                    baris.append(f"- **{p}** ({n} berita) — " + _contoh(g, 1)[0])
            else:
                baris.append("- Tidak ada pendorong yang jelas searah dengan perubahan rating di berita tersimpan.")
    elif r.get("Rating"):
        baris.append("\nRating **tidak berubah** pada data yang tersimpan.")

    # kondisi sentimen terkini
    s = r.get("Skor")
    n_ev = r.get("Peristiwa", r.get("Berita", 0)) or 0
    if s is None or pd.isna(s):
        baris.append(f"\n##### Sentimen {hari} hari terakhir\n" + (
            "Belum ada berita. Klik **🔄 Refresh**." if not n_ev else
            f"Data tidak mencukupi untuk skor 0–100 ({n_ev} peristiwa unik; minimal 3)."))
        if not n_ev:
            return "\n".join(baris)
    else:
        tr = r.get("Tren")
        baris.append(f"\n##### Sentimen {hari} hari terakhir: {s:.0f}/100 ({intel.band(s)[0].lower()})"
                     + (f", {tr:+.0f} poin vs 7 hari lalu" if tr is not None and not pd.isna(tr) else ""))
    baris.append(f"{n_ev} peristiwa unik dari {r.get('Berita', 0)} berita · dampak ke emiten: "
                 f"🔵 {r['Positif']} menguntungkan · ⚪ {r['Netral']} netral · 🔴 {r['Negatif']} merugikan.")
    neg, pos = _faktor(d, -1, acuan, paruh), _faktor(d, 1, acuan, paruh)
    if neg:
        baris.append("\n**Faktor penekan (risiko rating turun):**")
        for p, n, g in neg[:3]:
            baris.append(f"- **{p}** ({n} berita) — " + _contoh(g, 1)[0])
    if pos:
        baris.append("\n**Faktor pendukung:**")
        for p, n, g in pos[:3]:
            baris.append(f"- **{p}** ({n} berita) — " + _contoh(g, 1)[0])
    baris.append(f"\n**Sinyal:** {r.get('Sinyal', '—')}")
    return "\n".join(baris)
