"""
Evaluasi statistik mesin sentimen & dampak terhadap LABEL MANUSIA.

- Sampel berlapis (stratified) dari berita tersimpan: dibagi rata menurut label prediksi & bahasa, agar kelas jarang
  (negatif, berita Inggris) ikut teruji. Pelabel TIDAK diperlihatkan prediksi mesin (pelabelan buta).
- Dua tugas dievaluasi terpisah:
    1. Sentimen teks   — nada berita itu sendiri (Positif / Netral / Negatif)
    2. Dampak ke emiten — akibat finansialnya bagi emiten (Menguntungkan / Netral / Merugikan); "Tidak relevan" =
       berita tidak benar-benar tentang emiten → dihitung sebagai metrik relevansi, bukan dampak.
- Metrik: confusion matrix, precision, recall, F1 per kelas, accuracy, macro-F1 (rata-rata F1 semua kelas, tidak
  dikuasai kelas mayoritas) + selang kepercayaan 95% bootstrap, dan Cohen's kappa antar-pelabel bila ada ≥ 2 pelabel.
- Label dari AI (Claude) TIDAK pernah dipakai sebagai kebenaran; hanya label yang diisi manusia.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KELAS_SENTIMEN = ["Positif", "Netral", "Negatif"]
KELAS_DAMPAK = ["Menguntungkan", "Netral", "Merugikan"]
TIDAK_RELEVAN = "Tidak relevan"
MIN_N = 100          # di bawah ini hasil evaluasi masih indikatif
MIN_PER_KELAS = 20


def dampak_kelas(v) -> str | None:
    """Skor dampak (−1…+1) atau label dampak aplikasi → 3 kelas evaluasi."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, str):
        return {"Menguntungkan": "Menguntungkan", "Merugikan": "Merugikan", "Netral / kecil": "Netral",
                "Campuran / belum pasti": "Netral", "Belum dapat disimpulkan": "Netral", "Netral": "Netral",
                TIDAK_RELEVAN: TIDAK_RELEVAN}.get(v)
    return "Menguntungkan" if v >= 0.15 else ("Merugikan" if v <= -0.15 else "Netral")


