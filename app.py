"""
EMITEN INTELLIGENCE — AI-Powered Stock Sentiment, News & Risk Monitoring Platform (Streamlit).

Pilih kode saham / nama emiten → aplikasi mengumpulkan berita nasional & internasional, dokumen resmi, dan berita
faktor global; mengenali peristiwa yang relevan; menilai sentimen teks dan DAMPAK-nya ke emiten; lalu menjelaskan
implikasinya. Aplikasi tidak memberi rekomendasi beli/jual dan tidak memprediksi harga.

Halaman: Overview · News Intelligence · Global Impact · Market Analytics · Watchlist & Reports · Ask AI ·
Pengaturan · Panduan.

Jalankan:  streamlit run app.py      (Windows: klik dua kali jalankan.bat)
"""
from __future__ import annotations

import html as _html
from io import BytesIO
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core import analisis, demo, ekspor, emiten as em, grafik, intel, katalog as kt, laporan, monitor
from core import evaluasi as evm, pasar
from core import grup as grup_mod, rating as rt_mod, rating_dampak, rating_fitch, sumber
from core.session_store import SessionStore
from core.sentimen import MODEL_CLAUDE, PENDORONG, MesinClaude, unduh_model_lokal

APP_DIR = Path(__file__).resolve().parent
DATA = APP_DIR / "data"
EMITEN_XLSX = DATA / "emiten.xlsx"
RSS_XLSX = DATA / "sumber_rss.xlsx"
SITUS_XLSX = DATA / "situs_pilihan.xlsx"
SETELAN = DATA / "pengaturan.json"
WATCHLIST = DATA / "watchlist.json"  # kompatibilitas nama; tidak dibaca/ditulis

K = sumber
KANAL_SEMUA = (list(K.EDISI_GOOGLE) + [K.K_GOOGLE_SITUS, K.K_RESMI, K.K_FAKTOR, K.K_SEC] + list(K.PASAR_BING) +
               [K.K_YAHOO, K.K_STOCKBIT, K.K_INVESTING, K.K_GDELT, K.K_RSS, "NewsAPI", "GNews", "NewsData"])
KANAL_SATU_DEFAULT = (list(K.EDISI_GOOGLE) + [K.K_GOOGLE_SITUS, K.K_RESMI, K.K_FAKTOR, K.K_SEC] +
                      list(K.PASAR_BING) + [K.K_YAHOO, K.K_STOCKBIT, K.K_INVESTING, K.K_GDELT, K.K_RSS])
KANAL_BANYAK_DEFAULT = ["Google News · Indonesia", "Google News · Indonesia (EN)", "Google News · Global (EN)",
                        "Bing News · Indonesia", K.K_RESMI, K.K_STOCKBIT, K.K_INVESTING, K.K_GDELT, K.K_RSS]
MESIN = ["Kamus keuangan (bawaan, cepat)", "IndoBERT + FinBERT (model lokal)", "Claude API (paling teliti)"]
SATUAN = {"hari": 1, "minggu": 7, "bulan": 30, "tahun": 365}
BLN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
IKON_RISIKO = {"Rendah": "🟢", "Sedang": "🟠", "Tinggi": "🔴", "Kritis": "🚨", "—": "⚪"}
IKON_TINGKAT = {"Kritis": "🚨", "Tinggi": "🔴", "Sedang": "🟠", "Info": "🔵"}
KLS_LABEL = {"Positif": "pos", "Negatif": "neg"}
KLS_DAMPAK = {"Menguntungkan": "pos", "Merugikan": "neg", "Campuran / belum pasti": "mix"}
KLS_VERIF = {"Resmi": "res", "Media kredibel": "kred", "Opini/analisis": "op", "Belum terverifikasi": "unv",
             "Rumor / belum terkonfirmasi": "rum"}
RELASI_LANGSUNG = ["Langsung", "Entitas terkait"]

