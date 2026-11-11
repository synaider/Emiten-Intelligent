"""
Early Warning & Notifications: kirim peringatan ke Telegram (bot) dan/atau email (SMTP).

Telegram: buat bot lewat @BotFather → dapat token; kirim pesan ke bot; ambil chat_id dari
https://api.telegram.org/bot<TOKEN>/getUpdates (atau pakai id grup/channel).
Email: isi server SMTP kantor / Gmail (perlu App Password), port 587 (STARTTLS) atau 465 (SSL).
"""
from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage

import pandas as pd
import requests

IKON = {"Kritis": "🚨", "Tinggi": "🔴", "Sedang": "🟠", "Info": "🔵"}


def _waktu(t) -> str:
    if t is None or (isinstance(t, float) and pd.isna(t)):
        return ""
    t = pd.Timestamp(t)
    t = t.tz_convert("Asia/Jakarta") if t.tzinfo else t
    return t.strftime("%d/%m/%Y %H:%M")


def format_teks(nama: str, daftar, html_mode: bool = False, maks_pemicu: int = 8) -> str:
    esc = html.escape if html_mode else (lambda x: x)
    baris = [f"{'<b>' if html_mode else ''}Emiten Intelligence — {esc(nama)}{'</b>' if html_mode else ''}"]
    for p in daftar:
        judul = esc(p.judul)
        if html_mode and p.url:
            judul = f'<a href="{esc(p.url)}">{judul}</a>'
        baris.append(f"{IKON.get(p.tingkat, '•')} [{p.tingkat}] {esc(p.jenis)}: {judul}"
                     + (f"\n   {esc(p.detail)}" if p.detail else "") + (f" · {_waktu(p.waktu)}" if p.waktu else "")
                     + (f"\n   {p.url}" if p.url and not html_mode else ""))
        pemicu = [b for b in (getattr(p, "berita", None) or []) if b.get("url") != p.url]
        for b in pemicu[:maks_pemicu]:      # berita pemicu (mis. isi "lonjakan berita negatif")
            jb = esc(b.get("judul", ""))
            if html_mode and b.get("url"):
                jb = f'<a href="{esc(b["url"])}">{jb}</a>'
            baris.append(f"   • {jb} ({esc(b.get('sumber', ''))}"
                         + (f", {_waktu(b['waktu'])}" if b.get("waktu") else "") + ")"
                         + (f"\n     {b['url']}" if b.get("url") and not html_mode else ""))
        if len(pemicu) > maks_pemicu:
            baris.append(f"   … dan {len(pemicu) - maks_pemicu} berita lain (lihat dashboard)")
    baris.append("Pemantauan otomatis — bukan rekomendasi beli/jual.")
    return "\n".join(baris)


def kirim_telegram(token: str, chat_id: str, teks: str, sesi=None) -> None:
    if not token or not chat_id:
        raise ValueError("Token bot & chat_id Telegram belum diisi.")
    s = sesi or requests.Session()
    for i in range(0, len(teks), 3900):   # batas Telegram 4096 karakter
        r = s.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                   data={"chat_id": chat_id, "text": teks[i:i + 3900], "parse_mode": "HTML",
                         "disable_web_page_preview": "true"})
        if r.status_code != 200:
            try:
                pesan = r.json().get("description", r.text[:200])
            except ValueError:
                pesan = r.text[:200]
            raise RuntimeError(f"Telegram {r.status_code}: {pesan}")


def kirim_email(host: str, port: int, user: str, sandi: str, pengirim: str, ke: str, subjek: str, isi: str,
                isi_html: str | None = None) -> None:
    if not host or not ke:
        raise ValueError("Server SMTP & alamat tujuan belum diisi.")
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subjek, pengirim or user, ke
    m.set_content(isi)
    if isi_html:
        m.add_alternative(isi_html, subtype="html")
    port = int(port or 587)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            if user:
                s.login(user, sandi)
            s.send_message(m)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls(context=ctx)
                s.ehlo()
            if user:
                s.login(user, sandi)
            s.send_message(m)


def kirim(nama: str, daftar, cfg: dict, min_tingkat: str = "Sedang") -> list[str]:
    """Kirim peringatan (tingkat ≥ min_tingkat) ke semua kanal aktif. Kembalikan daftar kanal yang berhasil.
    cfg: tg_token, tg_chat, smtp_host, smtp_port, smtp_user, smtp_pass, smtp_dari, smtp_ke."""
    urut = ["Info", "Sedang", "Tinggi", "Kritis"]
    pilih = [p for p in daftar if urut.index(p.tingkat) >= urut.index(min_tingkat)]
    if not pilih:
        return []
    ok, galat = [], []
    if cfg.get("tg_token") and cfg.get("tg_chat"):
        try:
            kirim_telegram(cfg["tg_token"], cfg["tg_chat"], format_teks(nama, pilih, html_mode=True))
            ok.append("Telegram")
        except Exception as ex:  # noqa: BLE001
            galat.append(f"Telegram: {ex}")
    if cfg.get("smtp_host") and cfg.get("smtp_ke"):
        try:
            kirim_email(cfg["smtp_host"], cfg.get("smtp_port", 587), cfg.get("smtp_user", ""),
                        cfg.get("smtp_pass", ""), cfg.get("smtp_dari", ""), cfg["smtp_ke"],
                        f"[Peringatan] {nama}: {pilih[0].jenis}", format_teks(nama, pilih),
                        "<br>".join(format_teks(nama, pilih, html_mode=True).split("\n")))
            ok.append("Email")
        except Exception as ex:  # noqa: BLE001
            galat.append(f"Email: {ex}")
    if galat and not ok:
        raise RuntimeError("; ".join(galat))
    return ok