def sampel(berita: pd.DataFrame, n: int = 50, sudah: set | None = None, seed: int = 11) -> pd.DataFrame:
    """Sampel berlapis untuk dilabeli: lapisan = (label prediksi × bahasa), jatah dibagi rata antar-lapisan."""
    if berita is None or berita.empty:
        return pd.DataFrame()
    b = berita.drop_duplicates(["id", "emiten"])
    if sudah:
        b = b[[(i, e) not in sudah for i, e in zip(b["id"], b["emiten"])]]
    if b.empty:
        return b
    lap = b["label"].fillna("Netral").astype(str) + "|" + b["bahasa"].fillna("id").astype(str)
    grup = {k: g for k, g in b.groupby(lap)}
    rng = np.random.default_rng(seed)
    pilih, sisa = [], n
    kunci = sorted(grup, key=lambda k: len(grup[k]))
    for j, k in enumerate(kunci):                                  # lapisan kecil diambil semua bila perlu
        jatah = max(1, sisa // (len(kunci) - j))
        g = grup[k]
        ambil = g.iloc[rng.permutation(len(g))[:jatah]]
        pilih.append(ambil)
        sisa -= len(ambil)
        if sisa <= 0:
            break
    out = pd.concat(pilih)
    return out.iloc[rng.permutation(len(out))].reset_index(drop=True)


def metrik(y_benar: list, y_prediksi: list, kelas: list[str]) -> dict:
    """Confusion matrix + precision/recall/F1 per kelas, accuracy, macro-F1."""
    yt, yp = np.array(y_benar, dtype=object), np.array(y_prediksi, dtype=object)
    ok = np.array([a in kelas for a in yt])
    yt, yp = yt[ok], yp[ok]
    yp = np.array([p if p in kelas else "(tidak ada)" for p in yp], dtype=object)
    kol = kelas + (["(tidak ada)"] if (yp == "(tidak ada)").any() else [])
    cm = pd.DataFrame(0, index=pd.Index(kelas, name="Label manusia"), columns=pd.Index(kol, name="Prediksi"))
    for a, b in zip(yt, yp):
        cm.loc[a, b] += 1
    rows = []
    for k in kelas:
        tp = int(cm.loc[k, k])
        fp = int(cm[k].sum() - tp)
        fn = int(cm.loc[k].sum() - tp)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        rows.append({"Kelas": k, "Precision": p, "Recall": r, "F1": f1, "Support": int(cm.loc[k].sum())})
    per = pd.DataFrame(rows)
    n = int(len(yt))
    return {"n": n, "akurasi": float((yt == yp).mean()) if n else np.nan,
            "macro_f1": float(per["F1"].mean()) if n else np.nan, "per_kelas": per, "cm": cm}


def macro_f1_ci(y_benar: list, y_prediksi: list, kelas: list[str], b: int = 400, seed: int = 3) -> tuple[float, float]:
    """Selang kepercayaan 95% macro-F1 dengan bootstrap (sampel ulang pasangan label)."""
    yt, yp = np.array(y_benar, dtype=object), np.array(y_prediksi, dtype=object)
    ok = np.array([a in kelas for a in yt])
    yt, yp = yt[ok], yp[ok]
    if len(yt) < 10:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    nilai = []
    for _ in range(b):
        i = rng.integers(0, len(yt), len(yt))
        nilai.append(metrik(list(yt[i]), list(yp[i]), kelas)["macro_f1"])
    return float(np.percentile(nilai, 2.5)), float(np.percentile(nilai, 97.5))


def kappa(a: list, b: list) -> float:
    """Cohen's kappa: kesepakatan dua pelabel di luar kebetulan (1 = sempurna, 0 = setara kebetulan)."""
    a, b = np.array(a, dtype=object), np.array(b, dtype=object)
    if not len(a):
        return np.nan
    kelas = sorted(set(a) | set(b))
    po = float((a == b).mean())
    pe = sum(float((a == k).mean()) * float((b == k).mean()) for k in kelas)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def kesepakatan(label: pd.DataFrame) -> pd.DataFrame:
    """Kappa per pasangan pelabel untuk berita yang dilabeli keduanya (sentimen & dampak)."""
    rows = []
    pel = sorted(label["pelabel"].dropna().unique())
    for i, p1 in enumerate(pel):
        for p2 in pel[i + 1:]:
            a = label[label["pelabel"] == p1].set_index(["id", "emiten"])
            b = label[label["pelabel"] == p2].set_index(["id", "emiten"])
            sama = a.index.intersection(b.index)
            if len(sama) < 5:
                continue
            rows.append({"Pelabel": f"{p1} vs {p2}", "Berita sama": len(sama),
                         "Kappa sentimen": kappa(list(a.loc[sama, "sentimen"]), list(b.loc[sama, "sentimen"])),
                         "Kappa dampak": kappa(list(a.loc[sama, "dampak"]), list(b.loc[sama, "dampak"]))})
    return pd.DataFrame(rows)


def label_final(label: pd.DataFrame) -> pd.DataFrame:
    """Satu label per berita: bila beberapa pelabel, ambil suara terbanyak (seri → label terbaru)."""
    if label is None or label.empty:
        return pd.DataFrame(columns=["id", "emiten", "sentimen", "dampak"])

    def mayoritas(s: pd.Series):
        s = s.dropna()
        if s.empty:
            return None
        n = s.value_counts()
        return n.index[0] if (n == n.iloc[0]).sum() == 1 else s.iloc[0]
    x = label.sort_values("waktu", ascending=False)
    return x.groupby(["id", "emiten"], as_index=False).agg(sentimen=("sentimen", mayoritas),
                                                         dampak=("dampak", mayoritas))


def evaluasi(label: pd.DataFrame, prediksi: pd.DataFrame) -> dict:
    """label: id, emiten, sentimen, dampak (manusia, final). prediksi: id, emiten, sentimen_pred, dampak_pred
    (dampak_pred berupa kelas). → {"sentimen": metrik, "dampak": metrik, "relevansi": {...}, "n_cocok": int}."""
    g = label.merge(prediksi, on=["id", "emiten"], how="inner")
    out = {"n_cocok": len(g)}
    s = g[g["sentimen"].isin(KELAS_SENTIMEN)]
    out["sentimen"] = metrik(list(s["sentimen"]), list(s["sentimen_pred"]), KELAS_SENTIMEN)
    out["sentimen"]["ci"] = macro_f1_ci(list(s["sentimen"]), list(s["sentimen_pred"]), KELAS_SENTIMEN)
    d = g[g["dampak"].isin(KELAS_DAMPAK)]
    out["dampak"] = metrik(list(d["dampak"]), list(d["dampak_pred"]), KELAS_DAMPAK)
    out["dampak"]["ci"] = macro_f1_ci(list(d["dampak"]), list(d["dampak_pred"]), KELAS_DAMPAK)
    tr = g["dampak"] == TIDAK_RELEVAN
    out["relevansi"] = {"tidak_relevan": int(tr.sum()), "n": len(g),
                        "presisi_relevansi": float(1 - tr.mean()) if len(g) else np.nan}
    return out


def ringkas(hasil: dict[str, dict]) -> pd.DataFrame:
    """{mesin: hasil evaluasi} → tabel perbandingan mesin."""
    rows = []
    for mesin, h in hasil.items():
        for tugas in ("sentimen", "dampak"):
            m = h[tugas]
            per = m["per_kelas"].set_index("Kelas")
            kurang = [k for k, v in per["Support"].items() if v < MIN_PER_KELAS]
            rows.append({"Mesin": mesin, "Tugas": "Sentimen teks" if tugas == "sentimen" else "Dampak ke emiten",
                         "n": m["n"], "Accuracy": m["akurasi"], "Macro-F1": m["macro_f1"],
                         "CI 95% bawah": m["ci"][0], "CI 95% atas": m["ci"][1],
                         **{f"F1 {k}": per.loc[k, "F1"] for k in per.index},
                         "Catatan": ("indikatif: n < 100" if m["n"] < MIN_N else "") +
                                    ("; kelas kurang contoh: " + ", ".join(kurang) if kurang else "")})
    return pd.DataFrame(rows)


def prediksi(artikel: pd.DataFrame, emiten: pd.DataFrame, mesin: str = "Tersimpan", claude_key: str = "",
             claude_model: str = "claude-haiku-5-5") -> pd.DataFrame:
    """Prediksi satu mesin untuk artikel berlabel → id, emiten, sentimen_pred, dampak_pred (kelas evaluasi).
    'Tersimpan' = hasil yang sudah ada di database (mesin apa pun yang dipakai saat berita diambil)."""
    from . import analisis, intel
    from .sumber import pola_emiten
    if artikel is None or artikel.empty:
        return pd.DataFrame(columns=["id", "emiten", "sentimen_pred", "dampak_pred"])
    d = artikel.copy()
    if mesin != "Tersimpan":
        d = d.drop(columns=[c for c in ("skor", "label", "pendorong", "alasan", "mesin", "dampak", "dampak_label",
                                        "aspek", "materialitas", "penjelasan") if c in d.columns])
        d = analisis.nilai_artikel(d, emiten, mesin, claude_key, claude_model)
    info = {r["Nama"]: r for _, r in emiten.iterrows()}
    keluar = []
    for n, g in d.groupby("emiten"):
        e = info.get(n)
        sek = (e.get("Sektor") if e is not None else None) or "Lainnya"
        x = intel.perkaya(g, sek, (e.get("Website IR") if e is not None else "") or "",
                          pola_emiten(e) if e is not None else None)
        keluar.append(pd.DataFrame({"id": x["id"], "emiten": x["emiten"], "sentimen_pred": x["label"],
                                    "dampak_pred": x["dampak_label"].map(dampak_kelas)}))
    p = pd.concat(keluar, ignore_index=True) if keluar else pd.DataFrame(columns=["id", "emiten", "sentimen_pred",
                                                                                  "dampak_pred"])
    hilang = artikel[["id", "emiten"]].merge(p[["id", "emiten"]], how="left", indicator=True)
    hilang = hilang[hilang["_merge"] == "left_only"][["id", "emiten"]]
    if not hilang.empty:                      # Claude menganggap tidak relevan → prediksi 'Tidak relevan'
        p = pd.concat([p, hilang.assign(sentimen_pred="(tidak ada)", dampak_pred=TIDAK_RELEVAN)], ignore_index=True)
    return p