st.set_page_config(page_title="Emiten Intelligence", page_icon="📡", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1500px;}
  .hero h1 {font-size: 1.65rem; margin-bottom: 0;}
  .hero p, .sub {color: #5b5a56; margin-top: 0;}
  .chip {display:inline-block; padding: 1px 8px; border-radius: 10px; font-size: .76rem; margin: 0 5px 3px 0;
         font-weight: 600; white-space: nowrap;}
  .chip.pos {background:#e3eefb; color:#1c5cab;} .chip.neg {background:#fbe4e4; color:#9b2c2c;}
  .chip.net {background:#efeeea; color:#52514e;} .chip.mix {background:#efeeea; color:#52514e;}
  .chip.baru {background:#fff1cc; color:#6b4a00;} .chip.res {background:#e2f2e8; color:#1d6b3c;}
  .chip.kred {background:#eef3e6; color:#3f5d1f;} .chip.op {background:#f1ecf8; color:#5b3f86;}
  .chip.unv {background:#f1f1ef; color:#6b6a65;} .chip.rum {background:#fde9d7; color:#8a4b12;}
  .chip.rel {background:transparent; color:#6b6a65; border:1px solid #d8d7d2; font-weight:500;}
  .ev {padding: .62rem .1rem .7rem; border-bottom: 1px solid rgba(128,128,128,.18);}
  .ev a.j {text-decoration:none; font-weight:600; font-size:.98rem; line-height:1.35;}
  .ev .meta {color:#6b6a65; font-size:.82rem; margin-top:2px;}
  .ev .ai {color:#34332f; font-size:.86rem; margin-top:4px; border-left:3px solid #d9e6f7; padding-left:8px;}
  .ev details {font-size:.8rem; color:#6b6a65; margin-top:3px;} .ev details a {color:#1f5fae;}
  .meter {margin:.2rem 0 .1rem;} .meter .bar {display:flex; height:12px; border-radius:6px; overflow:hidden;}
  .meter .bar span {flex:1;} .meter .lbl {display:flex; font-size:.72rem; color:#6b6a65; margin-top:3px;}
  .meter .lbl span {flex:1; text-align:center;} .meter .pin {position:relative; height:16px;}
  .meter .pin b {position:absolute; top:0; transform:translateX(-50%); font-size:.8rem; color:#1b1b19;}
  div[data-testid="stMetricValue"] {font-size: 1.5rem;}
  ol.pemicu {margin: .2rem 0 .2rem 1.1rem; padding-left: .4rem;} ol.pemicu li {margin-bottom: .45rem;}
  ol.pemicu a.j {text-decoration:none; font-weight:600;} ol.pemicu .meta {color:#6b6a65; font-size:.8rem;}
  ol.pemicu .meta a {color:#1f5fae;}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Utilitas
# ----------------------------------------------------------------------------
def muat_tabel(path: Path, kolom: list[str], bawaan: list[dict]) -> pd.DataFrame:
    """Data sumber bawaan. Perubahan pengguna disimpan hanya pada sesi berjalan."""
    return pd.DataFrame(bawaan, columns=kolom)


def siapkan_demo(db: SessionStore):
    if db.get_meta("demo_siap") == "3":
        return
    db.hapus_berita()
    db.simpan_rating(demo.rating_demo())
    db.simpan_berita(analisis.nilai_artikel(demo.berita_demo(), demo.emiten_demo()), timpa=True)
    db.set_meta("demo_siap", "3")
    for n in demo.emiten_demo()["Nama"]:
        db.set_meta(f"refresh::{n}", datetime.now(timezone.utc).isoformat())
        db.set_meta(f"hari::{n}", "400")


def esc(x) -> str:
    return _html.escape(str(x if x is not None else ""))


def wib(t) -> str:
    if t is None or pd.isna(t):
        return "—"
    t = pd.Timestamp(t)
    t = t.tz_convert("Asia/Jakarta") if t.tzinfo else t
    return f"{t.day} {BLN[t.month - 1]} {t.year}" + (f", {t:%H:%M}" if (t.hour or t.minute) else "")


def tgl(t) -> str:
    if t is None or pd.isna(t):
        return "—"
    t = pd.Timestamp(t)
    return f"{t.day} {BLN[t.month - 1]} {t.year}"


def lalu(t) -> str:
    if t is None or pd.isna(t):
        return "belum pernah"
    s = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(t)).total_seconds()
    if s < 90:
        return "baru saja"
    if s < 3600:
        return f"{int(s // 60)} menit lalu"
    if s < 86400:
        return f"{int(s // 3600)} jam lalu"
    return f"{int(s // 86400)} hari lalu"


def angka(n) -> str:
    return f"{n:,}".replace(",", ".")


def init(key: str, nilai):
    if key not in st.session_state:
        st.session_state[key] = nilai


def chart(ch, teks_alt: str):
    if ch is None:
        st.caption("Belum ada data untuk grafik ini.")
    else:
        st.altair_chart(ch, width="stretch", theme=None, alt=teks_alt)


def charts(daftar_ch: list, teks_alt: str):
    if not daftar_ch:
        st.caption("Belum ada data untuk grafik ini.")
    for ch in daftar_ch:
        st.altair_chart(ch, width="stretch", theme=None, alt=teks_alt)


def chip(teks: str, kls: str) -> str:
    return f'<span class="chip {kls}">{esc(teks)}</span>'


def meter(s: float | None) -> str:
    warna = ["#c63d3c", "#ec9a99", "#d9d8d2", "#8dbbee", "#2a78d6"]
    nama_b = ["Sangat negatif", "Negatif", "Netral", "Positif", "Sangat positif"]
    bar = "".join(f'<span style="background:{w}; opacity:{1 if s is not None else .35}"></span>' for w in warna)
    pin = (f'<div class="pin"><b style="left:{min(max(s, 1.5), 98.5):.1f}%">▼ {s:.0f}</b></div>'
           if s is not None else '<div class="pin"><b style="left:50%">Data tidak mencukupi</b></div>')
    lbl = "".join(f"<span>{n}</span>" for n in nama_b)
    return f'<div class="meter">{pin}<div class="bar">{bar}</div><div class="lbl">{lbl}</div></div>'


# ----------------------------------------------------------------------------
# Pengaturan awal
# ----------------------------------------------------------------------------
setelan = {}  # tanpa pengaturan tersimpan; kunci API tidak ditulis ke disk
if setelan and int(setelan.get("versi", 2)) < 3:       # pengaturan versi lama: tambahkan kanal baru
    setelan["kanal_satu"] = list(dict.fromkeys((setelan.get("kanal_satu") or []) + [K.K_RESMI, K.K_FAKTOR, K.K_SEC]))
init("s_kanal_satu", [k for k in setelan.get("kanal_satu", KANAL_SATU_DEFAULT) if k in KANAL_SEMUA])
init("s_kanal_banyak", [k for k in setelan.get("kanal_banyak", KANAL_BANYAK_DEFAULT) if k in KANAL_SEMUA])
init("s_interval", int(setelan.get("interval", 15)))
for k_ in ("newsapi", "gnews", "newsdata", "claude_key", "sec_email"):
    init(f"s_{k_}", setelan.get(k_, ""))
init("s_model", setelan.get("model", list(MODEL_CLAUDE)[0]))
init("s_n", int(setelan.get("n_periode", 30)))
init("s_satuan", setelan.get("satuan", "hari"))

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📡 Emiten Intelligence")
    mode = st.segmented_control("Mode data", ["Live", "Demo"], default=setelan.get("mode", "Live"), required=True,
                                help="Live = berita sungguhan dari internet. Demo = perusahaan & berita fiktif untuk "
                                     "mencoba semua halaman tanpa internet.")
    with st.expander("🧠 Mesin sentimen", expanded=False):
        mesin = st.radio("Mesin", MESIN, index=MESIN.index(setelan["mesin"]) if setelan.get("mesin") in MESIN else 0,
                         label_visibility="collapsed")
        model_id = "hemat"
        if mesin.startswith("IndoBERT"):
            varian = st.selectbox("Model Indonesia", ["Hemat RAM (~475 MB)", "Besar (~1,34 GB; risiko RAM tinggi)"],
                                  key="s_varian_indobert",
                                  help="FinBERT (~438 MB) hanya diunduh saat ada artikel bahasa Inggris. "
                                       "Bobot model disimpan di cache runtime, berita tetap hanya di memori sesi.")
            model_id = "besar" if varian.startswith("Besar") else "hemat"
            k_cache = f"model_id_unduh::{model_id}"
            st.caption("Mengunduh **IndoBERT saja** saat pertama dipilih. Model FinBERT diunduh "
                       "otomatis hanya jika ada berita berbahasa Inggris. Setelah itu model dipakai "
                       "ulang selama cache tersedia. Tidak menyimpan berita historis.")
            if not st.session_state.get(k_cache, False):
                try:
                    with st.spinner("Memeriksa / mengunduh IndoBERT (sekali per cache server) …"):
                        unduh_model_lokal(hanya="id", mode_id=model_id)
                    st.session_state[k_cache] = True
                    st.success("Model Indonesia siap. Model Inggris akan diunduh bila diperlukan.")
                except Exception as ex:
                    st.session_state["model_lokal_gagal"] = str(ex)[:300]
                    st.warning("Model belum dapat diunduh; sementara gunakan kamus atau coba lagi. "
                               f"Detail: {st.session_state['model_lokal_gagal']}")
            else:
                st.caption("✅ File model IndoBERT telah disiapkan dalam cache server.")
        if mesin.startswith("Claude") and not st.session_state["s_claude_key"]:
            st.warning("Isi Claude API key di ⚙️ Pengaturan → Kunci API. Tanpa key, dipakai kamus keuangan.")
    with st.expander("⚙️ Lanjutan"):
        paruh_manual = st.toggle("Atur paruh waktu sendiri", value=bool(setelan.get("paruh_manual", False)),
                                 help="Otomatis = setengah periode (min. 7, maks. 90 hari).")
        paruh_set = st.slider("Paruh waktu bobot kebaruan (hari)", 3, 120, int(setelan.get("paruh", 14)),
                              disabled=not paruh_manual,
                              help="Berita setua nilai ini bobotnya setengah berita hari ini (D pada rumus skor).")
    st.caption("Pemantauan otomatis berbasis berita publik. Bukan rekomendasi beli/jual dan bukan prediksi harga.")

if f"mem_{mode}" not in st.session_state:
    st.session_state[f"mem_{mode}"] = SessionStore()
db = st.session_state[f"mem_{mode}"]
if mode == "Demo":
    siapkan_demo(db)
    emiten = demo.emiten_demo()
    kat_df, kat_ket = pd.DataFrame(columns=kt.KOLOM_KAT), "tidak dipakai di mode demo"
    semua = kt.gabung(emiten, None)
else:
    if "emiten_personal" not in st.session_state:
        st.session_state["emiten_personal"] = em.default_emiten()
    emiten = st.session_state["emiten_personal"].copy()
    if "katalog_sesi" not in st.session_state:
        st.session_state["katalog_sesi"] = kt.muat(DATA)
    kat_df, kat_ket = st.session_state["katalog_sesi"]
    semua = kt.gabung(emiten, kt.ke_emiten(kat_df))
rss_df = st.session_state.get("rss_df", muat_tabel(RSS_XLSX, ["Aktif", "Nama", "URL"],
                         [{"Aktif": True, "Nama": n, "URL": u} for n, u in K.RSS_BAWAAN]))
situs_df = st.session_state.get("situs_df", muat_tabel(SITUS_XLSX, ["Aktif", "Situs", "Bahasa", "Nama"],
                       [{"Aktif": True, "Situs": d, "Bahasa": b, "Nama": n} for d, b, n in K.SITUS_BAWAAN]))
rating_df = db.baca_rating()
claude_key = st.session_state["s_claude_key"]
model_claude = MODEL_CLAUDE.get(st.session_state["s_model"], list(MODEL_CLAUDE.values())[0])
kunci = {"newsapi": st.session_state["s_newsapi"], "gnews": st.session_state["s_gnews"],
         "newsdata": st.session_state["s_newsdata"], "sec_email": st.session_state["s_sec_email"]}
_wl_simpan = st.session_state.get("watchlists", {})
watchlist = [w for w in _wl_simpan.get(mode, []) if w in set(semua["Nama"])]
if mode == "Demo" and mode not in _wl_simpan:
    watchlist = emiten["Nama"].tolist()

# ----------------------------------------------------------------------------
# Header + pemilih emiten + periode manual
# ----------------------------------------------------------------------------
st.markdown('<div class="hero"><h1>Emiten Intelligence</h1><p>Analisis sentimen dari tautan berita '
            'nasional/internasional, sumber resmi, dan faktor global — tanpa database.</p></div>',
            unsafe_allow_html=True)
st.caption("🔒 Tanpa SQL & penyimpanan permanen. Semua data hanya berada di sesi browser. "
           "Unduh laporan bila ingin menyimpan hasilnya sendiri.")
if mode == "Demo":
    st.info("**Mode demo** — semua perusahaan, berita, harga, dan media di sini fiktif. Pilih **Live** di sidebar "
            "untuk memantau emiten sungguhan.", icon="🧪")

info_e = {r["Nama"]: r for _, r in semua.iterrows()}
# Grup hanya untuk identitas/filtrasi GUI, bukan alias berita atau sumber sentimen.
grup_manual = st.session_state.setdefault("grup_manual", {})
INFO_GRUP = {n: grup_mod.info_emiten(e, grup_manual) for n, e in info_e.items()}
daftar = semua.loc[semua["Aktif"].astype(bool), "Nama"].tolist()
_rating_label = {n: rt_mod.status_rating(rating_df, n, (e.get("Lembaga Utama") or ""))["Rating"]
                 for n, e in info_e.items() if e.get("Asal") == "Daftar saya"}
LABEL = {}
for n, e in info_e.items():
    if e.get("Asal") == "Katalog BEI":
        LABEL[n] = f"{n}  ·  {e['Entitas']}  ·  {INFO_GRUP[n]['grup']}  ·  {e['Sektor BEI'] or e['Sektor']}"
    else:
        LABEL[n] = "  ·  ".join(x for x in (e["Kode"], kt.inti_nama(e["Entitas"]), INFO_GRUP[n]["grup"], _rating_label.get(n)) if x)


def _cari_emiten():
    """Callback pemilih: teks bebas (kode/merek/anak usaha) → emiten di daftar bila dikenali."""
    v = st.session_state.get("pilih_emiten")
    if v and v not in info_e:
        hit = em.cari(semua, v)
        if hit:
            st.session_state["pilih_emiten"] = hit
            st.session_state["info_cari"] = f"“{v}” dikenali sebagai **{hit}**."
    st.session_state.pop("n_tampil", None)


def label_emiten(n: str) -> str:
    return LABEL.get(n) or f"✏️ {n} (di luar katalog)"


def label_pendek(n: str) -> str:
    e = info_e.get(n)
    if e is None:
        return n
    return f"{n} · {kt.inti_nama(e['Entitas'])}" if e.get("Asal") == "Katalog BEI" else \
        (f"{e['Kode']} · {n}" if e["Kode"] else n)


init("pilih_emiten", None)
cur = st.session_state.get("pilih_emiten")
opsi = daftar + ([cur] if cur and cur not in daftar else [])
c1, c2, c3, c4, c5 = st.columns([3.1, 0.85, 1.4, 1.2, 1.45], vertical_alignment="bottom")
pilih = c1.selectbox("Emiten · Grup (kode, nama, atau merek)", opsi, key="pilih_emiten", format_func=label_emiten,
                     accept_new_options=(mode == "Live"), filter_mode="fuzzy", on_change=_cari_emiten,
                     placeholder="Ketik kode/nama: BBRI, AADI, GOTO, Telkomsel, Indomie …")
if pilih in INFO_GRUP:
    g = INFO_GRUP[pilih]
    c1.caption(f"🏢 **Grup: {g['grup']}** · {g['sumber']}")
c2.number_input("Periode", 1, 120, key="s_n", help="Tulis angka periode berita, lalu pilih satuannya: hari, minggu, "
                                                     "bulan, atau tahun terakhir.")
c3.selectbox("Satuan", list(SATUAN), key="s_satuan", format_func=lambda u: f"{u} terakhir")
hari = int(min(st.session_state["s_n"] * SATUAN[st.session_state["s_satuan"]], 3650))
periode = f"{st.session_state['s_n']} {st.session_state['s_satuan']} terakhir"
paruh = float(paruh_set) if paruh_manual else float(min(90, max(7, hari / 2)))
tombol_refresh = c4.button("🔄 Refresh", type="primary", width="stretch", disabled=(mode == "Demo" or not pilih),
                           help="Ambil berita & dokumen terbaru dari semua sumber sekarang.")
c5.toggle(f"Auto {st.session_state['s_interval']} mnt", key="auto_refresh", disabled=(mode == "Demo"),
          help="Near-real-time: selama halaman terbuka, berita emiten ini diambil ulang otomatis. Untuk pemantauan "
               "hanya berjalan selama sesi browser terbuka. Tidak ada pembaruan di latar belakang.")
if st.session_state.get("info_cari"):
    st.toast(st.session_state.pop("info_cari"), icon="🔎")
if mode == "Live":
    n_kat = int((semua["Asal"] == "Katalog BEI").sum())
    st.caption(f"📚 Pilihan: **{len(emiten)} emiten di daftar saya** (dengan rating) + **{n_kat} emiten BEI lainnya** "
               f"dari katalog ({kat_ket}). Perusahaan di luar bursa bisa diketik langsung.")


# ----------------------------------------------------------------------------
# Pengambilan berita & analisis
# ----------------------------------------------------------------------------
def ambil(e_sel: pd.DataFrame, kanal: list[str], judul: str, longgar: bool) -> bool:
    if not kanal:
        st.warning("Belum ada sumber berita yang dipilih (⚙️ Pengaturan → Sumber berita).")
        return False
    mulai = datetime.now(timezone.utc).replace(microsecond=0)
    with st.status(judul, expanded=True) as s:
        bar = st.progress(0.0, text="Menyiapkan …")

        def prog(i, n, teks):
            bar.progress(min(i / max(n, 1), 1.0), text=f"{i}/{n} · {teks}")

        rss_list = [(r["Nama"], r["URL"]) for _, r in rss_df.iterrows() if r["Aktif"] and r["URL"]]
        situs = [(r["Situs"], r["Bahasa"]) for _, r in situs_df.iterrows() if r["Aktif"] and r["Situs"]]
        df, log = sumber.kumpulkan(e_sel, kanal, hari, rss_list, kunci, progress=prog, situs=situs, longgar=longgar)
        frames = [df]
        if K.K_FAKTOR in kanal:
            sektor_col = e_sel["Sektor"].fillna("").replace("", "Lainnya")
            for sek, g in e_sel.groupby(sektor_col):
                s.update(label=f"Global Impact: faktor sektor {sek} …")
                df_f, log_f = sumber.kumpulkan_faktor(sek, intel.faktor_sektor(sek), hari, progress=prog)
                log = pd.concat([log, log_f], ignore_index=True)
                if not df_f.empty:
                    frames += [df_f.assign(emiten=n) for n in g["Nama"]]
        isi = [f for f in frames if not f.empty]
        df = pd.concat(isi, ignore_index=True) if isi else df
        db.tambah_log(log)
        for kd_, inf_ in list(sumber.INFO_IDX.items()):        # kelengkapan halaman IDX (monitor cakupan)
            db.set_meta(f"idx::{kd_}", json.dumps(inf_))
        ok = int((log["Status"] == "OK").sum()) if not log.empty else 0
        gagal = int((log["Status"] == "Gagal").sum()) if not log.empty else 0
        ada = db.id_ada()
        baru = df[[(i, e) not in ada for i, e in zip(df["id"], df["emiten"])]] if not df.empty else df
        if not baru.empty:
            m = mesin if not ((mesin.startswith("Claude") and not claude_key) or
                             (mesin.startswith("IndoBERT") and not st.session_state.get(f"model_id_unduh::{model_id}"))) \
                else MESIN[0]
            e_all = pd.concat([semua, e_sel], ignore_index=True).drop_duplicates("Nama", keep="last")
            try:
                baru = analisis.nilai_artikel(baru, e_all, m, claude_key, model_claude, progress=prog,
                                                 model_id=model_id)
            except (ImportError, RuntimeError, OSError, MemoryError) as ex:
                st.error(f"Model lokal tidak dapat berjalan ({str(ex)[:180]}). Memakai kamus keuangan.")
                baru = analisis.nilai_artikel(baru, e_all, MESIN[0], progress=prog)
            db.simpan_berita(baru)
        if ok:
            for n in e_sel["Nama"]:
                db.set_meta(f"refresh::{n}", mulai.isoformat())
                db.set_meta(f"hari::{n}", str(max(hari, int(db.get_meta(f"hari::{n}", "0") or 0))))
                db.set_meta(f"log::{n}", json.dumps({"ok": ok, "gagal": gagal}))
        s.update(label=f"Selesai: {len(df)} berita relevan · {len(baru)} baru · {ok} dari {len(log)} permintaan "
                       "berhasil", state="complete" if ok else "error", expanded=False)
    if not ok and not log.empty:
        st.error("Semua permintaan gagal. Pastikan komputer terhubung ke internet dan situs berita tidak diblokir "
                 "jaringan kantor. Rinciannya ada di ⚙️ Pengaturan → Log.")
    return bool(ok)


def hitung(d: pd.DataFrame, nama: str, hari: int, paruh: float, sektor: str, ir: str, nama_list: tuple,
           log_ok: int, log_gagal: int, t_refresh: str, pola_items: tuple = ()) -> dict:
    """Analisis dari artikel sesi saat ini, tanpa SQL / penyimpanan di disk."""
    pola = sumber.pola_emiten(pd.Series(dict(pola_items))) if pola_items else None
    x = intel.perkaya(d, sektor or "Lainnya", ir, pola)
    ev = intel.peristiwa(x, list(nama_list), paruh)
    s = intel.skor_0_100(ev)
    tren = intel.tren_skor(ev, hari, paruh)
    sk_lalu = None
    if tren["Skor"].notna().any():
        t2 = tren.dropna(subset=["Skor"])
        lalu7 = t2[t2["Tanggal"] <= t2["Tanggal"].max() - pd.Timedelta(days=7)]
        sk_lalu = float(lalu7["Skor"].iloc[-1]) if not lalu7.empty else None
    log = pd.DataFrame({"Status": ["OK"] * log_ok + ["Gagal"] * log_gagal})
    risiko = intel.tingkat_risiko(ev, s)
    return {"x": x, "ev": ev, "skor": s, "skor_7": sk_lalu, "band": intel.band(s), "keyakinan": intel.keyakinan(ev),
            "cakupan": intel.cakupan_sumber(x, log), "risiko": risiko, "tren": tren,
            "kesegaran": intel.kesegaran(x, pd.to_datetime(t_refresh, utc=True) if t_refresh else None),
            "alerts": intel.peringatan(nama, ev, tren), "ref": intel.referensi(ev),
            "ringkasan": intel.ringkasan_aturan(nama, ev, s, risiko, f"{hari} hari terakhir")}


def nama_pola(e) -> tuple:
    return tuple(dict.fromkeys([x.strip('"') for x in em.pisah(e.get("Alias", "")) + em.pisah(e.get("Kueri", ""))]
                               + [e.get("Kode") or "", e.get("Entitas") or "", e.get("Nama") or ""]))


POLA_KOLOM = ("Nama", "Kode", "Alias", "Kueri", "Pengecualian", "Entitas", "Terkait")


def analisa(e) -> dict:
    n = e["Nama"]
    lg = json.loads(db.get_meta(f"log::{n}", "{}") or "{}")
    return hitung(db.baca_berita(hari=hari, emiten=[n]), n, hari, paruh,
                  e.get("Sektor") or "Lainnya", e.get("Website IR") or "",
                  nama_pola(e), int(lg.get("ok", 0)), int(lg.get("gagal", 0)),
                  db.get_meta(f"refresh::{n}", "") or "",
                  tuple((k, str(e.get(k) if e.get(k) is not None else "")) for k in POLA_KOLOM))


@st.cache_data(ttl=3600, show_spinner=False)
def harga_yahoo(sym: str, hari: int) -> pd.DataFrame:
    return pasar.yahoo_harga(sym, hari)


def data_ihsg() -> tuple[pd.DataFrame | None, str]:
    """IHSG sebagai pembanding pasar: unggahan CSV → demo → Yahoo Finance (^JKSE)."""
    up = st.session_state.get("ihsg_csv")
    if up is not None:
        return up, "CSV IHSG unggahan"
    if mode == "Demo":
        return pasar._rapikan(demo.indeks_demo(max(hari, 400))), "IHSG fiktif (demo)"
    try:
        return harga_yahoo("^JKSE", max(hari, 120)), "IHSG (Yahoo Finance ^JKSE)"
    except Exception as ex:  # noqa: BLE001
        return None, f"IHSG tidak bisa diambil ({str(ex)[:60]})"


def data_harga(e) -> tuple[pd.DataFrame | None, str]:
    """Harga: unggahan CSV (sesi ini) → demo → Yahoo Finance."""
    up = st.session_state.get(f"harga_csv::{e['Nama']}")
    if up is not None:
        return up, "CSV unggahan"
    if mode == "Demo":
        return pasar._rapikan(demo.harga_demo(e["Kode"], max(hari, 400))), "harga fiktif (demo)"
    sym = st.session_state.get(f"sym::{e['Nama']}") or (f"{e['Kode']}.JK" if re.fullmatch(r"[A-Z]{4}",
                                                                                         str(e["Kode"] or "")) else "")
    if not sym:
        return None, "kode saham belum diisi"
    try:
        return harga_yahoo(sym, max(hari, 60)), f"Yahoo Finance ({sym})"
    except Exception as ex:  # noqa: BLE001
        return None, f"Yahoo Finance tidak bisa diakses ({str(ex)[:80]})"


def simpan_alert(n: str, alerts: list):
    """Catat peringatan dalam memori sesi; tanpa Telegram / email."""
    if mode == "Live" and alerts:
        db.simpan_peringatan(n, alerts)


# ----------------------------------------------------------------------------
# Emiten terpilih (dalam daftar / diketik sendiri)
# ----------------------------------------------------------------------------
e_row = None
if pilih and pilih in info_e:
    e_row = info_e[pilih]
elif pilih:
    with st.container(border=True):
        st.markdown(f"**“{esc(pilih)}” tidak ada di daftar emiten.** Lengkapi datanya agar pencarian tepat sasaran "
                    "(nama perusahaan lengkap + kode saham), lalu klik **🔄 Refresh**.")
        kode_tebak = pilih.strip().upper() if re.fullmatch(r"[A-Za-z]{4}", pilih.strip()) else ""
        k1, k2, k3, k4 = st.columns([2.4, 0.9, 1.6, 2.2])
        nm_l = k1.text_input("Nama perusahaan", value="" if kode_tebak else pilih, key=f"lain_nama::{pilih}",
                             placeholder="mis. PT Aneka Tambang Tbk")
        kd_l = k2.text_input("Kode saham", value=kode_tebak, key=f"lain_kode::{pilih}", max_chars=6)
        sk_l = k3.selectbox("Sektor", intel.SEKTOR_LIST, index=intel.SEKTOR_LIST.index("Lainnya"),
                            key=f"lain_sek::{pilih}", help="Menentukan faktor global yang dipantau (Global Impact).")
        al_l = k4.text_input("Alias / merek / anak usaha (pisah ;)", key=f"lain_alias::{pilih}",
                             placeholder="mis. Antam; Logam Mulia")
        if (nm_l or kd_l).strip():
            e_row = em.emiten_kustom(nm_l or kd_l, kd_l, al_l)
            e_row["Sektor"] = sk_l
            e_row["Nama"] = pilih

            def _simpan_lain(row=e_row):
                d0 = st.session_state["emiten_personal"]
                row = row.copy()
                row["Nama"] = em.key_group(row["Entitas"])
                if row["Nama"] not in set(d0["Nama"]):
                    st.session_state["emiten_personal"] = em.rapikan(pd.concat([d0, row.to_frame().T], ignore_index=True))
                st.session_state["pilih_emiten"] = row["Nama"]

            st.button("➕ Tambah ke daftar sesi", on_click=_simpan_lain,
                      help="Tersedia sampai sesi browser ini berakhir.")

nama, A, harga, sumber_harga, terakhir = None, None, None, "", pd.NaT
if e_row is not None:
    nama = e_row["Nama"]
    terakhir = pd.to_datetime(db.get_meta(f"refresh::{nama}"), utc=True, errors="coerce")
    hari_ada = int(db.get_meta(f"hari::{nama}", "0") or 0)
    basi = pd.isna(terakhir) or (pd.Timestamp.now(tz="UTC") - terakhir) > pd.Timedelta(hours=6)
    sudah_auto = st.session_state.setdefault("sudah_auto", set())
    minta = st.session_state.pop("minta_refresh", None) == nama
    if mode == "Live" and (tombol_refresh or minta or ((basi or hari > hari_ada) and (nama, hari) not in sudah_auto)):
        sudah_auto.add((nama, hari))
        e_df = e_row.to_frame().T.assign(Aktif=True).reset_index(drop=True)
        ambil(e_df, st.session_state["s_kanal_satu"],
              f"Mengumpulkan informasi {nama} ({periode}) dari {len(st.session_state['s_kanal_satu'])} kanal …",
              longgar=False)  # Hanya berita dengan bukti hubungan; hasil pencarian lemah tidak disimpan.
        terakhir = pd.to_datetime(db.get_meta(f"refresh::{nama}"), utc=True, errors="coerce")
    A = analisa(e_row)
    simpan_alert(nama, A["alerts"])
    harga, sumber_harga = data_harga(e_row)

tab_ov, tab_news, tab_glob, tab_mkt, tab_watch, tab_ai, tab_set, tab_help = st.tabs(
    ["📊 Overview", "📰 News Intelligence", "🌐 Global Impact", "📈 Market Analytics",
     "⭐ Watchlist & Reports", "💬 Ask AI", "⚙️ Pengaturan", "❓ Panduan"], key="tab_utama")


def kartu_peristiwa(ev: pd.DataFrame, maks: int, batas_baru=None):
    out = []
    for _, r in ev.head(maks).iterrows():
        baru = (batas_baru is not None and pd.notna(r["terbit_akhir"]) and
                r["terbit"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2))
        chips = (chip("🆕 BARU", "baru") if baru else "") + \
            chip(f"Sentimen {r['label'].lower()}", KLS_LABEL.get(r["label"], "net")) + \
            chip(f"Dampak: {r['dampak_label'].lower()}", KLS_DAMPAK.get(r["dampak_label"], "net")) + \
            chip(f"{intel.VERIF_IKON.get(r['verifikasi'], '')} {r['konfirmasi']}", KLS_VERIF.get(r["verifikasi"], "unv"))
        if r.get("konflik"):
            chips += chip("⚠️ Informasi bertentangan", "rum")
        rel = r["relasi"] + (f" · {r['faktor']}" if r["relasi"] == "Tidak langsung" and r.get("faktor") else "")
        chips += chip(rel, "rel")
        info_s = r.get("sumber_info") if isinstance(r.get("sumber_info"), list) else []
        lain = r["sumber_list"][1:] if isinstance(r["sumber_list"], list) else []
        det = ""
        if len(info_s) > 1:
            det = (f'<details><summary>{len(info_s)} artikel · asal: {esc(r.get("asal_sumber") or "")}</summary>' +
                   "".join(f'<div>{intel.ASAL_IKON.get(x["asal"], "")} {esc(x["asal"].lower())} · '
                           f'{intel.VERIF_IKON.get(x["verifikasi"], "")} <a href="{esc(x["url"])}" target="_blank" '
                           f'rel="noopener">{esc(x["sumber"])}</a></div>' for x in info_s)
                   + '<div style="margin-top:3px">📰 liputan sendiri = dihitung sumber independen · 📣 siaran pers '
                     '= semua dihitung satu sumber asal · 📋 salinan = mengutip/menyalin media lain</div></details>')
        elif lain:
            det = (f'<details><summary>+{len(lain)} sumber lain memberitakan peristiwa ini</summary>' +
                   "".join(f'<div>{intel.VERIF_IKON.get(v, "")} <a href="{esc(u)}" target="_blank" rel="noopener">'
                           f'{esc(s_)}</a></div>' for s_, u, v in lain) + "</details>")
        asp = f" · aspek: {esc(r['aspek'])}" if r.get("aspek") else ""
        kat = "Faktor eksternal" if r["relasi"] == "Tidak langsung" else r["pendorong"]
        out.append(
            f'<div class="ev">{chips}<br><a class="j" href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'{esc(r["judul"])}</a><div class="meta">{esc(r["sumber"])} · {wib(r["terbit"])} ({lalu(r["terbit"])})'
            f' · {esc(kat)} · materialitas {intel.label_materialitas(r["M"]).lower()}{asp}</div>'
            + (f'<div class="meta">🔗 Kenapa dikaitkan: {esc(r["kaitan"])}</div>' if r.get("kaitan") else "")
            + (f'<div class="meta">⚠️ Bertentangan: {esc(r["konflik"])}</div>' if r.get("konflik") else "")
            + f'<div class="ai">🤖 {esc(r["penjelasan"])}</div>{det}</div>')
    st.markdown("\n".join(out), unsafe_allow_html=True)


def kartu_artikel(berita: pd.DataFrame) -> None:
    """Berita individual terbaru (bukan peristiwa gabungan): sudah melewati validasi relasi."""
    out = []
    for _, r in berita.iterrows():
        lab = str(r.get("label") or "Netral")
        dam = str(r.get("dampak_label") or "Belum dapat disimpulkan")
        rel = str(r.get("relasi") or "")
        chips = (chip(f"Sentimen {lab.lower()}", KLS_LABEL.get(lab, "net")) +
                 chip(f"Dampak: {dam.lower()}", KLS_DAMPAK.get(dam, "mix")) +
                 chip(rel, "rel"))
        nama_faktor = f" · {esc(r.get('faktor'))}" if rel == "Tidak langsung" and r.get("faktor") else ""
        kaitan = str(r.get("kaitan") or "")
        sumber = esc(r.get("sumber"))
        terbit = r.get("terbit")
        out.append(
            f'<div class="ev">{chips}<br>'
            f'<a class="j" href="{esc(r.get("url"))}" target="_blank" rel="noopener">{esc(r.get("judul"))}</a>'
            f'<div class="meta">{sumber} · {wib(terbit)} ({lalu(terbit)}){nama_faktor}</div>'
            + (f'<div class="meta">🔗 Kenapa terkait: {esc(kaitan)}</div>' if kaitan else "")
            + (f'<div class="ai">{esc(r.get("penjelasan"))}</div>' if r.get("penjelasan") else "")
            + '</div>')
    st.markdown("\n".join(out), unsafe_allow_html=True)


def halaman_artikel(df: pd.DataFrame, key: str, ukuran: int = 20) -> None:
    """Paginasi 20 berita per halaman dengan hitungan jujur (hanya artikel yang terkumpul)."""
    if df.empty:
        st.caption("Tidak ada berita yang memenuhi filter ini.")
        return
    df = df.sort_values("terbit", ascending=False, na_position="last", kind="stable")
    total = len(df)
    n_halaman = (total + ukuran - 1) // ukuran
    key_h = f"halaman_{key}"
    st.session_state[key_h] = min(n_halaman, max(1, int(st.session_state.get(key_h, 1))))
    nomor = st.session_state[key_h]
    awal = (nomor - 1) * ukuran
    kartu_artikel(df.iloc[awal:awal + ukuran])
    st.caption(f"**Menampilkan {angka(awal + 1)}–{angka(min(awal + ukuran, total))} "
               f"dari {angka(total)} berita relevan** · halaman {nomor} dari {n_halaman}. "
               "Total adalah berita yang benar-benar berhasil dikumpulkan, bukan estimasi jumlah di internet.")
    k1, k2, k3 = st.columns([1.2, 1.6, 1.2], vertical_alignment="bottom")
    def pindah(arah):
        st.session_state[key_h] = min(n_halaman, max(1, st.session_state[key_h] + arah))
    k1.button("← Sebelumnya", key=f"prev_{key}", disabled=nomor <= 1, on_click=pindah, args=(-1,),
              width="stretch")
    k2.number_input("Buka halaman", min_value=1, max_value=n_halaman, step=1,
                    key=key_h, help="Ketik nomor halaman untuk menuju berita yang lebih lama.")
    k3.button("Berikutnya →", key=f"next_{key}", disabled=nomor >= n_halaman, on_click=pindah, args=(1,),
              width="stretch")


def html_pemicu(berita: list, maks: int = 80) -> str:
    """Daftar berita pemicu peringatan (judul → artikel asli, sumber, waktu, dampak, verifikasi, sumber lain)."""
    out = []
    for b_ in (berita or [])[:maks]:
        t_ = pd.to_datetime(b_.get("waktu") or None, utc=True, errors="coerce")
        lain = b_.get("lain") or []
        meta = [esc(b_.get("sumber", "")), wib(t_)]
        if b_.get("kategori"):
            meta.append(esc(b_["kategori"]))
        if b_.get("relasi") and b_["relasi"] != "Langsung":
            meta.append(esc(b_["relasi"].lower()))
        out.append(
            f'<li><a class="j" href="{esc(b_.get("url", ""))}" target="_blank" rel="noopener">{esc(b_.get("judul", ""))}'
            f'</a><div class="meta">{" · ".join(m for m in meta if m)} '
            + (chip(f"Dampak: {b_['dampak'].lower()}", KLS_DAMPAK.get(b_["dampak"], "net")) if b_.get("dampak") else "")
            + (chip(b_["verifikasi"], "rel") if b_.get("verifikasi") else "")
            + ("<br>Juga diberitakan: " + ", ".join(f'<a href="{esc(x.get("url", ""))}" target="_blank" '
                                                    f'rel="noopener">{esc(x.get("sumber", ""))}</a>' for x in lain)
               if lain else "") + "</div></li>")
    lebih = (f'<div class="sub">… dan {len(berita) - maks} berita lain (lihat ekspor Excel).</div>'
             if berita and len(berita) > maks else "")
    return f'<ol class="pemicu">{"".join(out)}</ol>{lebih}'


def kartu_alert(tingkat: str, jenis: str, judul: str, detail: str, url: str, waktu, berita: list | None,
                emiten: str | None = None, buka: bool = False, terkirim: str | None = None):
    """Satu peringatan sebagai expander: isinya keterangan + SEMUA berita pemicunya."""
    n_b = len(berita or [])
    label = (f"{IKON_TINGKAT.get(tingkat, '•')} {tingkat} · " + (f"**{emiten}** · " if emiten else "") +
             f"{jenis}: {judul}" + (f" · {n_b} berita" if n_b > 1 else ""))
    with st.expander(label, expanded=buka):
        st.markdown(f'<div class="sub">{esc(detail)} · {wib(pd.to_datetime(waktu, utc=True, errors="coerce"))}'
                    + (f' · terkirim {esc(terkirim)}' if terkirim else "") + "</div>", unsafe_allow_html=True)
        if berita:
            st.markdown(html_pemicu(berita), unsafe_allow_html=True)
        elif url:
            st.markdown(f"[Buka berita ↗]({url})")
        else:
            st.caption("Rincian berita pemicu belum tersedia untuk peringatan lama ini (beritanya sudah di luar "
                       "periode analisis).")


def kosong():
    st.info("Pilih atau ketik emiten di kotak **Emiten** di atas — kode saham (BBRI), nama perusahaan, merek "
            "(Telkomsel, Indomie), atau nama grup. Periode berita ditulis bebas: mis. **7 hari**, **3 bulan**, "
            "atau **1 tahun** terakhir.", icon="🔎")


def filter_ev(ev: pd.DataFrame, cak: list, rel: list) -> pd.DataFrame:
    if ev.empty:
        return ev
    e = ev
    if cak and set(cak) != {"Nasional", "Internasional"}:
        e = e[e["cakupan"].fillna("").str.contains("|".join(cak))]
    if not cak:
        return e.iloc[0:0]
    if rel:
        # Hormati pilihan relasi satu per satu; jangan tampilkan entitas terkait saat hanya Langsung dipilih.
        e = e[e["relasi"].isin(rel)]
    else:
        return e.iloc[0:0]
    return e


def info_laporan() -> dict:
    evl = intel.langsung(A["ev"])
    lab = evl["dampak"].map(lambda v: "Positif" if v >= 0.15 else ("Negatif" if v <= -0.15 else "Netral"))
    return {"nama": nama, "kode": e_row.get("Kode"), "entitas": e_row.get("Entitas"), "sektor": e_row.get("Sektor"),
            "periode": periode, "dari": pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=hari),
            "sampai": pd.Timestamp.now(tz="UTC"), "skor": A["skor"], "band": A["band"][0],
            "keyakinan": A["keyakinan"][0], "keyakinan_label": A["keyakinan"][1], "risiko": A["risiko"][0],
            "risiko_alasan": A["risiko"][1], "n_peristiwa": len(evl),
            "n_artikel": int(evl["n_artikel"].sum()) if not evl.empty else 0,
            "positif": int((lab == "Positif").sum()), "negatif": int((lab == "Negatif").sum()),
            "netral": int((lab == "Netral").sum()), "cakupan": A["cakupan"]["teks"],
            "kesegaran": A["kesegaran"]["teks"], "mesin": mesin}


# ============================================================================
# 📊 OVERVIEW
# ============================================================================
with tab_ov:
    if e_row is None:
        kosong()
    else:
        ev, s = A["ev"], A["skor"]
        evl = intel.langsung(ev)
        judul_e = f"{e_row['Kode']} — {e_row['Entitas'] or nama}" if e_row.get("Kode") else (e_row["Entitas"] or nama)
        st.markdown(f"### {esc(judul_e)} · {esc(periode)}")
        st.markdown(f'<p class="sub">{esc(nama)} · sektor {esc(e_row.get("Sektor") or "-")} · diperbarui '
                    f'<b>{lalu(terakhir)}</b></p>', unsafe_allow_html=True)
        if e_row.get("Pemegang saham utama") or e_row.get("Sektor BEI"):
            prof = [f"Sektor BEI: **{e_row['Sektor BEI']}**" if e_row.get("Sektor BEI") else "",
                    f"industri {e_row['Industri']}" if e_row.get("Industri") else "",
                    f"papan {e_row['Papan']}" if e_row.get("Papan") else "",
                    f"tercatat {tgl(pd.to_datetime(e_row['Tgl Pencatatan'], errors='coerce'))}"
                    if e_row.get("Tgl Pencatatan") else "",
                    f"website {e_row['Website IR']}" if e_row.get("Website IR") else ""]
            st.caption(" · ".join(x for x in prof if x) + (
                f"  \nPemegang saham utama (KSEI, {kt.TANGGAL_BAWAAN}): {e_row['Pemegang saham utama']}"
                if e_row.get("Pemegang saham utama") else "") + (
                f"  \nInduk / pemegang pengendali (dipakai sebagai entitas terkait): {e_row['Terkait']}"
                if e_row.get("Asal") == "Katalog BEI" and e_row.get("Terkait") else ""))
        if e_row.get("Asal") == "Katalog BEI" and mode == "Live":
            def _ke_daftar(row=e_row):
                d0 = st.session_state["emiten_personal"]
                if row["Nama"] not in set(d0["Nama"]):
                    st.session_state["emiten_personal"] = em.rapikan(
                        pd.concat([d0, row[em.KOLOM].to_frame().T], ignore_index=True))
                st.session_state["info_cari"] = f"{row['Nama']} ditambahkan ke daftar saya (⚙️ Pengaturan → Daftar emiten)."
            st.button("➕ Tambah ke daftar saya (atur alias, rating, merek)", on_click=_ke_daftar, key=f"ke_daftar_{nama}",
                      help="Emiten katalog sudah bisa dipakai penuh. Tambahkan ke daftar saya bila ingin mengatur "
                           "alias/merek/anak usaha sendiri atau mengisi ratingnya.")
        if A["alerts"]:
            n_al = pd.Series([a.tingkat for a in A["alerts"]]).value_counts()
            st.markdown(f"**🚨 Peringatan dini — {len(A['alerts'])} aktif** (" +
                        ", ".join(f"{IKON_TINGKAT.get(k, '')} {v} {k.lower()}" for k, v in n_al.items()) +
                        "). Buka tiap peringatan untuk melihat semua berita pemicunya.")
            for p in A["alerts"]:
                kartu_alert(p.tingkat, p.jenis, p.judul, p.detail, p.url, p.waktu, p.berita,
                            buka=(p.tingkat == "Kritis"))

        b_nama, _ = A["band"]
        c = st.columns(4)
        c[0].metric("Sentiment Score", f"{s:.0f}/100" if s is not None else "—/100", border=True,
                    delta=(f"{s - A['skor_7']:+.0f} vs 7 hari lalu" if s is not None and A["skor_7"] is not None
                           else None),
                    help="0 = sangat negatif · 50 = netral · 100 = sangat positif. S = 50 + 50·Σ(w·s)/Σw atas "
                         "peristiwa unik; w = relevansi × materialitas × kualitas bukti × kebaruan. Tampil '—' bila "
                         "peristiwa unik < 3.")
        c[1].metric("Berita relevan", f"{len(evl)} peristiwa", border=True,
                    delta=f"{int(evl['n_artikel'].sum()) if not evl.empty else 0} artikel", delta_color="off",
                    delta_arrow="off", help="Artikel tentang peristiwa yang sama digabung menjadi satu peristiwa unik.")
        rk, alasan_rk = A["risiko"]
        c[2].metric("Risk Level", f"{IKON_RISIKO.get(rk, '')} {rk}", border=True,
                    help="Tingkat risiko pemberitaan: " + " · ".join(alasan_rk))
        kseg = A["kesegaran"]
        c[3].metric("Data Freshness", kseg["label"], border=True, delta=kseg["teks"].split(" · ")[0], delta_color="off",
                    delta_arrow="off", help=kseg["teks"] + ". Segar ≤ 1 jam · Cukup ≤ 6 jam · Usang > 6 jam.")
        st.markdown(meter(s), unsafe_allow_html=True)
        st.markdown(chip("🔵 Menguntungkan emiten", "pos") + "  " +
                    chip("🔴 Merugikan emiten", "neg") + "  " +
                    chip("⚪ Campuran / belum pasti", "mix"), unsafe_allow_html=True)
        st.caption("**Arti warna:** arah *potensi dampak pemberitaan* terhadap emiten. "
                   "Bukan bukti bahwa emiten sudah membukukan laba atau rugi bersih. "
                   "Baca sumber asli untuk verifikasi.")
        kk, cv = A["keyakinan"], A["cakupan"]
        log_e = db.baca_log(4000)
        mon_kanal = monitor.kesehatan_kanal(log_e, nama, 14, e_row.get("Sektor"))
        mon_temuan = monitor.kewajaran_jumlah(log_e, db.baca_berita(hari=70, emiten=[nama]), nama)
        mon_idx = json.loads(db.get_meta(f"idx::{e_row.get('Kode')}", "null") or "null")
        mon_ikon, mon_teks = monitor.ringkas(mon_kanal, mon_temuan, pd.DataFrame(), mon_idx)
        st.caption(f"**Kategori:** {b_nama} · **Keyakinan:** {kk[1]}" +
                   (f" ({kk[0]:.0f}/100)" if kk[0] is not None else "") +
                   f" — {kk[2]} · **Cakupan:** {cv['label']} — {cv['teks']}" +
                   (f"  \n**Independensi sumber:** {intel.ringkas_independensi(ev)}"
                    if intel.ringkas_independensi(ev) else ""))
        with st.expander(f"🩺 Cakupan & kesegaran data — {mon_ikon} {mon_teks}", expanded=(mon_ikon == "🔴")):
            st.markdown(f"**Kesegaran:** {A['kesegaran']['teks']} · **Cakupan sumber:** {cv['teks']}")
            if mon_idx:
                st.markdown(f"**Keterbukaan informasi IDX:** {mon_idx.get('diambil', 0)} dokumen diambil"
                            + (f" dari {mon_idx['total']} (ResultCount)" if mon_idx.get("total") is not None else "")
                            + f" dalam {mon_idx.get('halaman', 1)} halaman"
                            + (" — ⚠️ ada yang belum terambil" if mon_idx.get("terpotong") else " — lengkap ✓"))
            if mon_temuan:
                st.markdown("**Kewajaran jumlah berita**  \n" + "  \n".join(f"{t['tingkat']} {t['teks']}"
                                                                          for t in mon_temuan))
            else:
                st.markdown("**Kewajaran jumlah berita:** 🟢 sesuai pola sebelumnya (atau riwayat belum cukup).")
            if mon_kanal.empty:
                st.caption("Kesehatan kanal: belum ada log pengambilan untuk emiten ini (mode demo / belum Refresh).")
            else:
                st.markdown("**Kesehatan kanal (14 hari)**")
                st.dataframe(mon_kanal, hide_index=True, column_config={
                    "Terakhir berhasil": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                    "Berhasil %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%"),
                    "Galat terakhir": st.column_config.TextColumn(width=300)})

        with st.container(border=True):
            ai_ring = st.session_state.get(f"ai_ring::{nama}::{hari}")
            st.markdown("**Ringkasan** " + ("(Claude AI, hanya dari data terkumpul)" if ai_ring else
                                            "(otomatis, berbasis aturan)"))
            st.markdown(ai_ring or A["ringkasan"])
            if rk not in ("Rendah", "—"):
                st.markdown(f"**Kenapa risikonya {rk.lower()}:** " + "; ".join(alasan_rk) + ".")
            if claude_key and A["ref"] and not ai_ring:
                if st.button("✨ Ringkas dengan Claude AI", key=f"btn_ring_{nama}"):
                    with st.spinner("Claude merangkum peristiwa yang terkumpul …"):
                        try:
                            st.session_state[f"ai_ring::{nama}::{hari}"] = MesinClaude(claude_key, model_claude).tanya(
                                e_row["Entitas"] or nama, "Ringkas perkembangan terpenting, faktor penekan & pendukung, "
                                "dan hal yang perlu dipantau (maks 150 kata).", A["ref"], periode)
                            st.rerun()
                        except Exception as ex:  # noqa: BLE001
                            st.error(f"Gagal memanggil Claude API: {ex}")

        kiri, kanan = st.columns([1.12, 1], gap="large")
        with kiri:
            st.markdown("#### Sentiment Trend vs Stock Price")
            charts(grafik.tren_vs_harga(A["tren"], hari, harga),
                   "Panel bertumpuk: skor sentimen harian 0–100, harga penutupan saham, dan jumlah peristiwa "
                   "positif/negatif per hari.")
            st.caption(f"Harga: {sumber_harga}. Panel terpisah dengan sumbu waktu yang sama (bukan grafik dua sumbu). "
                       + pasar.CATATAN)
        with kanan:
            st.markdown("#### 📰 20 Berita Terbaru yang Relevan")
            st.caption("Memuat berita langsung tentang emiten, anak usaha yang relevan, serta faktor "
                       "sektor yang memiliki bukti hubungan. Berita tanpa hubungan tidak dimasukkan.")
            f1, f2 = st.columns(2)
            cak_f = f1.pills("Cakupan", ["Nasional", "Internasional"], selection_mode="multi",
                             default=["Nasional", "Internasional"], key=f"ov_cak_{nama}")
            rel_f = f2.pills("Relasi", ["Langsung", "Entitas terkait", "Tidak langsung"],
                             selection_mode="multi", default=["Langsung", "Entitas terkait", "Tidak langsung"],
                             key=f"ov_rel_{nama}",
                             help="Langsung = menyebut emiten; Entitas terkait = anak usaha/merek yang terdaftar; "
                                  "Tidak langsung = faktor sektor yang terbukti dibahas, bukan kebetulan muncul di pencarian.")
            b_tampil = A["x"].copy()
            if not b_tampil.empty:
                b_tampil = b_tampil[b_tampil["cakupan"].isin(cak_f or []) &
                                    b_tampil["relasi"].isin(rel_f or [])]
            halaman_artikel(b_tampil, f"ov_{nama}", ukuran=20)

        st_r = rt_mod.status_rating(rating_df, nama, e_row.get("Lembaga Utama") or "")
        with st.expander("🏷️ Rating & kenapa naik/turun", expanded=False):
            x_l = A["x"][A["x"]["relasi"] != "Tidak langsung"] if not A["x"].empty else A["x"]
            rk2 = analisis.ringkas_peristiwa(A["ev"], A["tren"])        # skor 0–100 yang sama dengan di atas
            r_full = {**st_r, **rk2, "Emiten": nama}
            r_full["Baru berubah"] = bool(st_r["Tgl Perubahan"] is not None and pd.notna(st_r["Tgl Perubahan"]) and
                                          pd.Timestamp(st_r["Tgl Perubahan"]) >= pd.Timestamp.now() - pd.Timedelta(
                                              days=180))
            r_full["Sinyal"] = analisis.sinyal(r_full)
            riwayat = db.baca_berita(hari=400, emiten=[nama])
            riwayat = riwayat[riwayat["relasi"].fillna("") != "Tidak langsung"]
            st.markdown(analisis.penjelasan(nama, r_full, x_l, hari, paruh, riwayat, e_row))
            rr = rating_df[rating_df["Nama"] == em.key_group(nama)].sort_values("Tanggal", ascending=False)
            if not rr.empty:
                st.dataframe(rr.drop(columns="Nama"), hide_index=True,
                             column_config={"Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                            "Keterangan": st.column_config.TextColumn(width=420)})

# ============================================================================
# 📰 NEWS INTELLIGENCE
# ============================================================================
with tab_news:
    st.caption("🔵 Menguntungkan emiten · 🔴 Merugikan emiten · ⚪ Campuran/belum pasti. "
               "Dampak hanya dinilai untuk berita yang terbukti terkait emiten atau faktor sektor yang "
               "dipetakan. Label sentimen teks ≠ dampak emiten; bukan laba/rugi laporan keuangan.")
    if e_row is None:
        kosong()
    else:
        x, ev = A["x"], A["ev"]
        if x.empty:
            st.info("Belum ada berita untuk emiten ini pada periode yang dipilih. Klik **🔄 Refresh**, perpanjang "
                    "periode, atau periksa alias/kata kunci di ⚙️ Pengaturan → Daftar emiten.", icon="🔎")
        else:
            st.markdown(f"#### {esc(nama)} · {angka(len(x))} artikel → {angka(len(ev))} peristiwa unik · "
                        f"{esc(periode)}")
            g1, g2, g3 = st.columns([2.2, 2.2, 1.8])
            src_f = g1.multiselect("Sumber", sorted(x["sumber"].fillna("").unique()), placeholder="Semua sumber",
                                   key=f"n_src_{nama}")
            top_opsi = [p for p in PENDORONG if p in set(x["pendorong"])] + sorted(
                {f"Faktor: {f}" for f in x["faktor"].dropna() if f})
            top_f = g2.multiselect("Topik", top_opsi, placeholder="Semua topik", key=f"n_top_{nama}")
            t_min = x["terbit"].min().tz_convert("Asia/Jakarta").date()
            t_max = pd.Timestamp.now(tz="Asia/Jakarta").date()
            rentang = g3.date_input("Tanggal", (t_min, t_max), min_value=t_min, max_value=t_max, format="DD/MM/YYYY",
                                    key=f"n_tgl_{nama}_{hari}")
            h1, h2 = st.columns([1.3, 2.2])
            h3, h4, h5 = st.columns([1.6, 1.2, 1.9])
            lab_f = h1.pills("Sentimen teks", ["Positif", "Netral", "Negatif"], selection_mode="multi",
                             default=["Positif", "Netral", "Negatif"], key=f"n_lab_{nama}")
            rel_opsi = ["Langsung", "Entitas terkait", "Tidak langsung"]
            rel_f = h2.pills("Relasi", rel_opsi, selection_mode="multi", default=rel_opsi, key=f"n_rel_{nama}")
            ver_f = h3.multiselect("Verifikasi", list(intel.VERIF_Q), placeholder="Semua status", key=f"n_ver_{nama}")
            cak_f = h4.pills("Cakupan", ["Nasional", "Internasional"], selection_mode="multi",
                             default=["Nasional", "Internasional"], key=f"n_cak_{nama}")
            cari = h5.text_input("Cari di judul / ringkasan", key=f"n_cari_{nama}",
                                 placeholder="mis. dividen, NPL, gugatan")
            tampilan = st.segmented_control("Tampilan", ["Peristiwa unik", "Semua artikel", "Tabel"],
                                            default="Peristiwa unik", key=f"n_view_{nama}")
            b = x.copy()
            if src_f:
                b = b[b["sumber"].isin(src_f)]
            if top_f:
                pd_sel = [t for t in top_f if not t.startswith("Faktor: ")]
                fk_sel = [t[8:] for t in top_f if t.startswith("Faktor: ")]
                b = b[b["pendorong"].isin(pd_sel) | b["faktor"].isin(fk_sel)]
            if isinstance(rentang, (tuple, list)) and len(rentang) == 2:
                tl = b["terbit"].dt.tz_convert("Asia/Jakarta").dt.date
                b = b[(tl >= rentang[0]) & (tl <= rentang[1])]
            b = b[b["label"].isin(lab_f or [])]
            b = b[b["relasi"].isin(rel_f or [])]
            if ver_f:
                b = b[b["verifikasi"].isin(ver_f)]
            b = b[b["cakupan"].isin(cak_f or [])]
            if cari:
                b = b[b["judul"].str.contains(cari, case=False, na=False, regex=False) |
                      b["ringkasan"].fillna("").str.contains(cari, case=False, regex=False)]
            ids = set(b["id"])
            ev_f = ev[ev["artikel"].map(lambda a: bool(ids & set(a)))] if not ev.empty else ev

            with st.expander("📊 Sebaran sentimen (artikel hasil filter)", expanded=True):
                if b.empty:
                    st.caption("Tidak ada artikel untuk filter ini.")
                else:
                    kel = pd.concat([b.assign(Kelompok="Semua"), b.assign(Kelompok=b["cakupan"]),
                                     b.assign(Kelompok="Relasi: " + b["relasi"].fillna(""))], ignore_index=True)
                    urut_kel = (["Semua"] + [k_ for k_ in ("Nasional", "Internasional") if k_ in set(b["cakupan"])] +
                                [f"Relasi: {r_}" for r_ in rel_opsi if r_ in set(b["relasi"])])
                    chart(grafik.batang_divergen(kel, "Kelompok", True, urut_kel, tinggi_baris=34),
                          "Komposisi sentimen teks per cakupan dan relasi.")
                    k1, k2 = st.columns(2, gap="large")
                    top = b["sumber"].value_counts().head(15).index.tolist()
                    with k1:
                        st.markdown(f"##### Per sumber ({len(top)} teratas)")
                        chart(grafik.batang_divergen(b[b["sumber"].isin(top)], "sumber", False, top, tinggi_baris=24),
                              "Jumlah artikel negatif, netral, positif per sumber.")
                    with k2:
                        st.markdown("##### Per topik")
                        urut_p = [p for p in PENDORONG if p in set(b["pendorong"])]
                        chart(grafik.batang_divergen(b, "pendorong", False, urut_p, tinggi_baris=28),
                              "Jumlah artikel negatif, netral, positif per topik.")
                    st.markdown("##### Tiap artikel (klik titik untuk membuka)")
                    chart(grafik.sebaran_berita(b, hari), "Setiap titik satu artikel: waktu terbit dan skor sentimen.")

            st.caption(f"{angka(len(b))} artikel · {angka(len(ev_f))} peristiwa unik · terbaru di atas")
            if tampilan == "Peristiwa unik":
                n_t = st.session_state.get("n_tampil", 25)
                kartu_peristiwa(ev_f, n_t, terakhir if pd.notna(terakhir) else None)
                if len(ev_f) > n_t and st.button(f"Tampilkan 25 lagi ({len(ev_f) - n_t} tersisa)", key="more_ev"):
                    st.session_state["n_tampil"] = n_t + 25
                    st.rerun()
            elif tampilan == "Semua artikel":
                halaman_artikel(b, f"news_{nama}", ukuran=20)
            else:
                st.dataframe(pd.DataFrame({
                    "Terbit (WIB)": b["terbit"].map(wib), "Judul": b["judul"], "Sumber": b["sumber"],
                    "Verifikasi": b["verifikasi"], "Relasi": b["relasi"], "Kenapa dikaitkan": b["kaitan"],
                    "Topik": b["pendorong"],
                    "Faktor": b["faktor"], "Sentimen teks": b["label"], "Skor teks": (b["skor"] * 100).round(0),
                    "Dampak emiten": b["dampak_label"], "Aspek": b["aspek"], "Materialitas": b["materialitas"],
                    "Penjelasan": b["penjelasan"], "Cakupan": b["cakupan"], "Kanal": b["kanal"], "Tautan": b["url"]}),
                    hide_index=True, height=620, column_config={
                        "Judul": st.column_config.TextColumn(width=420),
                        "Skor teks": st.column_config.NumberColumn(format="%+d", width=70),
                        "Materialitas": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f",
                                                                        width=90),
                        "Penjelasan": st.column_config.TextColumn(width=360),
                        "Tautan": st.column_config.LinkColumn(display_text="Buka ↗", width=70)})
            d1, d2, _ = st.columns([1.6, 1.2, 4])
            d1.download_button("⬇️ Excel (peristiwa + artikel)", data=laporan.buat_excel(
                info_laporan(), ev_f, b, [], None, None, A["ringkasan"]),
                file_name=f"Berita_{nama.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            d2.download_button("⬇️ CSV artikel", data=b.drop(columns=["id"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"Berita_{nama.replace(' ', '_')}_{datetime.now():%Y%m%d}.csv",
                               mime="text/csv")

# ============================================================================
# 🌐 GLOBAL IMPACT
# ============================================================================
with tab_glob:
    if e_row is None:
        kosong()
    else:
        sek = e_row.get("Sektor") or "Lainnya"
        ev_fk = A["ev"][A["ev"]["relasi"] == "Tidak langsung"] if not A["ev"].empty else A["ev"]
        rd = intel.radar_faktor(ev_fk, sek)
        st.markdown(f"#### Global & Domestic Impact Radar — {esc(nama)} (sektor {esc(sek)})")
        st.caption("Peristiwa eksternal yang tidak menyebut emiten, tetapi bisa memengaruhi bisnisnya. **Sentimen teks** "
                   "(nada berita) dan **dampak ke emiten** dinilai terpisah: harga emas naik bisa bernada netral, tetapi "
                   "menguntungkan penambang emas dan tidak berdampak pada bank. Arah dampak dibaca dari judul berita + "
                   "peta sensitivitas sektor; bila mekanismenya dua arah, ditandai *campuran / belum pasti*.")
        if K.K_FAKTOR not in st.session_state["s_kanal_satu"]:
            st.warning("Kanal *Global Impact (faktor sektor)* belum aktif di ⚙️ Pengaturan → Sumber berita.")
        if ev_fk.empty and mode == "Live":
            if st.button("🌐 Ambil berita faktor global sekarang", type="primary"):
                ambil(e_row.to_frame().T.assign(Aktif=True).reset_index(drop=True), [K.K_FAKTOR],
                      f"Mengambil berita faktor sektor {sek} …", longgar=False)
                st.rerun()
        st.markdown("##### Dampak bersih per faktor")
        chart(grafik.radar(rd), "Dampak bersih tiap faktor eksternal terhadap emiten, dari merugikan ke menguntungkan.")
        st.markdown("##### Peta sensitivitas sektor")
        st.dataframe(rd[["Faktor", "Sensitivitas", "Peristiwa", "Arah terbaru", "Dampak emiten", "Mekanisme", "URL"]],
                     hide_index=True, height=min(40 + 35 * len(rd), 420), column_config={
                         "Peristiwa": st.column_config.NumberColumn("Berita", width=60),
                         "Mekanisme": st.column_config.TextColumn(width=460),
                         "URL": st.column_config.LinkColumn("Berita terbaru", display_text="Buka ↗", width=90)})
        st.markdown("##### Peristiwa faktor terbaru")
        if ev_fk.empty:
            st.caption("Belum ada berita faktor untuk periode ini.")
        else:
            kartu_peristiwa(ev_fk, 15)

# ----------------------------------------------------------------------------
# Rating news: on-demand, hanya pada sesi aktif, tidak menulis database historis.
# ----------------------------------------------------------------------------
def panel_rating_berita(e, name: str):
    st.markdown("##### 🏷️ Apakah berita memengaruhi rating kredit perusahaan?")
    st.caption("**Rating kredit perusahaan ≠ harga saham.** Hanya pengumuman lembaga pemeringkat yang "
               "dapat mengonfirmasi aksi rating; berita lainnya hanya indikator potensi risiko. "
               "Afirmasi dan rating instrumen tidak disamakan dengan downgrade rating perusahaan.")
    pilihan = st.segmented_control("Rentang pemeriksaan rating", ["30 hari", "90 hari", "1 tahun"],
                                    default="30 hari", key=f"rentang_rating::{name}")
    durasi = {"30 hari": 30, "90 hari": 90, "1 tahun": 365}[pilihan or "30 hari"]
    sumber_pilihan = st.segmented_control("Lembaga rating untuk diperiksa",
                                           ["PEFINDO + Fitch", "PEFINDO", "Fitch"],
                                           default="PEFINDO + Fitch", key=f"sumber_rating::{name}")
    key_r = f"scan_rating::{name}::{durasi}::{sumber_pilihan}"
    scan = st.session_state.get(key_r)
    if st.button(f"🔎 Cari berita & aksi rating ({pilihan})", key=f"scan_rating_btn::{name}",
                 help="Memeriksa rilis resmi PEFINDO dan/atau Fitch serta berita yang relevan."):
        e_df = e.to_frame().T.assign(Aktif=True).reset_index(drop=True)
        laporan_scan = {"resmi": [], "berita": pd.DataFrame(), "status_resmi": "Belum diperiksa",
                        "sumber_ok": 0, "sumber_gagal": 0, "diperiksa": pd.Timestamp.now(tz="UTC")}
        with st.spinner(f"Mencari pengumuman rating dan berita {name} untuk {pilihan} …"):
            kd = str(e.get("Kode") or "").strip().upper()
            sumber_status = []
            if sumber_pilihan in ("PEFINDO", "PEFINDO + Fitch"):
                if kd:
                    try:
                        h = rt_mod.ambil_pefindo(kd)
                        riwayat_rt, rilis = rt_mod.riwayat_pefindo(h, name)
                        laporan_scan["resmi"].extend(rilis)
                        sumber_status.append("PEFINDO: berhasil diakses")
                        if not riwayat_rt.empty:
                            db.tambah_rating(riwayat_rt)
                    except Exception as ex:  # noqa: BLE001
                        sumber_status.append(f"PEFINDO: tidak dapat diverifikasi ({str(ex)[:95]})")
                else:
                    sumber_status.append("PEFINDO: kode emiten tidak tersedia")
            if sumber_pilihan in ("Fitch", "PEFINDO + Fitch"):
                try:
                    fr = rating_fitch.cari(str(e.get("Entitas") or ""), durasi)
                    laporan_scan["resmi"].extend(fr["rilis"])
                    sumber_status.append("Fitch: " + fr["status"])
                    r_fitch = rating_fitch.ke_rating(fr["rilis"], name)
                    if not r_fitch.empty:
                        db.tambah_rating(r_fitch)
                except Exception as ex:  # noqa: BLE001
                    sumber_status.append(f"Fitch: tidak dapat diperiksa ({str(ex)[:95]})")
            laporan_scan["status_resmi"] = " · ".join(sumber_status)
            try:
                daftar_kanal = ["Google News · Indonesia", "Google News · Global (EN)", K.K_RESMI]
                df_r, lg_r = sumber.kumpulkan(e_df, daftar_kanal, durasi,
                                              rss_list=[], kunci=kunci, longgar=False)
                if df_r is not None and not df_r.empty:
                    df_r = intel.perkaya(df_r, e.get("Sektor") or "Lainnya", e.get("Website IR") or "",
                                         sumber.pola_emiten(e))
                laporan_scan["berita"] = df_r
                if lg_r is not None and not lg_r.empty:
                    laporan_scan["sumber_ok"] = int(lg_r["Status"].eq("OK").sum())
                    laporan_scan["sumber_gagal"] = int(lg_r["Status"].eq("Gagal").sum())
            except Exception as ex:  # noqa: BLE001
                laporan_scan["galat_berita"] = str(ex)[:180]
        st.session_state[key_r] = laporan_scan
        scan = laporan_scan

    berita_sesi = db.baca_berita(hari=durasi, emiten=[name])
    extra = scan.get("berita", pd.DataFrame()) if scan else pd.DataFrame()
    if extra is not None and not extra.empty:
        frames = [x for x in (berita_sesi, extra) if x is not None and not x.empty]
        berita_sesi = pd.concat(frames, ignore_index=True).drop_duplicates(["id", "emiten"], keep="last")
    if not berita_sesi.empty:
        berita_sesi = intel.perkaya(berita_sesi, e.get("Sektor") or "Lainnya", e.get("Website IR") or "",
                                    sumber.pola_emiten(e))
    hasil = rating_dampak.telaah_rating(berita_sesi, scan.get("resmi") if scan else [], durasi)
    actual, possible, affirmed = hasil["konfirmasi"], hasil["indikasi"], hasil["afirmasi"]
    peringkat_berubah = actual[actual["Kategori"] == "Perubahan rating terkonfirmasi"] if not actual.empty else actual
    outlook_berubah = actual[actual["Kategori"] == "Perubahan outlook/CreditWatch terkonfirmasi"] if not actual.empty else actual
    cols = st.columns(4)
    cols[0].metric("Upgrade/downgrade resmi", len(peringkat_berubah), border=True)
    cols[1].metric("Outlook/CreditWatch resmi", len(outlook_berubah), border=True)
    cols[2].metric("Berita indikasi rating", len(possible), border=True)
    cols[3].metric("Afirmasi/rating baru", len(affirmed), border=True)
    if not scan:
        st.info("Penelusuran khusus rating belum dijalankan. Analisis awal memakai berita yang sudah "
                "dikumpulkan pada sesi ini. Tekan **Cari berita & aksi rating** untuk pemeriksaan rilis resmi "
                "dan periode yang dipilih.")
    else:
        st.caption(f"Cakupan pencarian: {scan['status_resmi']} · "
                   f"{scan['sumber_ok']} kanal/permintaan berita berhasil, {scan['sumber_gagal']} gagal. "
                   "Hasil hanya dari sumber yang dapat diakses, bukan seluruh internet.")
        if scan.get("galat_berita"):
            st.warning(f"Pencarian berita mengalami gangguan: {scan['galat_berita']}")
    if actual.empty:
        if scan and (scan["sumber_ok"] > 0 or "berhasil diakses" in scan["status_resmi"] or "rilis Fitch resmi ditemukan" in scan["status_resmi"]):
            if possible.empty:
                st.info(f"Tidak ditemukan berita yang **terbukti mengubah rating perusahaan** dalam "
                        f"{pilihan}, maupun indikasi material dari berita yang berhasil diperiksa. "
                        "Ini hanya hasil pencarian, bukan jaminan seluruh rating/sumber telah tercakup.")
            else:
                st.info(f"Tidak ditemukan **upgrade/downgrade atau perubahan outlook terkonfirmasi** "
                        f"dalam {pilihan} dari sumber yang berhasil diperiksa. "
                        "Ada berita berindikasi yang memerlukan verifikasi (lihat di bawah).")
        else:
            st.caption("Belum ada bukti perubahan rating terkonfirmasi dari data yang tersedia. "
                       "Jalankan pencarian dan verifikasi sumber resmi sebelum menyimpulkan.")
    else:
        if peringkat_berubah.empty:
            st.caption(f"Tidak ditemukan upgrade/downgrade rating perusahaan dalam {pilihan} "
                       "pada rilis resmi yang berhasil diperiksa.")
        st.markdown(f"**Pengumuman resmi tentang rating/outlook ({len(actual)})**")
        st.dataframe(actual, hide_index=True, width="stretch",
                     column_config={"Tanggal": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
                                    "URL": st.column_config.LinkColumn("Sumber resmi", display_text="Buka ↗")})
    if possible.empty:
        st.caption(f"Tidak ditemukan berita berindikasi material terhadap rating dalam {pilihan} "
                   "pada data yang berhasil dikumpulkan.")
    else:
        st.markdown(f"**Berita berindikasi risiko/penguatan kredit ({len(possible)})**")
        st.caption("**Hubungan** = Langsung, Entitas terkait, atau Tidak langsung; "
                   "kategori ini adalah *potensi*, bukan bukti perubahan rating.")
        st.dataframe(possible, hide_index=True, width="stretch",
                     column_config={"Tanggal": st.column_config.DatetimeColumn(format="DD/MM/YYYY"),
                                    "URL": st.column_config.LinkColumn("Buka berita", display_text="Buka ↗")})
    if not affirmed.empty:
        with st.expander(f"ℹ️ Afirmasi/rating baru, bukan perubahan rating ({len(affirmed)})"):
            st.dataframe(affirmed, hide_index=True, width="stretch",
                         column_config={"URL": st.column_config.LinkColumn("Rilis resmi", display_text="Buka ↗")})
    st.caption("Metode: *screening* atas judul/ringkasan + rilis resmi, tanpa memprediksi rating. "
               "Untuk keputusan kredit, periksa rating terkini, outlook dan tanggal di PEFINDO/Fitch/Moody's.")


# ============================================================================
# 📈 MARKET ANALYTICS
# ============================================================================
with tab_mkt:
    if e_row is None:
        kosong()
    else:
        st.markdown(f"#### Sentiment Trend & Market Response — {esc(nama)}")
        with st.expander("🏷️ Pengaruh Berita terhadap Rating Kredit Perusahaan", expanded=True):
            panel_rating_berita(e_row, nama)
        s1, s2, s3 = st.columns([1.4, 1.6, 2.6], vertical_alignment="bottom")
        sym0 = f"{e_row['Kode']}.JK" if re.fullmatch(r"[A-Z]{4}", str(e_row.get("Kode") or "")) else ""
        s1.text_input("Simbol Yahoo Finance", value=st.session_state.get(f"sym::{nama}", sym0), key=f"sym_in_{nama}",
                      disabled=(mode == "Demo"), help="Saham IDX: KODE.JK (mis. BBRI.JK). ADR AS: mis. TLK.")
        if s2.button("🔄 Ambil ulang harga", disabled=(mode == "Demo")):
            st.session_state[f"sym::{nama}"] = st.session_state[f"sym_in_{nama}"]
            harga_yahoo.clear()
            st.rerun()
        up = s3.file_uploader("…atau unggah CSV/Excel harga historis (Investing.com, Stockbit, IDX)",
                              type=["csv", "xlsx", "xls"], key=f"up_harga_{nama}")
        if up is not None:
            try:
                st.session_state[f"harga_csv::{nama}"] = pasar.dari_csv(up)
                harga, sumber_harga = st.session_state[f"harga_csv::{nama}"], "CSV unggahan"
            except Exception as ex:  # noqa: BLE001
                st.error(f"File harga tidak terbaca: {ex}")
        if harga is None or harga.empty:
            st.info(f"Data harga belum tersedia ({sumber_harga}). Unggah CSV harga historis untuk melihat hubungan "
                    "sentimen dengan return, volume, dan volatilitas.", icon="📈")
            charts(grafik.tren_vs_harga(A["tren"], hari, None), "Skor sentimen harian dan jumlah peristiwa per hari.")
        else:
            m = pasar.metrik(harga, hari)
            c = st.columns(5)
            c[0].metric("Harga terakhir", f"{m.get('harga', 0):,.0f}".replace(",", "."), border=True,
                        help=f"Per {tgl(m.get('tanggal'))} · sumber: {sumber_harga}")
            c[1].metric(f"Return {periode}", f"{m.get('return', 0):+.1%}", border=True)
            c[2].metric("Volatilitas (tahunan)", f"{m['volatilitas']:.0%}" if m.get("volatilitas") else "—",
                        border=True, help="Simpangan baku return harian × √252.")
            c[3].metric("Volume 5 hari vs rata-rata", f"{m['volume_5h_vs_rata']:+.0%}" if m.get("volume_5h_vs_rata")
                        is not None else "—", border=True)
            c[4].metric("Penurunan terdalam", f"{m.get('drawdown', 0):.1%}", border=True,
                        help="Maximum drawdown dalam periode.")
            charts(grafik.tren_vs_harga(A["tren"], hari, harga),
                   "Skor sentimen harian, harga penutupan, dan peristiwa per hari dengan sumbu waktu yang sama.")
            g = pasar.gabung(harga, A["tren"])
            kr = pasar.korelasi(g)
            with st.expander("Hubungan historis skor sentimen ↔ return", expanded=False):
                if kr.get("n", 0) < 10:
                    st.caption(f"Data bersama sentimen & harga baru {kr.get('n', 0)} hari bursa — minimal 10 untuk "
                               "menghitung korelasi. Perpanjang periode.")
                else:
                    fmt = lambda v: "—" if v is None or pd.isna(v) else f"{v:+.2f}"  # noqa: E731
                    st.markdown(f"- Korelasi peringkat skor sentimen ↔ return **hari yang sama**: "
                                f"**{fmt(kr.get('sama_hari'))}**\n"
                                f"- Skor sentimen hari ini ↔ return **hari bursa berikutnya**: "
                                f"**{fmt(kr.get('hari_berikut'))}**\n"
                                f"- Berdasarkan {kr['n']} hari bursa. |ρ| < 0,2 = lemah; 0,2–0,5 = sedang.")
                st.caption(pasar.CATATAN)

            kd_e = e_row.get("Kode") or nama
            st.markdown(f"#### Reaksi harga setelah peristiwa — apakah berita ini benar-benar memengaruhi {kd_e}?")
            ihsg, sumber_ihsg = data_ihsg()
            r1, r2, r3 = st.columns([2.8, 1.5, 1.7], vertical_alignment="bottom")
            rel_pil = r1.pills("Peristiwa yang dianalisis", ["Langsung", "Entitas terkait", "Tidak langsung"],
                               selection_mode="multi", default=list(pasar.RELASI_REAKSI), key=f"sp_rel2_{nama}",
                               format_func=lambda r_: {"Tidak langsung": "Tidak langsung (faktor)"}.get(r_, r_),
                               help="Langsung = berita/dokumen resmi yang menyebut emiten. Entitas terkait = anak "
                                    "usaha/merek/induk. Tidak langsung = faktor eksternal yang memengaruhi bisnis "
                                    "sektornya (mis. harga minyak, batu bara, CPO, kurs, BI Rate) — hanya yang arah "
                                    "dampaknya jelas. Berita yang hanya muncul di hasil pencarian "
                                    "tanpa bukti kaitan tidak dianalisis.")
            min_m = r2.select_slider("Materialitas minimum", [0.4, 0.55, 0.7, 0.85], value=0.55,
                                     key=f"sp_m_{nama}", format_func=lambda v: {0.4: "semua", 0.55: "sedang+",
                                                                                0.7: "tinggi", 0.85: "sangat tinggi"}[v],
                                     help="Untuk berita emiten. Faktor eksternal (materialitas maks. sedang) ikut "
                                          "selama ambang ≤ sedang.")
            with r3.popover(f"📉 Pembanding: {'IHSG ✓' if ihsg is not None else 'IHSG ✗'}", width="stretch"):
                st.caption(f"Sumber: {sumber_ihsg}. Reaksi saham dikurangi gerak IHSG di hari yang sama, supaya "
                           "kenaikan/penurunan yang hanya ikut pasar tidak dianggap reaksi terhadap berita.")
                up_i = st.file_uploader("Unggah CSV/Excel historis IHSG (opsional)", type=["csv", "xlsx", "xls"],
                                        key="up_ihsg")
                if up_i is not None:
                    try:
                        st.session_state["ihsg_csv"] = pasar.dari_csv(up_i)
                        st.rerun()
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"File IHSG tidak terbaca: {ex}")
            sp = pasar.studi_peristiwa(harga, A["ev"], min_m, ihsg, tuple(rel_pil or ["Langsung"]))
            if sp.empty:
                st.info("Belum ada peristiwa dengan relasi & materialitas ini yang bisa dipasangkan dengan data harga. "
                        "Coba turunkan materialitas atau perpanjang periode.", icon="ℹ️")
            else:
                berp = sp[sp["Berpengaruh"]].reset_index(drop=True)
                info_sp = sp[~sp["Berpengaruh"]].reset_index(drop=True)
                dk = pasar.dasar_kebetulan(harga, ihsg)
                n_tl = int((berp["Relasi"] == "Tidak langsung").sum())
                q1, q2, q3 = st.columns(3)
                q1.metric("Peristiwa dianalisis", len(sp), border=True)
                q2.metric("Berpengaruh ke harga", f"{len(berp)}", border=True,
                          help="Harga bergerak SEARAH dampak berita dan ≥ 1× gerak normal (selisih vs IHSG).")
                q3.metric("Peluang kebetulan", "—" if pd.isna(dk["acak"]) else f"≈ {dk['acak']:.0%}", border=True,
                          help="Seberapa sering harga saham ini bergerak ≥ 1× gerak normal ke satu arah tertentu tanpa "
                               "perlu ada berita (dihitung dari semua hari bursa periode ini). Bila porsi peristiwa "
                               "'berpengaruh' tidak jauh di atas angka ini, hubungan berita–harga secara umum lemah.")
                porsi = len(berp) / len(sp)
                if not pd.isna(dk["acak"]):
                    kes_umum = ("jauh di atas" if porsi >= dk["acak"] * 1.8 else
                                ("sedikit di atas" if porsi > dk["acak"] * 1.2 else
                                 ("setara dengan" if porsi >= dk["acak"] * 0.8 else "di bawah")))
                    st.caption(f"{porsi:.0%} peristiwa tampak berpengaruh — {kes_umum} peluang kebetulan "
                               f"(≈ {dk['acak']:.0%}). " + ("Berita cenderung benar-benar menggerakkan harga saham ini."
                                                            if kes_umum == "jauh di atas" else
                               "Sebagian 'pengaruh' bisa saja kebetulan; baca bersama peristiwa lain di hari yang sama."))
                if berp.empty:
                    st.info("Tidak ada peristiwa yang terbukti berpengaruh: pada semua peristiwa, selisih harga terhadap "
                            "IHSG masih dalam batas gerak normal atau arahnya tidak sesuai dampak berita. Semuanya "
                            "tercatat sebagai informasi di bawah.", icon="ℹ️")
                else:
                    st.markdown(f"##### ✅ Peristiwa yang berpengaruh ({len(berp)}" +
                                (f", termasuk {n_tl} faktor eksternal" if n_tl else "") + ")")
                    st.caption("Batang = selisih return saham terhadap IHSG pada hari bursa pertama setelah berita (H+1). "
                               "Biru = berita tentang emiten, oranye = faktor eksternal (mis. harga minyak). Pekat = "
                               "signifikan (≥ 2× gerak normal), pudar = moderat. Klik batang untuk membuka berita.")
                    chart(grafik.studi_peristiwa(berp.head(30)),
                          "Selisih return saham terhadap IHSG setelah tiap peristiwa yang berpengaruh.")
                    k_ai = f"ai_reaksi::{nama}"
                    if claude_key and st.button("✨ Jelaskan tiap peristiwa dengan Claude AI", key=f"btn_ai_sp_{nama}"):
                        data_ai = [{"id": str(i), "tanggal": f"{r['Tanggal']:%d/%m/%Y}", "judul": r["Peristiwa"],
                                    "kenapa_dikaitkan": r["Kaitan"], "relasi": r["Relasi"], "faktor": r["Faktor"],
                                    "kategori": r["Kategori"], "jalur_dampak": r["Jalur dampak"],
                                    "sentimen": r["Sentimen"], "dampak": r["Dampak"],
                                    "return_saham_h1": None if pd.isna(r["Return H+1"]) else round(r["Return H+1"], 4),
                                    "return_ihsg_h1": None if pd.isna(r["IHSG H+1"]) else round(r["IHSG H+1"], 4),
                                    "selisih_h1": None if pd.isna(r["AR H+1"]) else round(r["AR H+1"], 4),
                                    "kali_gerak_normal": None if pd.isna(r["z"]) else round(r["z"], 1),
                                    "peristiwa_lain_hari_itu": r["Peristiwa lain"][:3]}
                                   for i, r in berp.head(15).iterrows()]
                        with st.spinner("Claude menyusun penjelasan …"):
                            try:
                                hasil_ai = MesinClaude(claude_key, model_claude).jelaskan_reaksi(
                                    e_row["Entitas"] or nama, data_ai)
                                st.session_state[k_ai] = {berp.loc[int(i), "Peristiwa"]: t for i, t in hasil_ai.items()
                                                          if str(i).isdigit() and int(i) in berp.index}
                            except Exception as ex:  # noqa: BLE001
                                st.error(f"Claude API gagal: {ex}")
                    ai_txt = st.session_state.get(k_ai, {})
                    for _, r in berp.head(30).iterrows():
                        ikon_j = "🌐" if r["Relasi"] == "Tidak langsung" else ("🔵" if r["Penilaian"] ==
                                                                              "Searah & signifikan" else "🔷")
                        pref = f"{r['Faktor']} · " if r["Relasi"] == "Tidak langsung" and r["Faktor"] else ""
                        judul_x = (f"{ikon_j} {r['Tanggal']:%d/%m/%Y} · {pasar._fmt(r['AR H+1'])} vs IHSG · {pref}"
                                   f"{r['Peristiwa'][:90]}{'…' if len(r['Peristiwa']) > 90 else ''}")
                        with st.expander(judul_x):
                            lain = r["Peristiwa lain"] or []
                            st.markdown(
                                f"**1 · Kenapa berita ini dikaitkan dengan {kd_e}:** {r['Kaitan'] or '—'}  \n"
                                f"Relasi: *{r['Relasi']}*" + (f" ({r['Faktor']})" if r["Faktor"] else "") +
                                f" · sumber: {r['Sumber']} · {r['Verifikasi']}"
                                + (f" · {int(r['Serupa'])} berita serupa di hari yang sama" if r["Serupa"] else "")
                                + f"\n\n**2 · Bagaimana bisa memengaruhi bisnisnya:** {r['Jalur dampak'] or '—'}  \n"
                                f"Kategori: {r['Kategori']}" + (f" · aspek: {r['Aspek']}" if r["Aspek"] else "") +
                                f" · sentimen teks: {r['Sentimen'].lower()} · dampak ke emiten: {r['Dampak'].lower()}"
                                f"\n\n**3 · Reaksi harga ({r['Penilaian'].lower()}):** {r['Kesimpulan']}\n\n"
                                + ("**Peristiwa lain di hari bursa yang sama:** " +
                                   "; ".join(f"“{x[:90]}”" for x in lain[:4]) + "\n\n" if lain else "")
                                + (f"**✨ Penjelasan Claude:** {ai_txt[r['Peristiwa']]}\n\n"
                                   if r["Peristiwa"] in ai_txt else "")
                                + f"[Buka berita ↗]({r['URL']})")
                            c_ = st.columns(5)
                            c_[0].metric("Saham H+1", pasar._fmt(r["Return H+1"]))
                            c_[1].metric("IHSG H+1", pasar._fmt(r["IHSG H+1"]))
                            c_[2].metric("Selisih H+1", pasar._fmt(r["AR H+1"]))
                            c_[3].metric("Selisih 3 hari", pasar._fmt(r["AR H+3"]))
                            c_[4].metric("× gerak normal",
                                         "—" if pd.isna(r["z"]) else f"{abs(r['z']):.1f}×".replace(".", ","))
                if not info_sp.empty:
                    with st.expander(f"ℹ️ Hanya informasi — {len(info_sp)} peristiwa yang tidak terbukti "
                                     "menggerakkan harga", expanded=berp.empty):
                        hit = info_sp["Penilaian"].value_counts()
                        st.caption(" · ".join(f"{k}: {v}" for k, v in hit.items()) + ". Pilih baris untuk membaca "
                                   "penjelasan lengkapnya.")
                        tb = info_sp.assign(
                            Jenis=np.where(info_sp["Relasi"] == "Tidak langsung", "🌐 " + info_sp["Faktor"],
                                           info_sp["Relasi"]),
                            Saham=info_sp["Return H+1"] * 100, IHSG=info_sp["IHSG H+1"] * 100,
                            Selisih=info_sp["AR H+1"] * 100, Kali=info_sp["z"].abs())
                        sel_i = st.dataframe(
                            tb[["Tanggal", "Peristiwa", "Jenis", "Dampak", "Saham", "IHSG", "Selisih", "Kali",
                                "Penilaian", "Keterangan", "URL"]], hide_index=True, on_select="rerun",
                            selection_mode="single-row", key=f"tbl_info_sp_{nama}",
                            height=min(60 + 35 * len(tb), 420), column_config={
                                "Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY", width=90),
                                "Peristiwa": st.column_config.TextColumn(width=320),
                                "Jenis": st.column_config.TextColumn("Relasi / faktor", width=130),
                                "Dampak": st.column_config.TextColumn("Dampak berita", width=110),
                                "Saham": st.column_config.NumberColumn("Saham H+1", format="%+.2f%%", width=80),
                                "IHSG": st.column_config.NumberColumn("IHSG H+1", format="%+.2f%%", width=80),
                                "Selisih": st.column_config.NumberColumn(format="%+.2f%%", width=80),
                                "Kali": st.column_config.NumberColumn("× normal", format="%.1f×", width=70),
                                "Keterangan": st.column_config.TextColumn(width=280),
                                "URL": st.column_config.LinkColumn("Berita", display_text="Buka ↗", width=70)})
                        rows_i = sel_i.selection.rows if sel_i and sel_i.selection else []
                        if rows_i:
                            r = info_sp.iloc[rows_i[0]]
                            st.markdown(f"**{r['Peristiwa']}**  \n🔗 {r['Kaitan'] or '—'}  \n"
                                        f"⚙️ {r['Jalur dampak'] or '—'}  \n📈 {r['Kesimpulan']}")
                st.caption("Cara membaca: **selisih** = return saham − return IHSG (bagian gerak yang bukan sekadar "
                           "ikut pasar). **× gerak normal** = selisih dibagi simpangan baku selisih harian 60 hari "
                           "bursa sebelumnya; ≥ 2× tergolong tidak biasa. **Berpengaruh** = searah dampak berita dan "
                           "≥ 1×. " + pasar.CATATAN)

# ============================================================================
# ⭐ WATCHLIST & REPORTS
# ============================================================================
with tab_watch:
    st.markdown("#### ⭐ Watchlist & perbandingan emiten")

    def _simpan_watch():
        daftar_w = st.session_state.setdefault("watchlists", {})
        daftar_w[mode] = st.session_state["wl_sel"]

    if st.session_state.get("wl_mode") != mode:      # ganti Live/Demo → muat watchlist mode itu
        st.session_state["wl_sel"] = watchlist
        st.session_state["wl_mode"] = mode
    w1, w2 = st.columns([4, 1.4], vertical_alignment="bottom")
    w1.multiselect("Emiten di watchlist (semua emiten BEI bisa dipilih)", daftar, key="wl_sel",
                   on_change=_simpan_watch, format_func=label_pendek,
                   placeholder="Pilih beberapa emiten untuk dipantau & dibandingkan")
    wl = [w for w in (st.session_state.get("wl_sel") or []) if w in info_e]
    if w2.button("🔄 Refresh watchlist", disabled=(mode == "Demo" or not wl), width="stretch",
                 help="Mengambil berita semua emiten watchlist dengan kanal 'Refresh banyak emiten'."):
        ambil(pd.DataFrame([info_e[n] for n in wl]).assign(Aktif=True), st.session_state["s_kanal_banyak"],
              f"Mengambil berita {len(wl)} emiten watchlist …", longgar=False)
        st.rerun()
    if not wl:
        st.caption("Watchlist kosong. Tambahkan emiten di atas — hanya tersedia selama sesi aplikasi ini.")
    else:
        rows = []
        for n in wl:
            Aw = analisa(info_e[n])
            simpan_alert(n, Aw["alerts"])
            evw = intel.langsung(Aw["ev"])
            mat_neg = int(((evw["M"] >= 0.8) & (evw["dampak"] <= -0.4)).sum()) if not evw.empty else 0
            rows.append({"Emiten": n, "Kode": info_e[n]["Kode"], "Skor": Aw["skor"], "Kategori": Aw["band"][0],
                         "Δ 7 hari": (Aw["skor"] - Aw["skor_7"]) if Aw["skor"] is not None and Aw["skor_7"]
                         is not None else None, "Keyakinan": Aw["keyakinan"][1], "Risiko": Aw["risiko"][0],
                         "Peristiwa": len(evw), "Material negatif": mat_neg,
                         "Peringatan": len([a for a in Aw["alerts"] if a.tingkat in ("Kritis", "Tinggi")]),
                         "Berita terbaru": evw.iloc[0]["judul"] if not evw.empty else "",
                         "Diperbarui": Aw["kesegaran"]["teks"]})
        cmp_ = pd.DataFrame(rows)
        for c_ in ("Skor", "Δ 7 hari"):
            cmp_[c_] = pd.to_numeric(cmp_[c_], errors="coerce").astype(float)
        cmp_["_r"] = cmp_["Risiko"].map({"Kritis": 0, "Tinggi": 1, "Sedang": 2, "Rendah": 3}).fillna(4)
        cmp_ = cmp_.sort_values(["_r", "Skor"], na_position="last").drop(columns="_r").reset_index(drop=True)
        k1, k2 = st.columns([1, 1.6], gap="large")
        with k1:
            chart(grafik.skor_banding(cmp_), "Skor sentimen 0–100 tiap emiten watchlist; batang bertolak dari 50.")
        with k2:
            sel = st.dataframe(
                cmp_.assign(Risiko=cmp_["Risiko"].map(lambda r: f"{IKON_RISIKO.get(r, '')} {r}")), hide_index=True,
                on_select="rerun", selection_mode="single-row", key="tbl_wl",
                column_config={"Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                               "Δ 7 hari": st.column_config.NumberColumn(format="%+.0f"),
                               "Berita terbaru": st.column_config.TextColumn(width=300)})
            rows_sel = sel.selection.rows if sel and sel.selection else []
            if rows_sel:
                nm_sel = cmp_.iloc[rows_sel[0]]["Emiten"]

                def _buka(n_=nm_sel):
                    st.session_state["pilih_emiten"] = n_

                st.button(f"📊 Buka {nm_sel} di Overview", on_click=_buka)

    st.markdown("#### 🚨 Early warning")
    st.caption("Semua peringatan dini yang tercatat, lengkap dengan **berita pemicunya** (buka tiap baris). Peringatan "
               "dibuat saat emiten dianalisis — dibuka di aplikasi, ada di watchlist, atau dipantau terjadwal — dan "
               "hanya dari berita yang menyebut emiten / entitas terkaitnya (hasil pencarian lemah & faktor global "
               "tidak memicu peringatan).")
    e1, e2, e3, e4 = st.columns([2.4, 2.1, 1.3, 1.7], vertical_alignment="bottom")
    cak_al = e1.segmented_control("Emiten", ["Semua emiten", "Watchlist", "Emiten terpilih"],
                                  default="Semua emiten", key="al_cak", required=True,
                                  format_func=lambda v: {"Emiten terpilih": "Emiten ini"}.get(v, v))
    tk_al = e2.pills("Tingkat", ["Kritis", "Tinggi", "Sedang", "Info"], selection_mode="multi",
                     default=["Kritis", "Tinggi", "Sedang", "Info"], key="al_tk")
    hr_al = e3.selectbox("Periode", [3, 7, 30, 90, 365], index=2, format_func=lambda d_: f"{d_} hari terakhir",
                         key="al_hr")
    cari_al = e4.text_input("Cari emiten / judul", key="al_cari", placeholder="mis. BMRI, gugatan")
    KOL_AL = ["kunci", "emiten", "tingkat", "jenis", "judul", "detail", "url", "waktu", "dibuat", "terkirim", "berita"]
    if mode == "Demo":                              # demo: dihitung langsung, tidak dicatat/dikirim
        rows_al = []
        for n_ in daftar:
            for p in analisa(info_e[n_])["alerts"]:
                rows_al.append({"kunci": p.kunci, "emiten": n_, "tingkat": p.tingkat, "jenis": p.jenis,
                                "judul": p.judul, "detail": p.detail, "url": p.url,
                                "waktu": pd.Timestamp(p.waktu).strftime("%Y-%m-%dT%H:%M:%SZ"), "dibuat": None,
                                "terkirim": None, "berita": p.berita})
        al = pd.DataFrame(rows_al, columns=KOL_AL)
    else:
        al = db.baca_peringatan(hari=hr_al, n=2000)
    if not al.empty:
        al = al[pd.to_datetime(al["waktu"], utc=True, errors="coerce") >=
                pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=hr_al)]
        if cak_al == "Watchlist":
            al = al[al["emiten"].isin(wl)]
        elif cak_al == "Emiten terpilih":
            al = al[al["emiten"] == nama] if nama else al.iloc[0:0]
        al = al[al["tingkat"].isin(tk_al or [])]
        if cari_al.strip():
            q_ = cari_al.strip().lower()
            al = al[al["emiten"].str.lower().str.contains(q_, regex=False) |
                    al["judul"].fillna("").str.lower().str.contains(q_, regex=False) |
                    al["emiten"].map(lambda n_: str((info_e.get(n_) or {}).get("Kode") or "").lower() == q_)]
        al = al.assign(_u=al["tingkat"].map({"Kritis": 0, "Tinggi": 1, "Sedang": 2, "Info": 3}).fillna(9),
                       _t=pd.to_datetime(al["waktu"], utc=True, errors="coerce"))
        al = al.sort_values(["_u", "_t"], ascending=[True, False]).drop(columns=["_u", "_t"]).reset_index(drop=True)
    if mode == "Live" and not al.empty and al["berita"].isna().any():
        # peringatan lama (sebelum rincian disimpan): susun ulang daftar berita pemicu dari data yang tersimpan
        for n_, g_ in list(al[al["berita"].isna()].groupby("emiten"))[:12]:
            if n_ not in info_e:
                continue
            ev_n = analisa(info_e[n_])["ev"]
            for i_, r_ in g_.iterrows():
                b_ = intel.pemicu(r_["jenis"], ev_n, pd.Timestamp(r_["waktu"]), r_["url"] or "", r_["judul"] or "")
                if b_:
                    db.isi_rincian(r_["kunci"], b_)
                    al.at[i_, "berita"] = b_
    if mode == "Live":
        ada_data = db.emiten_tersimpan(hari)
        ada_data = [n_ for n_ in ada_data if n_ in info_e]

        def _periksa_semua(daftar_n=tuple(ada_data)):
            for n_ in daftar_n:
                simpan_alert(n_, analisa(info_e[n_])["alerts"])
            st.session_state["info_cari"] = f"Peringatan {len(daftar_n)} emiten diperiksa ulang."
        st.button(f"🔍 Periksa ulang peringatan semua emiten yang punya data ({len(ada_data)})",
                  on_click=_periksa_semua, disabled=not ada_data,
                  help="Menghitung ulang peringatan dari berita yang sudah tersimpan (tanpa mengambil berita baru) "
                       "untuk semua emiten yang pernah diperbarui — termasuk yang tidak ada di watchlist.")
    if al.empty:
        st.caption("Tidak ada peringatan untuk pilihan ini. Peringatan dibuat otomatis saat ada berita material "
                   "negatif, peristiwa kredit, isu hukum/regulasi, rumor material, sentimen turun ≥ 15 poin dalam "
                   "7 hari, atau lonjakan berita negatif.")
    else:
        cnt = al["tingkat"].value_counts()
        m_ = st.columns(5)
        m_[0].metric("Peringatan", len(al), border=True)
        for k_i, t_ in enumerate(["Kritis", "Tinggi", "Sedang", "Info"], start=1):
            m_[k_i].metric(f"{IKON_TINGKAT[t_]} {t_}", int(cnt.get(t_, 0)), border=True)
        ring_al = al.assign(Tingkat=al["tingkat"].map(lambda t_: f"{IKON_TINGKAT.get(t_, '')} {t_}"),
                            Waktu=pd.to_datetime(al["waktu"], utc=True, errors="coerce").map(wib),
                            Pemicu=al["berita"].map(lambda v: len(v) if isinstance(v, list) else 0))
        with st.expander(f"📋 Tabel ringkas {len(al)} peringatan · {al['emiten'].nunique()} emiten"):
            st.dataframe(ring_al[["Tingkat", "emiten", "jenis", "judul", "Pemicu", "detail", "Waktu", "terkirim"]],
                         hide_index=True, height=min(60 + 35 * len(ring_al), 420), column_config={
                             "emiten": "Emiten", "jenis": "Jenis", "detail": "Detail", "terkirim": "Terkirim",
                             "judul": st.column_config.TextColumn("Peringatan", width=340),
                             "Pemicu": st.column_config.NumberColumn("Berita pemicu", format="%d")})
        n_show = 30 if len(al) > 30 else len(al)
        if len(al) > 30:
            n_show = st.number_input("Jumlah peringatan yang ditampilkan", 10, len(al), 30, 10, key="al_n")
        for _, r_ in al.head(int(n_show)).iterrows():
            kartu_alert(r_["tingkat"], r_["jenis"], r_["judul"], r_["detail"] or "", r_["url"] or "", r_["waktu"],
                        r_["berita"] if isinstance(r_["berita"], list) else None, emiten=r_["emiten"],
                        terkirim=r_["terkirim"] if isinstance(r_["terkirim"], str) else None)
    st.caption("Peringatan hanya muncul dalam dashboard selama sesi aktif. "
               "Tidak ada pengiriman otomatis melalui email atau Telegram.")

    st.markdown("#### 📄 AI Research Report")
    if e_row is None:
        st.caption("Pilih emiten di atas untuk membuat laporan.")
    else:
        st.caption(f"Laporan **{nama}** untuk **{periode}**: ringkasan, skor & keyakinan, peristiwa terpenting, faktor "
                   "risiko, skenario dampak, faktor global, data pasar, dan referensi bernomor. "
                   + ("Narasi ditulis Claude AI (hanya dari referensi)." if claude_key else
                      "Tanpa Claude API key, narasi disusun otomatis berbasis aturan."))
        if st.button("📝 Buat laporan", type="primary"):
            rd = intel.radar_faktor(A["ev"][A["ev"]["relasi"] == "Tidak langsung"] if not A["ev"].empty else A["ev"],
                                    e_row.get("Sektor") or "Lainnya")
            narasi = A["ringkasan"]
            if claude_key and A["ref"]:
                with st.spinner("Claude menulis laporan …"):
                    try:
                        narasi = MesinClaude(claude_key, model_claude).laporan(
                            e_row["Entitas"] or nama, periode, A["ref"],
                            f"skor {A['skor']}, risiko {A['risiko'][0]}, keyakinan {A['keyakinan'][1]}")
                    except Exception as ex:  # noqa: BLE001
                        st.warning(f"Claude gagal ({ex}); memakai ringkasan otomatis.")
            sken = laporan.skenario_aturan(A["ev"], rd)
            mk = pasar.metrik(harga, hari) if harga is not None and not harga.empty else None
            info = info_laporan()
            st.session_state["laporan"] = {
                "nama": nama, "pdf": laporan.buat_pdf(info, A["ev"], A["ref"], rd, narasi, sken, mk),
                "xlsx": laporan.buat_excel(info, A["ev"], A["x"], A["ref"], rd, db.baca_peringatan([nama]), narasi,
                                           sken)}
        lp = st.session_state.get("laporan")
        if lp and lp["nama"] == nama:
            l1, l2, _ = st.columns([1.4, 1.4, 4])
            l1.download_button("⬇️ PDF", lp["pdf"], type="primary", mime="application/pdf",
                               file_name=f"Laporan_{nama.replace(' ', '_')}_{datetime.now():%Y%m%d}.pdf")
            l2.download_button("⬇️ Excel", lp["xlsx"],
                               file_name=f"Laporan_{nama.replace(' ', '_')}_{datetime.now():%Y%m%d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("🏆 Peringkat emiten di daftar saya (rating tertinggi → terendah, dengan sentimen)"):
        tampil_pk = st.toggle("Tampilkan peringkat", key="tampil_pk",
                              help="Dihitung saat dibutuhkan saja agar halaman tetap cepat.")
        if not tampil_pk:
            st.caption(f"Peringkat {len(emiten)} emiten di daftar saya menurut rating, dengan Sentiment Score 0–100 "
                       "yang sama dengan Overview & watchlist.")
        else:
            e_pk = semua[semua["Nama"].isin(set(emiten.loc[emiten["Aktif"].astype(bool), "Nama"]))]
            bar_pk = st.progress(0.0, text="Menghitung skor peristiwa tiap emiten …")
            _n_pk = {"i": 0}

            def _hasil_pk(e_):
                _n_pk["i"] += 1
                bar_pk.progress(min(_n_pk["i"] / max(len(e_pk), 1), 1.0), text=f"{_n_pk['i']}/{len(e_pk)} · {e_['Nama']}")
                A_ = analisa(e_)
                return A_["ev"], A_["tren"]
            pk = analisis.urutkan(analisis.peringkat_emiten(e_pk, pd.DataFrame(), rating_df, hari, paruh,
                                                            hasil=_hasil_pk), "Rating (tertinggi → terendah)")
            bar_pk.empty()
            if pk.empty:
                st.caption("Belum ada emiten aktif.")
            else:
                st.caption("**Skor 0–100 berbasis peristiwa unik** — metodologi yang sama dengan Overview & watchlist "
                           "(50 = netral, < 40 negatif, > 60 positif; '—' bila peristiwa unik < 3). Δ = perubahan skor "
                           "dibanding 7 hari lalu.")
                st.dataframe(pk[["#", "Emiten", "Kode", "Rating", "Outlook", "Perubahan", "Skor", "Tren", "Kategori",
                                 "Keyakinan", "Risiko", "Peristiwa", "Positif", "Negatif", "Sinyal", "Berita terbaru"]],
                             hide_index=True, height=420,
                             column_config={"Skor": st.column_config.ProgressColumn("Skor 0–100", min_value=0,
                                                                                    max_value=100, format="%.0f"),
                                            "Tren": st.column_config.NumberColumn("Δ 7 hari", format="%+.0f"),
                                            "Positif": st.column_config.NumberColumn("Peristiwa +"),
                                            "Negatif": st.column_config.NumberColumn("Peristiwa −"),
                                            "Berita terbaru": st.column_config.TextColumn(width=380)})
                berita_all = db.baca_berita(hari=hari, emiten=list(e_pk["Nama"]))
                berita_all = berita_all[berita_all["relasi"].fillna("") != "Tidak langsung"]
                st.download_button("⬇️ Excel peringkat", data=ekspor.buat_excel(pk, berita_all, rating_df, {
                    "Dibuat": datetime.now().strftime("%d/%m/%Y %H:%M"), "Periode": periode}),
                    file_name=f"Peringkat_Emiten_{datetime.now():%Y%m%d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================================================================
# 💬 ASK AI
# ============================================================================
with tab_ai:
    if e_row is None:
        kosong()
    else:
        ref = A["ref"]
        st.markdown(f"#### 💬 Ask AI about {esc(e_row.get('Kode') or nama)}")
        st.caption(f"Jawaban **hanya** disusun dari {len(ref)} peristiwa yang dikumpulkan aplikasi ({periode}), dengan "
                   "nomor referensi [n] yang bisa diklik. " +
                   (f"Mesin: Claude ({model_claude})." if claude_key else
                    "Tanpa Claude API key: mode pencarian lokal (tanpa narasi AI)."))
        k_chat = f"chat::{nama}::{hari}"
        riwayat = st.session_state.setdefault(k_chat, [])
        saran = ["Apa risiko terbesar saat ini?", "Kenapa sentimennya seperti ini?", "Berita resmi apa yang terbaru?",
                 "Bagaimana faktor global memengaruhi emiten ini?"]
        pilih_saran = st.pills("Contoh pertanyaan", saran, key=f"saran_{nama}_{len(riwayat)}")
        tanya = st.chat_input(f"Tanya tentang {e_row.get('Kode') or nama} …", key=f"chat_in_{nama}")
        q = tanya or pilih_saran
        if q and ref:
            with st.spinner("Menyusun jawaban dari data terkumpul …"):
                if claude_key:
                    try:
                        jawab = MesinClaude(claude_key, model_claude).tanya(e_row["Entitas"] or nama, q, ref, periode)
                    except Exception as ex:  # noqa: BLE001
                        jawab = f"Claude API gagal ({ex}). Hasil pencarian lokal:\n\n" + intel.jawab_lokal(q, ref)
                else:
                    jawab = intel.jawab_lokal(q, ref)
            riwayat.append({"q": q, "a": jawab})
        elif q:
            riwayat.append({"q": q, "a": "Belum ada data berita yang terkumpul untuk emiten ini. Klik **🔄 Refresh**."})
        nomor = {r["no"]: r for r in ref}
        for item in riwayat[-8:]:
            with st.chat_message("user"):
                st.markdown(item["q"])
            with st.chat_message("assistant", avatar="📡"):
                st.markdown(item["a"])
                dipakai = sorted({int(n_) for n_ in re.findall(r"\[(\d{1,3})\]", item["a"]) if int(n_) in nomor})
                if dipakai:
                    st.markdown("**Referensi:**  \n" + "  \n".join(
                        f"[{n_}] [{nomor[n_]['judul']}]({nomor[n_]['url']}) — {nomor[n_]['sumber']}, "
                        f"{nomor[n_]['tanggal']} · {nomor[n_]['verifikasi']}" for n_ in dipakai))
        if riwayat and st.button("🧹 Hapus percakapan"):
            st.session_state[k_chat] = []
            st.rerun()

# ============================================================================
# ⚙️ PENGATURAN
# ============================================================================
with tab_set:
    s_src, s_em, s_grup, s_rt, s_key, s_ev, s_log = st.tabs(["🗞️ Sumber berita", "🏢 Daftar emiten",
                                                                   "🏢 Grup perusahaan", "🏷️ Rating",
                                                                   "🔑 Kunci API", "🧪 Evaluasi model", "📜 Log"])
    with s_src:
        st.multiselect("Kanal untuk satu emiten (Overview / Refresh)", KANAL_SEMUA, key="s_kanal_satu")
        st.multiselect("Kanal untuk Refresh watchlist / banyak emiten", KANAL_SEMUA, key="s_kanal_banyak",
                       help="Disarankan tanpa 'Situs pilihan' agar tidak dibatasi mesin pencari.")
        st.select_slider("Interval refresh otomatis", [5, 10, 15, 30, 60], key="s_interval",
                         format_func=lambda m: f"{m} menit")
        st.markdown("**Situs pilihan** — dicari lewat Google News dengan `site:` (judul + tautan asli). Bahasa `id` = "
                    "edisi Indonesia, `en` = edisi Inggris. Tambah situs di baris kosong paling bawah.")
        situs_ed = st.data_editor(situs_df, num_rows="dynamic", hide_index=True, key="ed_situs",
                                  column_config={"Situs": st.column_config.TextColumn(width=220),
                                                 "Bahasa": st.column_config.SelectboxColumn(options=["id", "en"])})
        if st.button("✅ Terapkan daftar situs"):
            st.session_state["situs_df"] = situs_ed.copy()
            st.toast("Daftar situs diterapkan untuk sesi ini.", icon="✅")
        st.markdown("**Feed RSS media nasional** — dibaca sekali per refresh, lalu disaring ke emiten yang disebut.")
        rss_ed = st.data_editor(rss_df, num_rows="dynamic", hide_index=True, key="ed_rss",
                                column_config={"URL": st.column_config.TextColumn(width=520)})
        c1, c2, _ = st.columns([1.3, 1.3, 4])
        if c1.button("✅ Terapkan daftar feed"):
            st.session_state["rss_df"] = rss_ed.copy()
            st.toast("Daftar feed diterapkan untuk sesi ini.", icon="✅")
        if c2.button("🧪 Tes semua feed", disabled=(mode == "Demo")):
            hasil = []
            for nm_, url_ in ([(r["Nama"], r["URL"]) for _, r in rss_ed.iterrows()] + K.FEED_STOCKBIT +
                              K.FEED_INVESTING):
                try:
                    hasil.append({"Feed": nm_, "Status": "OK", "Item": len(sumber.rss_media(nm_, url_))})
                except Exception as ex:  # noqa: BLE001
                    hasil.append({"Feed": nm_, "Status": "Gagal", "Pesan": str(ex)[:150]})
            st.dataframe(pd.DataFrame(hasil), hide_index=True)
        with st.expander("Sumber resmi & faktor global"):
            st.markdown(f"- **{K.K_RESMI}**: keterbukaan informasi IDX per kode saham (bila situs IDX mengizinkan "
                        "akses otomatis), plus pencarian `site:idx.co.id`, `site:ojk.go.id`, `site:bi.go.id`, dan "
                        "website IR emiten (kolom *Website IR*).\n"
                        f"- **{K.K_SEC}**: pengajuan SEC (20-F, 6-K) untuk emiten yang tercatat di AS (kolom *Kode AS*, "
                        "mis. TLK). Perlu email kontak di 🔑 Kunci API sesuai aturan SEC.\n"
                        f"- **{K.K_FAKTOR}**: berita faktor sektor (komoditas, suku bunga, kurs, kebijakan) — lihat "
                        "tab 🌐 Global Impact.")

    with s_em:
        if mode == "Demo":
            st.info("Di mode demo, daftar emiten bersifat contoh dan tidak bisa diubah.")
        else:
            t_milik, t_kat = st.tabs([f"⭐ Daftar saya ({len(emiten)})",
                                      f"📚 Katalog seluruh emiten BEI ({len(kat_df)})"])
            with t_milik:
                st.caption("Emiten prioritas yang punya **rating** dan alias/merek yang diatur sendiri. Kodenya "
                           "menggantikan baris katalog yang sama (mis. BBRI → BRI GROUP). **Alias** = nama yang harus "
                           "disebut berita. **Terkait** = anak usaha / merek / induk (relasi *Entitas terkait*). "
                           "**Kueri** = kata kunci pencarian. **Pengecualian** = nama mirip yang harus dibuang. "
                           "**Sektor** menentukan faktor global. **Website IR** untuk sumber resmi. **Kode AS** untuk "
                           "SEC EDGAR. Pisahkan isian dengan titik koma (;).")
                ed = st.data_editor(emiten, num_rows="dynamic", hide_index=True, key="ed_emiten", height=520,
                                    column_config={"Aktif": st.column_config.CheckboxColumn(width=55),
                                                   "Nama": st.column_config.TextColumn(width=220),
                                                   "Sektor": st.column_config.SelectboxColumn(
                                                       options=sorted(set(intel.SEKTOR_LIST) |
                                                                      set(emiten["Sektor"].dropna()))),
                                                   "Lembaga Utama": st.column_config.SelectboxColumn(
                                                       options=["PEFINDO", "Fitch"], width=95),
                                                   "Alias": st.column_config.TextColumn(width=240),
                                                   "Terkait": st.column_config.TextColumn(width=240),
                                                   "Kueri": st.column_config.TextColumn(width=240)})
                c1, c2, _ = st.columns([1.3, 1.6, 4])
                if c1.button("✅ Terapkan daftar emiten", type="primary"):
                    st.session_state["emiten_personal"] = em.rapikan(ed)
                    st.toast("Daftar emiten diperbarui untuk sesi ini.", icon="✅")
                    st.rerun()
                if c2.button("↩️ Kembalikan ke daftar bawaan"):
                    st.session_state["emiten_personal"] = em.default_emiten()
                    st.rerun()
            with t_kat:
                st.caption(f"Seluruh perusahaan tercatat di Bursa Efek Indonesia — sumber: {kat_ket}. Setiap emiten "
                           "otomatis punya alias, kata kunci, sektor faktor (Global Impact), website (sumber resmi), "
                           "pemegang saham utama, dan induk usaha sebagai entitas terkait. Semua bisa langsung dipilih "
                           "di kotak Emiten dan dimasukkan ke watchlist.")
                k1, k2, k3 = st.columns([2.2, 1.8, 1.8])
                q_kat = k1.text_input("Cari kode / nama", key="q_kat", placeholder="mis. bank, tambang, ADRO")
                sek_kat = k2.multiselect("Sektor BEI", sorted(x for x in kat_df["Sektor BEI"].unique() if x),
                                         key="sek_kat", placeholder="Semua sektor")
                pap_kat = k3.multiselect("Papan", sorted(x for x in kat_df["Papan"].unique() if x), key="pap_kat",
                                         placeholder="Semua papan")
                kv = kat_df.copy()
                if q_kat:
                    kv = kv[kv["Kode"].str.contains(q_kat, case=False, regex=False) |
                            kv["Nama"].str.contains(q_kat, case=False, regex=False) |
                            kv["Industri"].str.contains(q_kat, case=False, regex=False)]
                if sek_kat:
                    kv = kv[kv["Sektor BEI"].isin(sek_kat)]
                if pap_kat:
                    kv = kv[kv["Papan"].isin(pap_kat)]
                kv = kv.rename(columns={"Sektor": "Sektor faktor"})
                pil = st.dataframe(kv, hide_index=True, height=440, on_select="rerun", selection_mode="multi-row",
                                   key="tbl_kat", column_config={
                                       "Nama": st.column_config.TextColumn(width=280),
                                       "Pemegang saham utama": st.column_config.TextColumn(width=380),
                                       "BUMN/Danantara": st.column_config.CheckboxColumn("BUMN", width=60)})
                rows_k = pil.selection.rows if pil and pil.selection else []
                st.caption(f"{len(kv)} emiten ditampilkan. Centang baris untuk menambahkannya ke watchlist atau ke "
                           "daftar saya.")
                b1, b2, b3 = st.columns([1.6, 1.6, 3])
                if b1.button(f"⭐ Tambah {len(rows_k)} ke watchlist", disabled=not rows_k):
                    tambah = [k_ for k_ in kv.iloc[rows_k]["Kode"] if k_ in info_e or em.cari(semua, k_)]
                    tambah = [k_ if k_ in info_e else em.cari(semua, k_) for k_ in tambah]
                    semua_wl = st.session_state.setdefault("watchlists", {})
                    semua_wl[mode] = list(dict.fromkeys((semua_wl.get(mode) or []) + tambah))
                    st.session_state.pop("wl_mode", None)
                    st.toast(f"{len(tambah)} emiten ditambahkan ke watchlist.", icon="⭐")
                    st.rerun()
                if b2.button(f"➕ Tambah {len(rows_k)} ke daftar saya", disabled=not rows_k):
                    d0 = st.session_state["emiten_personal"]
                    baru_rows = [info_e[k_][em.KOLOM] for k_ in kv.iloc[rows_k]["Kode"]
                                 if k_ in info_e and info_e[k_].get("Asal") == "Katalog BEI"
                                 and k_ not in set(d0["Nama"])]
                    if baru_rows:
                        st.session_state["emiten_personal"] = em.rapikan(pd.concat([d0, pd.DataFrame(baru_rows)], ignore_index=True))
                    st.toast(f"{len(baru_rows)} emiten ditambahkan ke daftar saya.", icon="✅")
                    st.rerun()
                st.markdown("**Perbarui katalog** (emiten baru IPO, ganti nama, delisting)")
                u1, u2 = st.columns([1.3, 2.7], vertical_alignment="top")
                if u1.button("🔄 Perbarui dari situs IDX"):
                    try:
                        with st.spinner("Mengambil daftar emiten dari idx.co.id …"):
                            baru_kat, info_k = kt.perbarui(kat_df, kt.dari_idx())
                        st.session_state["katalog_sesi"] = (baru_kat, f"IDX (sesi): {info_k['waktu']}")
                        st.session_state["info_kat"] = info_k
                        st.rerun()
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"Situs IDX tidak bisa diakses otomatis ({str(ex)[:120]}). Unduh file **Daftar Saham** "
                                 "dari idx.co.id (Data Pasar → Data Saham → Daftar Saham → unduh Excel), lalu unggah "
                                 "di sebelah kanan.")
                f_kat = u2.file_uploader("…atau unggah file Daftar Saham dari idx.co.id (Excel/CSV)",
                                         type=["xlsx", "xls", "csv"], key="up_kat")
                if f_kat is not None and u2.button("📥 Terapkan file ke katalog", type="primary"):
                    try:
                        baru = kt.dari_file(f_kat)
                        baru_kat, info_k = kt.perbarui(kat_df, baru)
                        st.session_state["katalog_sesi"] = (baru_kat, f"Unggahan sesi: {f_kat.name}")
                        st.session_state["info_kat"] = info_k
                        st.rerun()
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"File tidak terbaca: {ex}")
                ik = st.session_state.pop("info_kat", None)
                if ik:
                    st.success(f"Katalog diperbarui: {ik['total']} emiten · {len(ik['tambah'])} baru"
                               + (f" ({', '.join(ik['tambah'][:15])}{'…' if len(ik['tambah']) > 15 else ''})"
                                  if ik["tambah"] else "") + f" · {len(ik['ubah_nama'])} ganti nama · "
                               f"{len(ik['hapus'])} tidak tercatat lagi"
                               + (f" ({', '.join(ik['hapus'][:15])})" if ik["hapus"] else "") + ".")
                if st.button("↩️ Kembalikan ke katalog bawaan"):
                    st.session_state["katalog_sesi"] = (kt._rapikan_kat(pd.read_csv(kt.KATALOG_BAWAAN, dtype=str)), "katalog bawaan")
                    st.rerun()

    with s_grup:
        st.markdown("**Pemetaan grup perusahaan** — referensi utama: Excel Limit Counterparty yang diberikan "
                    "(tab Perbankan, Non Perbankan, dan Group). Untuk emiten lain, gunakan grup dari "
                    "katalog kepemilikan bawaan jika tersedia.")
        st.caption("Nama grup hanya ditampilkan sebagai informasi identitas perusahaan, tidak otomatis "
                   "membuat seluruh perusahaan satu grup dianggap relevan dalam berita.")
        if pilih in INFO_GRUP:
            rec = INFO_GRUP[pilih]
            st.info(f"**{label_pendek(pilih)} → {rec['grup']}** · Sumber: {rec['sumber']}. "
                    + (f"Catatan: {rec['bukti']}" if rec['bukti'] else ""))
        if mode == "Live":
            g1, g2 = st.columns([2.0, 2.5], vertical_alignment="bottom")
            kode_g = g1.selectbox("Emiten untuk memperbaiki grup", daftar, key="grp_code",
                                  format_func=label_pendek)
            group_now = INFO_GRUP.get(kode_g, {}).get("grup", "")
            g2.text_input("Nama grup pengganti (hanya sesi ini)",
                          value=grup_manual.get(str(info_e[kode_g].get('Kode') or '').upper(), ''), key=f"grp_edit::{kode_g}",
                          placeholder=f"Contoh: {group_now}")
            t1, t2 = st.columns([1, 1])
            if t1.button("✅ Terapkan grup", key="apply_group"):
                k = str(info_e[kode_g].get('Kode') or '').upper()
                v = st.session_state.get(f"grp_edit::{kode_g}", "").strip()
                if k and v:
                    st.session_state["grup_manual"][k] = v
                    st.rerun()
                else:
                    st.warning("Isi kode emiten dan nama grup terlebih dahulu.")
            if t2.button("↩️ Pulihkan grup asli", key="reset_group"):
                st.session_state["grup_manual"].pop(str(info_e[kode_g].get('Kode') or '').upper(), None)
                st.rerun()
        st.markdown("**Daftar grup sesuai Excel unggahan**")
        st.dataframe(grup_mod.tabel_excel(), hide_index=True, height=360, width="stretch")
        st.caption("Jika sumber katalog tidak mempunyai data grup, aplikasi menampilkan 'Belum teridentifikasi'. "
                   "Pemetaan grup merupakan referensi dan tidak menjamin struktur kepemilikan terbaru.")

    with s_rt:
        if mode == "Demo":
            st.info("Di mode demo, rating bersifat contoh dan tidak bisa diubah.")
        else:
            st.markdown("**1 · Impor dari aplikasi / file Limit Counterparty**")
            up = st.file_uploader("`data/master_data.xlsx` dari aplikasi Limit Counterparty, atau file Excel "
                                  "`Limit_Countreparty_DDMMYYYY.xlsx`", type=["xlsx"], accept_multiple_files=True)
            if up and st.button("📥 Impor rating", type="primary"):
                total, baru_em = 0, []
                for f in up:
                    try:
                        try:
                            r_new, nama_l, _info = rt_mod.impor_master_limit(f.getvalue())
                        except ValueError:
                            r_new, nama_l = rt_mod.impor_excel_limit(f.getvalue(), f.name)
                        db.tambah_rating(r_new)
                        total += len(r_new)
                        ed2, tambah = em.tambah_dari_limit(st.session_state["emiten_personal"], nama_l)
                        if tambah:
                            st.session_state["emiten_personal"] = ed2
                            baru_em += tambah
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"{f.name}: {ex}")
                st.success(f"{total} baris rating diimpor." + (f" Emiten baru: {', '.join(baru_em)}" if baru_em else ""))
                st.rerun()
            st.markdown("**2 · Sinkron dari PEFINDO** (rating terkini + press release, juga masuk sebagai berita resmi)")
            n_kode = int((emiten["Aktif"] & (emiten["Kode"].str.len() > 0)).sum())
            if st.button(f"🔄 Sinkronkan {n_kode} emiten dari pefindo.com"):
                with st.status("Mengambil data PEFINDO …", expanded=True) as s:
                    bar = st.progress(0.0)
                    r_new, rilis, lap = rt_mod.sinkron_pefindo(
                        emiten, progress=lambda i, n, t: bar.progress(i / n, text=f"{i}/{n} · {t}"))
                    if not r_new.empty:
                        db.tambah_rating(r_new, ganti_sumber_berisi="pefindo.com",
                                         untuk_nama=list(r_new["Nama"].unique()))
                    if rilis:
                        db.simpan_berita(analisis.berita_pefindo(rilis).assign(relasi="Langsung"), timpa=True)
                    ok = int((lap["Status"] == "OK").sum()) if not lap.empty else 0
                    s.update(label=f"PEFINDO: {ok} berhasil dari {len(lap)} emiten",
                             state="complete" if ok else "error", expanded=False)
                if not ok:
                    st.error("Tidak ada data yang terambil. Pastikan pefindo.com bisa dibuka dari komputer ini.")
                st.dataframe(lap, hide_index=True, column_config={"Catatan": st.column_config.TextColumn(width=420)})
            st.markdown("**3 · Periksa Fitch Ratings untuk emiten terpilih**")
            st.caption("Sumber resmi: https://www.fitchratings.com/latest-rating-actions/ dan "
                       "https://www.fitchratings.com/region/indonesia. Pencarian publik dapat tidak lengkap atau "
                       "dibatasi situs; hanya URL asli Fitch dan judul yang menyebut perusahaan yang diterima.")
            if st.button("🔎 Cari rilis Fitch emiten ini", disabled=(e_row is None), key="fitch_periksa"):
                target = str(e_row.get("Entitas") or "").strip()
                with st.spinner(f"Mencari rilis Fitch resmi: {target} …"):
                    fr = rating_fitch.cari(target, 365)
                st.session_state["fitch_hasil_terakhir"] = fr
                rows_f = rating_fitch.ke_rating(fr["rilis"], nama)
                if not rows_f.empty:
                    db.tambah_rating(rows_f)
                    st.success(f"{len(rows_f)} rating Fitch terbaca dari rilis resmi; data hanya di memori sesi.")
                else:
                    st.info(fr['status'])
            if st.session_state.get("fitch_hasil_terakhir"):
                info_f = st.session_state['fitch_hasil_terakhir']
                st.caption(info_f['status'])
                if info_f['rilis']:
                    st.dataframe(pd.DataFrame(info_f['rilis']), hide_index=True, width="stretch",
                                 column_config={"url": st.column_config.LinkColumn("Sumber Fitch")})
                st.link_button("Buka pencarian Fitch resmi", rating_fitch.FITCH_CARI)
            st.markdown("**4 · Edit / input manual** (Fitch, rating lama, koreksi)")
            rt_tampil = rating_df.copy()
            for c_ in ("Outlook", "Aksi", "Keterangan", "Sumber"):
                rt_tampil[c_] = rt_tampil[c_].astype(object).where(rt_tampil[c_].notna(), "")
            rt_ed = st.data_editor(rt_tampil, num_rows="dynamic", hide_index=True, key="ed_rating", height=420,
                                   column_config={
                                       "Nama": st.column_config.SelectboxColumn(options=emiten["Nama"].tolist(),
                                                                                width=230),
                                       "Lembaga": st.column_config.SelectboxColumn(
                                           options=["PEFINDO", "Fitch", "Moody's", "S&P", "Lainnya"]),
                                       "Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                       "Keterangan": st.column_config.TextColumn(width=300)})
            if st.button("✅ Terapkan tabel rating"):
                db.simpan_rating(rt_ed)
                st.toast("Rating diterapkan pada sesi ini.", icon="✅")
                st.rerun()

    with s_key:
        st.caption("Semua kunci opsional. Tanpa kunci, aplikasi tetap memakai sumber gratis (Google News, Bing, Yahoo "
                   "Finance, Stockbit Snips, Investing.com, GDELT, RSS media, IDX).")
        a1, a2, a3 = st.columns(3)
        a1.text_input("NewsAPI.org key", key="s_newsapi", type="password",
                      help="Paket Developer gratis: 100 permintaan/hari, artikel tertunda 24 jam (untuk pengembangan).")
        a2.text_input("GNews.io key", key="s_gnews", type="password")
        a3.text_input("NewsData.io key", key="s_newsdata", type="password")
        b1, b2, b3 = st.columns([2, 1.2, 1.6])
        b1.text_input("Claude API key (ANTHROPIC_API_KEY)", key="s_claude_key", type="password",
                      help="Untuk mesin sentimen & dampak Claude, ringkasan AI, Ask AI, dan laporan AI.")
        b2.selectbox("Model Claude", list(MODEL_CLAUDE), key="s_model")
        b3.text_input("Email kontak untuk SEC EDGAR", key="s_sec_email",
                      help="SEC mewajibkan User-Agent berisi email kontak untuk akses otomatis.")
        st.caption("🔒 Kunci API hanya digunakan selama sesi browser dan **tidak ditulis ke file/database**. "
                   "Jangan unggah atau membagikan kunci API.")

    with s_ev:
        st.markdown("#### 🧪 Evaluasi mesin sentimen & dampak terhadap label manusia")
        st.caption("Seberapa akurat kamus / IndoBERT+FinBERT / Claude pada berita emiten Indonesia? Labeli sampel berita "
                   "secara **buta** (prediksi mesin tidak diperlihatkan), lalu bandingkan: confusion matrix, precision, "
                   "recall, F1 per kelas, accuracy, dan **macro-F1** dengan selang kepercayaan 95%. Sentimen teks dan "
                   "dampak ke emiten dievaluasi terpisah. Label AI tidak pernah dipakai sebagai kebenaran.")
        lab_all = db.baca_label()
        lab_fin = evm.label_final(lab_all)
        e1_, e2_, e3_, e4_ = st.columns([1.3, 1, 1.2, 1.5], vertical_alignment="bottom")
        cak_ev = e1_.segmented_control("Sampel dari", ["Semua emiten", "Emiten terpilih"], default="Semua emiten",
                                       key="ev_cak", required=True)
        n_ev = e2_.select_slider("Jumlah", [20, 50, 100, 200], value=50, key="ev_n")
        pelabel = e3_.text_input("Nama pelabel", key="ev_pelabel", placeholder="mis. Rina",
                                 help="Bila beberapa orang melabeli berita yang sama, aplikasi menghitung kesepakatan "
                                      "antar-pelabel (Cohen's kappa) dan memakai suara terbanyak.")
        if e4_.button("🎲 Ambil sampel berlapis untuk dilabeli", width="stretch"):
            b_ev = db.baca_berita(hari=3650, emiten=[nama] if cak_ev == "Emiten terpilih" and nama else None)
            sudah_ev = set(zip(lab_all.loc[lab_all["pelabel"] == (pelabel or "anonim"), "id"],
                               lab_all.loc[lab_all["pelabel"] == (pelabel or "anonim"), "emiten"]))
            st.session_state["ev_sampel"] = evm.sampel(b_ev, int(n_ev), sudah_ev,
                                                       seed=int(pd.Timestamp.now().timestamp()) % 10_000)
        smp = st.session_state.get("ev_sampel")
        if smp is not None and not smp.empty:
            st.markdown(f"**Labeli {len(smp)} berita** — baca judul/ringkasan, buka tautan bila perlu. *Sentimen teks* "
                        "= nada beritanya; *Dampak ke emiten* = akibat finansial bagi emiten yang tertera (bisa beda: "
                        "'harga minyak naik' bernada positif tetapi merugikan maskapai).")
            ed_in = smp[["emiten", "judul"]].assign(sentimen=None, dampak=None, url=smp["url"],
                                                    ringkasan=smp["ringkasan"].fillna("").str.slice(0, 220),
                                                    catatan="")
            ed = st.data_editor(ed_in, hide_index=True, key="ev_editor", num_rows="fixed", column_config={
                "emiten": st.column_config.TextColumn("Emiten", disabled=True, width=100),
                "judul": st.column_config.TextColumn("Judul", disabled=True, width=340),
                "ringkasan": st.column_config.TextColumn("Ringkasan", disabled=True, width=240),
                "url": st.column_config.LinkColumn("Buka", display_text="↗", disabled=True, width=50),
                "sentimen": st.column_config.SelectboxColumn("Sentimen teks", options=evm.KELAS_SENTIMEN,
                                                             width=110),
                "dampak": st.column_config.SelectboxColumn("Dampak ke emiten", options=evm.KELAS_DAMPAK +
                                                           [evm.TIDAK_RELEVAN], width=130),
                "catatan": st.column_config.TextColumn("Catatan", width=150)})
            isi_ev = ed[ed["sentimen"].notna() | ed["dampak"].notna()]
            if st.button(f"💾 Simpan {len(isi_ev)} label", type="primary", disabled=isi_ev.empty):
                simpan_ev = smp.loc[isi_ev.index, ["id", "emiten", "judul"]].assign(
                    sentimen=isi_ev["sentimen"].values, dampak=isi_ev["dampak"].values,
                    catatan=isi_ev["catatan"].values, pelabel=pelabel or "anonim",
                    waktu=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
                db.simpan_label(simpan_ev)
                st.session_state.pop("ev_sampel", None)
                st.toast(f"{len(simpan_ev)} label tersimpan.", icon="💾")
                st.rerun()
        with st.expander(f"📁 Label tersimpan: {len(lab_all)} label · {len(lab_fin)} berita · "
                         f"{lab_all['pelabel'].nunique() if not lab_all.empty else 0} pelabel (impor/ekspor CSV)"):
            if not lab_all.empty:
                st.download_button("⬇️ Ekspor label (CSV)", lab_all.to_csv(index=False).encode("utf-8"),
                                   file_name=f"label_manual_{datetime.now():%Y%m%d}.csv", mime="text/csv")
            up_lab = st.file_uploader("Impor label (CSV: id, emiten, judul, sentimen, dampak, catatan, pelabel, waktu)",
                                      type=["csv"], key="up_label")
            if up_lab is not None and st.button("📥 Impor"):
                try:
                    d_lab = pd.read_csv(up_lab, dtype=str).fillna("")
                    d_lab = d_lab[d_lab["sentimen"].isin(evm.KELAS_SENTIMEN + [""]) &
                                  d_lab["dampak"].isin(evm.KELAS_DAMPAK + [evm.TIDAK_RELEVAN, ""])]
                    for c_ in ("judul", "catatan", "pelabel", "waktu"):
                        if c_ not in d_lab.columns:
                            d_lab[c_] = ""
                    st.toast(f"{db.simpan_label(d_lab.replace('', None))} label diimpor.", icon="📥")
                except Exception as ex:  # noqa: BLE001
                    st.error(f"CSV tidak terbaca: {ex}")
            kp = evm.kesepakatan(lab_all) if not lab_all.empty else pd.DataFrame()
            if not kp.empty:
                st.markdown("**Kesepakatan antar-pelabel (Cohen's kappa)** — < 0,4 lemah · 0,4–0,6 sedang · > 0,6 "
                            "baik. Bila kappa rendah, definisi label perlu disepakati dulu sebelum menilai mesin.")
                st.dataframe(kp, hide_index=True, column_config={
                    "Kappa sentimen": st.column_config.NumberColumn(format="%.2f"),
                    "Kappa dampak": st.column_config.NumberColumn(format="%.2f")})
        if lab_fin.empty:
            st.info("Belum ada label manusia. Ambil sampel di atas dan labeli minimal ±100 berita (≥ 20 per kelas) "
                    "agar hasil evaluasi bermakna.", icon="🧪")
        else:
            art_ev = db.baca_berita(hari=None)
            art_ev = art_ev.merge(lab_fin[["id", "emiten"]], on=["id", "emiten"], how="inner")
            pilihan_m = ["Tersimpan", "Kamus keuangan"]
            m_tambah = st.pills("Bandingkan juga", ["IndoBERT + FinBERT", "Claude API"], selection_mode="multi",
                                key="ev_mesin", help="IndoBERT+FinBERT perlu requirements-ai.txt; Claude perlu API key "
                                                     "(biaya per berita). Hasilnya disimpan selama sesi ini.")
            hasil_ev = {}
            cache_ev = st.session_state.setdefault("ev_cache", {})
            for m_ in pilihan_m + list(m_tambah or []):
                k_c = (m_, len(art_ev), hash(tuple(sorted(lab_fin["id"] + "|" + lab_fin["emiten"]))))
                if k_c not in cache_ev:
                    if m_ == "Claude API" and not claude_key:
                        st.caption("Claude API dilewati: isi API key di Kunci API.")
                        continue
                    try:
                        with st.spinner(f"Menjalankan {m_} pada {len(art_ev)} berita berlabel …"):
                            cache_ev[k_c] = evm.prediksi(art_ev, semua, m_ if m_ != "Claude API" else "Claude",
                                                         claude_key, model_claude)
                    except ImportError:
                        st.caption(f"{m_} belum terpasang (`pip install -r requirements-ai.txt`).")
                        continue
                    except Exception as ex:  # noqa: BLE001
                        st.caption(f"{m_} gagal: {ex}")
                        continue
                hasil_ev[m_ if m_ != "Tersimpan" else "Tersimpan (hasil di database)"] = evm.evaluasi(
                    lab_fin, cache_ev[k_c])
            if hasil_ev:
                tb_ev = evm.ringkas(hasil_ev)
                st.markdown("##### Perbandingan mesin")
                st.dataframe(tb_ev, hide_index=True, column_config={
                    **{c_: st.column_config.NumberColumn(format="%.2f") for c_ in tb_ev.columns
                       if c_ not in ("Mesin", "Tugas", "n", "Catatan")},
                    "Catatan": st.column_config.TextColumn(width=260)})
                st.caption("Macro-F1 = rata-rata F1 ketiga kelas (tidak 'tertolong' kelas mayoritas seperti Netral). "
                           "Selang kepercayaan lebar = sampel masih kecil; dua mesin yang selangnya tumpang tindih belum "
                           "terbukti berbeda.")
                r_ev = next(iter(hasil_ev.values()))["relevansi"]
                st.caption(f"Relevansi: {r_ev['tidak_relevan']} dari {r_ev['n']} berita berlabel dinilai manusia "
                           f"**tidak relevan** dengan emitennya (presisi relevansi ≈ {r_ev['presisi_relevansi']:.0%}).")
                c_m, c_t = st.columns([1.2, 1])
                m_lihat = c_m.selectbox("Confusion matrix untuk", list(hasil_ev), key="ev_lihat")
                t_lihat = c_t.segmented_control("Tugas", ["Sentimen teks", "Dampak ke emiten"],
                                                default="Sentimen teks", key="ev_tugas", required=True)
                h_ = hasil_ev[m_lihat]["sentimen" if t_lihat == "Sentimen teks" else "dampak"]
                k1_, k2_ = st.columns([1.1, 1])
                with k1_:
                    chart(grafik.matriks_konfusi(h_["cm"]), "Confusion matrix label manusia vs prediksi mesin.")
                with k2_:
                    st.dataframe(h_["per_kelas"], hide_index=True, column_config={
                        c_: st.column_config.NumberColumn(format="%.2f") for c_ in ("Precision", "Recall", "F1")})
                    st.caption(f"n = {h_['n']} · accuracy {h_['akurasi']:.2f} · macro-F1 {h_['macro_f1']:.2f} "
                               f"(95% CI {h_['ci'][0]:.2f}–{h_['ci'][1]:.2f})".replace("nan", "—"))

    with s_log:
        log_g = db.baca_log(5000)
        kn_g = monitor.kesehatan_kanal(log_g, hari=14)
        st.markdown("**🩺 Kesehatan kanal (14 hari terakhir, semua emiten)**")
        if kn_g.empty:
            st.caption("Belum ada pengambilan berita yang tercatat.")
        else:
            gg = kn_g[kn_g["Status"].str.startswith("🔴")]
            if not gg.empty:
                st.warning(f"{len(gg)} kanal gagal berkepanjangan: " + ", ".join(gg["Kanal"]) + ". Berita dari kanal "
                           "ini tidak masuk — cek koneksi/jaringan kantor, atau nonaktifkan kanalnya di Sumber berita.")
            st.dataframe(kn_g, hide_index=True, column_config={
                "Terakhir berhasil": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
                "Berhasil %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%"),
                "Galat terakhir": st.column_config.TextColumn(width=320)})
        st.markdown("**Log permintaan**")
        st.dataframe(log_g.head(1000), hide_index=True, height=420)

# ============================================================================
# ❓ PANDUAN
# ============================================================================
with tab_help:
    st.markdown(f"""
### Alur pakai
1. Ketik **kode saham, nama perusahaan, atau merek** di kotak *Emiten* (mis. BBRI, AADI, *aneka tambang*,
   Telkomsel → Telkom). Pilihan mencakup **seluruh emiten BEI (± 955)** dari katalog, plus emiten di
   *daftar saya* yang punya rating. Perusahaan di luar bursa bisa diketik langsung lalu dilengkapi kode & sektornya.
2. Tulis **periode** secara manual: angka + satuan (*hari, minggu, bulan, tahun terakhir*). Periode panjang diambil per
   jendela waktu dari Google News; berita yang telah diambil **dalam sesi ini** dapat digunakan kembali.
3. Klik **🔄 Refresh** untuk mengambil ulang informasi dari link; aktifkan **Otomatis** untuk pemantauan
   near-real-time tiap
   {st.session_state['s_interval']} menit.

### Halaman
| Halaman | Isi |
|---|---|
| 📊 Overview | Skor 0–100, 20 berita terbaru relevan per halaman (dengan total dan navigasi), Risk Level, Data Freshness, tren sentimen vs harga, peristiwa terbaru dengan penjelasan AI & status verifikasi |
| 📰 News Intelligence | Semua berita (20 per halaman) & peristiwa, filter sumber, topik, tanggal, sentimen, relasi, verifikasi; sebaran & unduhan |
| 🌐 Global Impact | Faktor eksternal per sektor (komoditas, suku bunga, kurs, kebijakan) dan dampaknya ke emiten |
| 📈 Market Analytics | Harga, return, volume, volatilitas, korelasi historis & reaksi harga setelah peristiwa (langsung & faktor eksternal; hanya yang berpengaruh ditonjolkan) |
| ⭐ Watchlist & Reports | Perbandingan multi-emiten, early warning semua emiten + berita pemicunya, laporan PDF/Excel, peringkat (skor 0–100) |
| 💬 Ask AI | Tanya jawab yang hanya memakai data terkumpul, dengan referensi [n] yang bisa diklik |

### Cara AI menilai berita
1. **Entity matching** — *Langsung* (menyebut emiten), *Entitas terkait* (anak usaha/merek, kolom *Terkait*),
   dan *Tidak langsung* (faktor global/domestik). Hasil kueri yang tidak menyebut emiten bukan bukti relevansi.
2. **Klasifikasi** — kinerja keuangan, aksi korporasi, regulasi, litigasi, utang, rating, pasar, faktor makro.
3. **Sentimen teks** — kamus keuangan, IndoBERT/FinBERT, atau Claude.
4. **Dampak ke emiten** — dipisah dari sentimen teks: aspek bisnis (pendapatan, laba, biaya, likuiditas, reputasi,
   regulasi), materialitas, dan arah dampak lewat peta sensitivitas sektor.
5. **Verifikasi** — 🛡️ resmi (IDX, OJK, BI, *.go.id, lembaga rating, website emiten) · ✅ media kredibel ·
   💬 opini/analisis · ❔ belum terverifikasi · ⚠️ rumor.
   **Independensi sumber:** media yang hanya mengutip satu siaran pers (📣 "siaran pers", "keterangan tertulis",
   "said in a statement") dihitung **satu** sumber asal; salinan (📋 "dilansir", "mengutip", konten ANTARA dimuat
   ulang, judul/ringkasan hampir identik) tidak menambah konfirmasi. Hanya 📰 liputan sendiri yang dihitung sumber
   independen. **Konflik** ditandai ⚠️ bila arah dampak antarsumber berlawanan, ada bantahan/klarifikasi, atau angka
   utama (laba, pendapatan, kredit, dividen) berbeda; kualitas bukti peristiwa itu diturunkan.
6. **Penggabungan peristiwa** — artikel berjudul mirip dalam ±3 hari digabung, jadi satu peristiwa tidak dihitung
   berulang kali.

### Skor sentimen (0–100)
Untuk setiap peristiwa unik *i*: **sᵢ** = dampak ke emiten (−1…+1); **wᵢ = Rᵢ × Mᵢ × Qᵢ × Dᵢ** (relevansi ×
materialitas × kualitas bukti × kebaruan, paruh waktu {paruh:.0f} hari). **S = 50 + 50 · Σwᵢsᵢ / Σwᵢ**.
0–20 sangat negatif · 20–40 negatif · 40–60 netral · 60–80 positif · 80–100 sangat positif. Bila peristiwa unik
kurang dari 3, tampil **Data tidak mencukupi** (bukan 50 yang menyesatkan). **Keyakinan**, **Cakupan**, dan
**Kesegaran** ditampilkan terpisah. Skor menghitung peristiwa *langsung*; faktor global dinilai di 🌐 Global Impact.
Skor yang **sama** dipakai di Overview, watchlist, peringkat emiten, penjelasan rating, dan ekspor Excel.

### Early warning
Peringatan dibuat dari peristiwa yang menyebut emiten / entitas terkaitnya: peristiwa kredit, berita material negatif,
hukum/regulasi, rumor material, sentimen turun ≥ 15 poin dalam 7 hari, dan lonjakan berita negatif. **Setiap
peringatan bisa dibuka untuk melihat semua berita pemicunya** (judul, sumber, waktu, dampak, verifikasi, sumber lain)
— mis. "5 peristiwa negatif dalam 3 hari terakhir" menampilkan kelima peristiwa itu. Tab ⭐ menampilkan peringatan
**semua emiten** (bisa disaring watchlist/emiten terpilih, tingkat, periode, kata kunci); peringatan hanya disimpan sementara dalam dashboard dan tidak dikirim ke email/Telegram.

### Cakupan & kesegaran data
Panel 🩺 di Overview memeriksa kanal yang gagal, kewajaran jumlah berita selama sesi, dan kelengkapan
halaman keterbukaan informasi IDX. Aplikasi tidak melakukan audit atas angka laporan keuangan resmi.

### Katalog seluruh emiten BEI
Setiap emiten katalog otomatis punya alias & kata kunci (nama + kode saham), sektor faktor untuk Global Impact,
website untuk sumber resmi, pemegang saham utama, dan induk/pengendali yang **tidak tercatat di bursa** (pemegang
korporasi ≥ 20%) sebagai entitas terkait — jadi semua halaman bekerja sama seperti emiten di daftar saya. Kode yang juga kata umum (mis. EMAS, BUMI,
GOOD) hanya dicocokkan dalam bentuk $EMAS, (EMAS), EMAS.JK, atau "saham EMAS". Katalog bisa diperbarui di
⚙️ Pengaturan → Daftar emiten → Katalog (dari situs IDX atau unggah file *Daftar Saham* idx.co.id).

### Kenapa berita dikaitkan
Setiap berita/peristiwa punya keterangan **🔗 Kenapa dikaitkan** — mis. "Judul menyebut “Antam”", "Dokumen resmi
emiten", "Menyebut anak usaha/merek", atau untuk faktor eksternal "Faktor harga minyak → biaya bahan bakar (sektor
penerbangan)". Berita yang hanya muncul di hasil pencarian tanpa bukti penyebutan emiten **tidak masuk analisis utama**.
Misalnya, kerugian SoftBank bukan bukti dampak ke BMRI.

### Reaksi harga (Market Analytics)
Bawaan: peristiwa **langsung** (menyebut emiten / dokumen resminya), **entitas terkait**, dan **tidak langsung** —
faktor eksternal sektor seperti harga minyak, batu bara, CPO, kurs, BI Rate (hanya yang arah dampaknya ke sektor emiten
jelas; berita faktor yang sama di hari yang sama digabung). Reaksi = return saham dikurangi IHSG pada hari bursa pertama
setelah berita (berita setelah 16.00 WIB dihitung ke hari berikutnya), dibandingkan gerak normal harian 60 hari.
**Hanya peristiwa yang berpengaruh** (harga bergerak searah dampak berita dan ≥ 1× gerak normal) yang ditampilkan di
grafik & penjelasan; sisanya (netral, lemah, berlawanan, tidak berarti) masuk tabel *Hanya informasi*. Angka **peluang
kebetulan** menunjukkan seberapa sering saham itu bergerak sebesar itu tanpa berita — bila porsi peristiwa
"berpengaruh" tidak jauh di atasnya, hubungan berita–harga lemah. Ini hubungan historis, bukan bukti sebab-akibat.

### Evaluasi model (⚙️ Pengaturan → 🧪)
Labeli sampel berita berlapis secara buta (sentimen teks & dampak ke emiten terpisah), lalu bandingkan mesin kamus,
IndoBERT+FinBERT, dan Claude: confusion matrix, precision, recall, F1 per kelas, accuracy, macro-F1 dengan selang
kepercayaan 95%, dan kesepakatan antar-pelabel (Cohen's kappa). Hasil di bawah 100 label masih indikatif.

### Penyimpanan sesi
Data diambil dari link berita/website dan hanya ditahan di memori selama sesi aplikasi aktif. Tidak ada SQLite,
SQL, atau penyimpanan file otomatis. Watchlist, label evaluasi, pengaturan, serta data berita akan hilang ketika sesi
berakhir. Anda bisa mengunduh PDF/Excel/CSV sebelum keluar. Auto-refresh hanya berjalan saat aplikasi terbuka.

### Batasan
- Label biru = berita diperkirakan menguntungkan emiten; merah = berita diperkirakan merugikan emiten.
  Ini **bukan** angka laba/rugi aktual maupun rekomendasi trading.
- Aplikasi memakai RSS/pencarian publik dan API yang diizinkan, menahan sementara metadata (judul, ringkasan, tautan), lalu
  mengarahkan ke artikel asli. Berita berbayar (paywall) hanya terbaca judul/ringkasannya.
- Situs yang menolak akses otomatis (mis. IDX, sebagian Investing.com) dicatat gagal di Log dan dilewati; aplikasi
  tidak memakai cara untuk menembus perlindungan situs. Beritanya biasanya tetap masuk lewat pencarian `site:`.
- Periode panjang (bulan/tahun) lebih tidak lengkap daripada periode pendek; GDELT maks. 90 hari.
- NewsAPI gratis: 100 permintaan/hari dan tertunda 24 jam — hanya pelengkap.
- Sentimen & dampak otomatis bisa keliru — ukur akurasinya di 🧪 Evaluasi model. Hubungan dengan harga bersifat
  historis, bukan sebab-akibat. Bukan rekomendasi beli/jual.
- Deteksi siaran pers/salinan & konflik hanya membaca judul + ringkasan (isi artikel tidak diambil).
""")

# ----------------------------------------------------------------------------
# Refresh otomatis (near-real-time; selama sesi terbuka)
# ----------------------------------------------------------------------------
if e_row is not None and mode == "Live":
    @st.fragment(run_every=60)
    def _cek_otomatis():
        if not st.session_state.get("auto_refresh"):
            return
        t = pd.to_datetime(db.get_meta(f"refresh::{nama}"), utc=True, errors="coerce")
        if pd.isna(t) or pd.Timestamp.now(tz="UTC") - t >= pd.Timedelta(minutes=st.session_state["s_interval"]):
            st.session_state["minta_refresh"] = nama
            st.rerun()

    _cek_otomatis()

