"""
Direktori emiten / counterparty yang dipantau.

Daftar bawaan = 44 counterparty Non Manajer Investasi pada file "Limit Counterparty"
(sama dengan aplikasi Limit Counterparty). Tiap emiten punya:
  - Nama        : nama group seperti di file limit (kunci utama, dipakai mencocokkan rating)
  - Kode        : kode PEFINDO / IDX entitas acuan (boleh kosong)
  - Entitas     : nama entitas yang dirating
  - Alias       : nama lain yang dipakai media (pisahkan dengan ;) -> dipakai menyaring berita
  - Kueri       : kata kunci pencarian berita (pisahkan dengan ;)
  - Terkait     : anak usaha, merek, induk, atau entitas terkait (pisahkan dengan ;) -> berita tentang mereka
                  dihitung sebagai relasi "Entitas terkait" (tidak langsung, bobot lebih kecil)
  - Pengecualian: kata yang membuat berita DIBUANG bila muncul (pisahkan dengan ;) — untuk nama mirip yang
                  TIDAK berhubungan
  - Website IR  : domain situs resmi emiten (mis. bri.co.id) -> dicari sebagai sumber resmi
  - Kode AS     : kode saham/ADR di bursa AS bila ada (mis. TLK) -> pengajuan resmi di SEC EDGAR
  - Sektor, Lembaga Utama (PEFINDO / Fitch), Aktif

Semua bisa diubah di tab "Emiten & Rating" dan disimpan ke data/emiten.xlsx.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

KOLOM = ["Aktif", "Nama", "Kode", "Entitas", "Sektor", "Lembaga Utama", "Alias", "Terkait", "Kueri", "Pengecualian",
         "Website IR", "Kode AS"]

# (Nama group, Kode, Entitas, Sektor, Lembaga utama, Alias, Kueri, Pengecualian)
_DEFAULT = [
    ("BRI GROUP", "BBRI", "PT Bank Rakyat Indonesia (Persero) Tbk", "Perbankan", "PEFINDO",
     "Bank Rakyat Indonesia; BBRI; Bank BRI; BRI", '"Bank Rakyat Indonesia"; BBRI; "Bank BRI"', ""),
    ("MANDIRI GROUP", "BMRI", "PT Bank Mandiri (Persero) Tbk", "Perbankan", "PEFINDO",
     "Bank Mandiri; BMRI", '"Bank Mandiri"; BMRI', ""),
    ("PLN GROUP", "PPLN", "PT Perusahaan Listrik Negara (Persero)", "Energi & Utilitas", "PEFINDO",
     "Perusahaan Listrik Negara; PLN", '"PLN (Persero)"; "Perusahaan Listrik Negara"; "PT PLN"', ""),
    ("SMI GROUP", "SMII", "PT Sarana Multi Infrastruktur (Persero)", "Pembiayaan BUMN", "PEFINDO",
     "Sarana Multi Infrastruktur; PT SMI", '"Sarana Multi Infrastruktur"; "PT SMI"', ""),
    ("INDOSAT GROUP", "ISAT", "PT Indosat Tbk", "Telekomunikasi", "PEFINDO",
     "Indosat; ISAT; Indosat Ooredoo Hutchison; IOH", 'Indosat; ISAT', ""),
    ("BNI GROUP", "BBNI", "PT Bank Negara Indonesia (Persero) Tbk", "Perbankan", "PEFINDO",
     "Bank Negara Indonesia; BBNI; Bank BNI; BNI", '"Bank Negara Indonesia"; BBNI; "Bank BNI"', ""),
    ("DJARUM GROUP", "BBCA", "PT Bank Central Asia Tbk", "Perbankan", "PEFINDO",
     "Bank Central Asia; BBCA; BCA", '"Bank Central Asia"; BBCA; "Bank BCA"', ""),
    ("INDONESIA EXIMBANK GROUP", "BEXI", "Lembaga Pembiayaan Ekspor Indonesia", "Pembiayaan BUMN", "PEFINDO",
     "Lembaga Pembiayaan Ekspor Indonesia; Indonesia Eximbank; LPEI", '"Lembaga Pembiayaan Ekspor Indonesia"; LPEI; "Indonesia Eximbank"', ""),
    ("SMF GROUP", "SMFP", "PT Sarana Multigriya Finansial (Persero)", "Pembiayaan BUMN", "PEFINDO",
     "Sarana Multigriya Finansial; PT SMF", '"Sarana Multigriya Finansial"; "PT SMF"', ""),
    ("MAYBANK INDONESIA GROUP", "BNII", "PT Bank Maybank Indonesia Tbk", "Perbankan", "PEFINDO",
     "Maybank Indonesia; BNII", '"Maybank Indonesia"; BNII', ""),
    ("ASTRA GROUP", "ASII", "PT Astra International Tbk", "Konglomerasi", "PEFINDO",
     "Astra International; ASII", '"Astra International"; ASII', ""),
    ("TELKOM GROUP", "TLKM", "PT Telkom Indonesia (Persero) Tbk", "Telekomunikasi", "PEFINDO",
     "Telkom Indonesia; TLKM; Telekomunikasi Indonesia; Telkom", '"Telkom Indonesia"; TLKM', "Telkom University"),
    ("CIMB NIAGA GROUP", "BNGA", "PT Bank CIMB Niaga Tbk", "Perbankan", "PEFINDO",
     "CIMB Niaga; BNGA", '"CIMB Niaga"; BNGA', ""),
    ("MITSUBISHI UFJ F.GROUP", "BDMN", "PT Bank Danamon Indonesia Tbk", "Perbankan", "PEFINDO",
     "Bank Danamon; Danamon; BDMN; MUFG", '"Bank Danamon"; BDMN', ""),
    ("SUMITOMO MITSUI FINANCIAL GROUP", "", "Sumitomo Mitsui Financial Group", "Perbankan", "Fitch",
     "Sumitomo Mitsui Financial; SMFG", '"Sumitomo Mitsui Financial"; SMFG', ""),
    ("PT WOORI FINANCIAL GROUP", "SDRA", "PT Bank Woori Saudara Indonesia 1906 Tbk", "Perbankan", "PEFINDO",
     "Woori Saudara; SDRA; Woori Financial", '"Woori Saudara"; SDRA', ""),
    ("BTN GROUP", "BBTN", "PT Bank Tabungan Negara (Persero) Tbk", "Perbankan", "PEFINDO",
     "Bank Tabungan Negara; BBTN; Bank BTN; BTN", '"Bank Tabungan Negara"; BBTN; "Bank BTN"', ""),
    ("SEMEN INDONESIA GROUP", "SMGR", "PT Semen Indonesia (Persero) Tbk", "Industri Dasar", "PEFINDO",
     "Semen Indonesia; SMGR", '"Semen Indonesia"; SMGR', ""),
    ("INJOURNEY GROUP", "INJH", "PT Aviasi Pariwisata Indonesia (Persero)", "Transportasi & Pariwisata", "PEFINDO",
     "InJourney; Aviasi Pariwisata Indonesia", 'InJourney; "Aviasi Pariwisata Indonesia"', ""),
    ("KAI GROUP", "KAII", "PT Kereta Api Indonesia (Persero)", "Transportasi & Pariwisata", "PEFINDO",
     "Kereta Api Indonesia; PT KAI; KAI", '"Kereta Api Indonesia"; "PT KAI"', ""),
    ("BANGKOK BANK PC LIMITED", "", "Bangkok Bank Public Company Limited", "Perbankan", "Fitch",
     "Bangkok Bank", '"Bangkok Bank"', ""),
    ("SALIM GROUP", "INDF", "PT Indofood Sukses Makmur Tbk", "Konsumer", "PEFINDO",
     "Indofood Sukses Makmur; Indofood; INDF", '"Indofood Sukses Makmur"; INDF', ""),
    ("PANIN GROUP", "PNBN", "PT Bank Pan Indonesia Tbk", "Perbankan", "PEFINDO",
     "Bank Panin; Panin Bank; Bank Pan Indonesia; PNBN", '"Bank Panin"; PNBN', ""),
    ("CT CORP GROUP", "MEGA", "PT Bank Mega Tbk", "Perbankan", "PEFINDO",
     "Bank Mega", '"Bank Mega"', ""),
    ("HK GROUP", "PTHK", "PT Hutama Karya (Persero)", "Konstruksi BUMN", "PEFINDO",
     "Hutama Karya", '"Hutama Karya"', ""),
    ("SINARMAS GROUP", "ASMS", "PT Asuransi Sinar Mas", "Konglomerasi", "PEFINDO",
     "Asuransi Sinar Mas; Sinar Mas; Sinarmas", '"Asuransi Sinar Mas"; "Sinar Mas"', ""),
    ("JASA MARGA GROUP", "JSMR", "PT Jasa Marga (Persero) Tbk", "Infrastruktur", "PEFINDO",
     "Jasa Marga; JSMR", '"Jasa Marga"; JSMR', ""),
    ("BANK RAYA INDONESIA", "AGRO", "PT Bank Raya Indonesia Tbk", "Perbankan", "PEFINDO",
     "Bank Raya; AGRO", '"Bank Raya"', ""),
    ("BANK SULSELBAR GROUP", "BSSB", "PT Bank Pembangunan Daerah Sulawesi Selatan dan Sulawesi Barat", "Bank Daerah",
     "PEFINDO", "Bank Sulselbar; Sulselbar", '"Bank Sulselbar"', ""),
    ("BARITO PACIFIC GROUP", "BRPT", "PT Barito Pacific Tbk", "Energi & Petrokimia", "PEFINDO",
     "Barito Pacific; BRPT", '"Barito Pacific"; BRPT', ""),
    ("BANK JATENG GROUP", "BJTG", "PT Bank Pembangunan Daerah Jawa Tengah", "Bank Daerah", "PEFINDO",
     "Bank Jateng; Bank Pembangunan Daerah Jawa Tengah", '"Bank Jateng"', ""),
    ("BANK JATIM GROUP", "BJTM", "PT Bank Pembangunan Daerah Jawa Timur Tbk", "Bank Daerah", "PEFINDO",
     "Bank Jatim; BJTM", '"Bank Jatim"; BJTM', ""),
    ("BANK NAGARI GROUP", "BSBR", "PT Bank Nagari", "Bank Daerah", "PEFINDO",
     "Bank Nagari", '"Bank Nagari"', ""),
    ("PTPP GROUP", "PTPP", "PT Pembangunan Perumahan (Persero) Tbk", "Konstruksi BUMN", "PEFINDO",
     "PTPP; PP (Persero); Pembangunan Perumahan", 'PTPP; "PP (Persero)"', ""),
    ("SULUTGO GROUP", "BSLT", "PT Bank SulutGo", "Bank Daerah", "PEFINDO",
     "Bank SulutGo; SulutGo", '"Bank SulutGo"; SulutGo', ""),
    ("WASKITA GROUP", "WSKT", "PT Waskita Karya (Persero) Tbk", "Konstruksi BUMN", "PEFINDO",
     "Waskita Karya; Waskita; WSKT", '"Waskita Karya"; WSKT', ""),
    ("DBS GROUP", "", "PT Bank DBS Indonesia", "Perbankan", "Fitch",
     "Bank DBS Indonesia; DBS Indonesia", '"Bank DBS Indonesia"; "DBS Indonesia"', ""),
    ("BAF GROUP", "BAFI", "PT Bussan Auto Finance", "Multifinance", "PEFINDO",
     "Bussan Auto Finance; BAF", '"Bussan Auto Finance"', ""),
    ("BJB GROUP", "BJBR", "PT Bank Pembangunan Daerah Jawa Barat dan Banten Tbk", "Bank Daerah", "PEFINDO",
     "Bank BJB; BJBR; bank bjb", '"Bank BJB"; BJBR', ""),
    ("MERDEKA GROUP", "MDKA", "PT Merdeka Copper Gold Tbk", "Pertambangan", "PEFINDO",
     "Merdeka Copper Gold; MDKA", '"Merdeka Copper Gold"; MDKA', ""),
    ("OCBC GROUP", "NISP", "PT Bank OCBC NISP Tbk", "Perbankan", "PEFINDO",
     "OCBC NISP; Bank OCBC; NISP; OCBC Indonesia", '"OCBC NISP"; NISP; "Bank OCBC"', ""),
    ("PT METAMORFOSIS EKOSISTEM INDONESIA", "", "PT Metamorfosis Ekosistem Indonesia", "Lainnya", "Fitch",
     "Metamorfosis Ekosistem Indonesia", '"Metamorfosis Ekosistem Indonesia"', ""),
    ("BANK JAKARTA GROUP", "BDKI", "PT Bank Jakarta", "Bank Daerah", "PEFINDO",
     "Bank Jakarta; Bank DKI", '"Bank Jakarta"; "Bank DKI"', ""),
    ("BANK BTPN GROUP", "BTPN", "PT Bank SMBC Indonesia Tbk", "Perbankan", "Fitch",
     "Bank SMBC Indonesia; SMBC Indonesia; BTPN; Bank BTPN", '"SMBC Indonesia"; BTPN', ""),
]


# Entitas terkait (anak usaha / merek / induk). Bisa diubah di aplikasi.
TERKAIT_BAWAAN = {
    "BRI GROUP": "BRImo; Pegadaian; PNM; Permodalan Nasional Madani; BRI Life; BRI Finance; BRI Danareksa; Bank Raya; "
                 "BRI Insurance",
    "MANDIRI GROUP": "Livin' by Mandiri; Bank Syariah Indonesia; Mandiri Sekuritas; Mandiri Tunas Finance; AXA Mandiri; "
                     "Mandiri Taspen; Mandiri Utama Finance",
    "PLN GROUP": "PLN Indonesia Power; PLN Nusantara Power; PLN Icon Plus",
    "INDOSAT GROUP": "IM3; Lintasarta; Indosat Ooredoo Hutchison",
    "BNI GROUP": "wondr by BNI; BNI Sekuritas; BNI Life; BNI Finance",
    "DJARUM GROUP": "BCA Syariah; BCA Digital; blu by BCA; BCA Finance; Dwimuria Investama Andalan",
    "ASTRA GROUP": "Astra Honda Motor; Toyota Astra Motor; Astra Otoparts; United Tractors; Astra Agro Lestari; "
                   "Federal International Finance; Astra Credit Companies; Toyota Astra Financial; Pamapersada",
    "TELKOM GROUP": "Telkomsel; IndiHome; Mitratel; Dayamitra Telekomunikasi",
    "MITSUBISHI UFJ F.GROUP": "MUFG; Adira Finance; Adira Dinamika Multi Finance",
    "BANK BTPN GROUP": "SMBC; Jenius; BTPN Syariah",
    "SUMITOMO MITSUI FINANCIAL GROUP": "SMBC Indonesia; Bank BTPN",
    "SEMEN INDONESIA GROUP": "Semen Gresik; Semen Padang; Semen Tonasa; Solusi Bangun Indonesia; Semen Baturaja",
    "INJOURNEY GROUP": "InJourney Airports; Angkasa Pura; Hotel Indonesia Natour; Sarinah; ITDC; Taman Wisata Candi",
    "KAI GROUP": "KAI Commuter; KCIC; Whoosh; LRT Jabodebek",
    "SALIM GROUP": "Indofood CBP; ICBP; Indomie; Bogasari; Indomobil",
    "CT CORP GROUP": "Allo Bank; Bank Mega Syariah; Transmart; Trans Retail",
    "SINARMAS GROUP": "Sinar Mas Land; Bumi Serpong Damai; Golden Agri; SMART Tbk; Indah Kiat; Tjiwi Kimia; Asia Pulp "
                      "& Paper; Dian Swastatika Sentosa",
    "BARITO PACIFIC GROUP": "Chandra Asri; TPIA; Barito Renewables; BREN; Star Energy",
    "MERDEKA GROUP": "Merdeka Battery Materials; MBMA; Tujuh Bukit; Merdeka Gold Resources",
    "WASKITA GROUP": "Waskita Beton Precast; WSBP; Waskita Toll Road",
    "HK GROUP": "Hutama Karya Infrastruktur; Tol Trans Sumatera",
    "PANIN GROUP": "Panin Dubai Syariah; Clipan Finance",
    "BJB GROUP": "bank bjb syariah",
    "OCBC GROUP": "OCBC Group; Oversea-Chinese Banking Corporation",
    "MAYBANK INDONESIA GROUP": "Malayan Banking; Maybank Group",
    "CIMB NIAGA GROUP": "CIMB Group; CIMB Niaga Auto Finance",
    "DBS GROUP": "DBS Group; DBS Bank",
    "PT WOORI FINANCIAL GROUP": "Woori Bank; Woori Finance Indonesia",
    "BANK RAYA INDONESIA": "Bank Rakyat Indonesia",
    "JASA MARGA GROUP": "Jasamarga Transjawa Tol",
}
WEBSITE_IR = {
    "BRI GROUP": "bri.co.id", "MANDIRI GROUP": "bankmandiri.co.id", "PLN GROUP": "pln.co.id", "SMI GROUP": "ptsmi.co.id",
    "INDOSAT GROUP": "ioh.co.id", "BNI GROUP": "bni.co.id", "DJARUM GROUP": "bca.co.id",
    "INDONESIA EXIMBANK GROUP": "indonesiaeximbank.go.id", "SMF GROUP": "smf-indonesia.co.id",
    "MAYBANK INDONESIA GROUP": "maybank.co.id", "ASTRA GROUP": "astra.co.id", "TELKOM GROUP": "telkom.co.id",
    "CIMB NIAGA GROUP": "cimbniaga.co.id", "MITSUBISHI UFJ F.GROUP": "danamon.co.id",
    "PT WOORI FINANCIAL GROUP": "bankwoorisaudara.com", "BTN GROUP": "btn.co.id", "SEMEN INDONESIA GROUP": "sig.id",
    "INJOURNEY GROUP": "injourney.id", "KAI GROUP": "kai.id", "SALIM GROUP": "indofood.com", "PANIN GROUP": "panin.co.id",
    "CT CORP GROUP": "bankmega.com", "HK GROUP": "hutamakarya.com", "JASA MARGA GROUP": "jasamarga.com",
    "BANK RAYA INDONESIA": "bankraya.co.id", "BANK SULSELBAR GROUP": "banksulselbar.co.id",
    "BARITO PACIFIC GROUP": "barito-pacific.com", "BANK JATENG GROUP": "bankjateng.co.id",
    "BANK JATIM GROUP": "bankjatim.co.id", "BANK NAGARI GROUP": "banknagari.co.id", "PTPP GROUP": "ptpp.co.id",
    "SULUTGO GROUP": "banksulutgo.co.id", "WASKITA GROUP": "waskita.co.id", "DBS GROUP": "dbs.id", "BAF GROUP": "baf.id",
    "BJB GROUP": "bankbjb.co.id", "MERDEKA GROUP": "merdekacoppergold.com", "OCBC GROUP": "ocbc.id",
    "BANK JAKARTA GROUP": "bankdki.co.id", "BANK BTPN GROUP": "smbci.com",
}
KODE_AS = {"TELKOM GROUP": "TLK", "MITSUBISHI UFJ F.GROUP": "MUFG", "SUMITOMO MITSUI FINANCIAL GROUP": "SMFG"}


def key_group(nama) -> str:
    """'BRI GROUP+)' -> 'BRI GROUP'; spasi ganda dirapatkan; huruf besar."""
    s = re.sub(r"[+\-]\)\s*$", "", str(nama or "")).strip()
    return re.sub(r"\s+", " ", s).upper()


def pisah(teks) -> list[str]:
    """'a; b; "c d"' -> ['a', 'b', '"c d"'] (kosong dibuang)."""
    if teks is None or (isinstance(teks, float) and pd.isna(teks)):
        return []
    return [t.strip() for t in str(teks).split(";") if t.strip()]


def default_emiten() -> pd.DataFrame:
    rows = [{"Aktif": True, "Nama": n, "Kode": k, "Entitas": e, "Sektor": s, "Lembaga Utama": l,
             "Alias": a, "Terkait": TERKAIT_BAWAAN.get(n, ""), "Kueri": q, "Pengecualian": x,
             "Website IR": WEBSITE_IR.get(n, ""), "Kode AS": KODE_AS.get(n, "")} for n, k, e, s, l, a, q, x in _DEFAULT]
    return pd.DataFrame(rows, columns=KOLOM)


def rapikan(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in KOLOM:
        if c not in df.columns:
            df[c] = True if c == "Aktif" else ""
    df = df[KOLOM]
    df["Aktif"] = df["Aktif"].fillna(True).astype(bool)
    for c in KOLOM[1:]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    df = df[df["Nama"] != ""]
    df = df.drop_duplicates(subset=["Nama"], keep="first").reset_index(drop=True)
    return df


def muat(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            d = pd.read_excel(path, sheet_name="Emiten")
            lama = "Terkait" not in d.columns
            d = rapikan(d)
            if lama:  # file versi sebelumnya: isi kolom baru dari bawaan, pengecualian lama yang kini 'Terkait' dibuang
                b = default_emiten().set_index("Nama")
                for c in ("Terkait", "Website IR", "Kode AS"):
                    d[c] = [b[c].get(n, "") if n in b.index else "" for n in d["Nama"]]
                d["Pengecualian"] = [b["Pengecualian"].get(n, x) if n in b.index else x
                                     for n, x in zip(d["Nama"], d["Pengecualian"])]
                simpan(d, path)
            return d
        except Exception:  # noqa: BLE001
            pass
    df = default_emiten()
    simpan(df, path)
    return df


def simpan(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        rapikan(df).to_excel(xw, sheet_name="Emiten", index=False)
        ws = xw.book["Emiten"]
        for col, w in zip("ABCDEFGHIJKL", [7, 34, 8, 44, 22, 12, 50, 60, 50, 30, 24, 10]):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "C2"


def emiten_kustom(nama: str, kode: str = "", alias_tambahan: str = "") -> pd.Series:
    """Emiten yang diketik sendiri (di luar daftar). Nama perusahaan + kode saham jadi alias & kata kunci."""
    nama = re.sub(r"\s+", " ", (nama or "").strip())
    kode = (kode or "").strip().upper()
    inti = re.sub(r"^(PT\.?\s+)|\s+(Tbk\.?|\(Persero\))$", "", nama, flags=re.I).strip()
    alias = [inti] + ([kode] if kode else []) + pisah(alias_tambahan)
    kueri = [f'"{inti}"'] + ([kode] if len(kode) == 4 else []) + [f'"{a}"' for a in pisah(alias_tambahan)]
    return pd.Series({"Aktif": True, "Nama": key_group(inti), "Kode": kode, "Entitas": nama, "Sektor": "",
                      "Lembaga Utama": "PEFINDO", "Alias": "; ".join(dict.fromkeys(alias)), "Terkait": "",
                      "Kueri": "; ".join(dict.fromkeys(kueri)), "Pengecualian": "", "Website IR": "", "Kode AS": ""})


def cari(df: pd.DataFrame, teks: str) -> str | None:
    """Pencarian pintar: kode, nama group, nama entitas, alias, merek/anak usaha -> Nama emiten.
    Mis. 'BBRI', 'bank rakyat', 'Telkomsel' (-> TELKOM GROUP), 'Indomie' (-> SALIM GROUP)."""
    q = re.sub(r"\s+", " ", (teks or "").strip()).lower()
    if not q:
        return None
    for kol in ("Kode", "Nama"):
        hit = df[df[kol].str.lower() == q]
        if not hit.empty:
            return hit.iloc[0]["Nama"]
    for kol in ("Alias", "Entitas", "Terkait"):
        for _, r in df.iterrows():
            if any(q == x.strip('"').lower() for x in pisah(r[kol])) or \
                    (kol == "Entitas" and len(q) >= 4 and q in r[kol].lower()):
                return r["Nama"]
    for _, r in df.iterrows():
        teks_all = " ".join(str(r[k]) for k in ("Nama", "Entitas", "Alias", "Terkait")).lower()
        if len(q) >= 4 and q in teks_all:
            return r["Nama"]
    return None


def tambah_dari_limit(df: pd.DataFrame, nama_list: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Tambahkan nama group dari file limit yang belum ada di daftar (dengan alias = nama tanpa 'GROUP')."""
    ada = {key_group(n) for n in df["Nama"]}
    baru = []
    for n in nama_list:
        k = key_group(n)
        if not k or k in ada:
            continue
        inti = re.sub(r"\b(GROUP|GRUP|PT|TBK)\b", "", k).strip(" .")
        baru.append({"Aktif": True, "Nama": k, "Kode": "", "Entitas": inti.title(), "Sektor": "", "Lembaga Utama":
                     "PEFINDO", "Alias": inti.title(), "Terkait": "", "Kueri": f'"{inti.title()}"',
                     "Pengecualian": "", "Website IR": "", "Kode AS": ""})
        ada.add(k)
    if baru:
        df = pd.concat([df, pd.DataFrame(baru)], ignore_index=True)
    return rapikan(df), [b["Nama"] for b in baru]
