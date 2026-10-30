#!/usr/bin/env python3
"""L'CARLIE — GÜNLÜK RAPOR (her sabah 09:00, e-posta)

NEDEN VAR
Yönetici özeti 08:15'te üretiliyor ve veritabanına yazılıyordu; kimseye
GITMIYORDU. Sahip 29.09.2026: *"Bana her gün saat 9'da rapor atacak,
L'CARLIE ile ilgili her şeyi raporlayacak."*

İLKELER
  🔴 "Veri yok" ile "soramadım" AYRI yazılır. Bir bölüm boşsa sebebi
     yazılır; sessizce atlanmaz. (Durum ayrımı kapısı.)
  🔴 Sistem etiketleri rapora taşınmaz. `BLOCKED_NEEDS_HUMAN` yerine
     "senin bir adımını bekliyor" yazılır. (Terimsel yazma kuralı.)
  🔴 Hiçbir rakam uydurulmaz. Sorgu hata verirse o bölüm "okunamadı"
     der ve hatayı taşır.
  🔴 Rapor DIŞ EYLEM YAPMAZ. Yalnız okur ve e-posta gönderir.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys

ALICI_VARSAYILAN = "moy.ozeryildiz@gmail.com"
GONDEREN = "info@lcarlie.com.tr"


def sorgu(sql: str) -> tuple[list[list[str]], str | None]:
    """psql ile salt okunur sorgu. (satirlar, hata) doner."""
    try:
        p = subprocess.run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n",
             "-d", "n8n", "-At", "-F", "\x1f", "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True, text=True, timeout=90)
    except Exception as hata:  # noqa: BLE001
        return [], f"sorgu çalıştırılamadı: {str(hata)[:120]}"
    if p.returncode != 0:
        return [], p.stderr.strip().splitlines()[-1][:200] if p.stderr else "bilinmeyen hata"
    satirlar = [s.split("\x1f") for s in p.stdout.strip().splitlines() if s.strip()]
    return satirlar, None


def bolum(baslik: str, sql: str, bicim, bos_mesaj: str = "kayıt yok") -> str:
    satirlar, hata = sorgu(sql)
    g = [f"\n{baslik}", "-" * len(baslik)]
    if hata:
        # 🔴 Okunamadi ile "veri yok" ayri seylerdir.
        g.append(f"  okunamadı — {hata}")
        return "\n".join(g)
    if not satirlar:
        g.append(f"  {bos_mesaj}")
        return "\n".join(g)
    try:
        g.extend(bicim(satirlar))
    except Exception as hata:  # noqa: BLE001
        g.append(f"  biçimlenemedi — {str(hata)[:120]}")
    return "\n".join(g)


def kabuk(komut: str) -> str:
    try:
        p = subprocess.run(["sh", "-c", komut], capture_output=True,
                           text=True, timeout=60)
        return p.stdout.strip()
    except Exception as hata:  # noqa: BLE001
        return f"okunamadı: {str(hata)[:80]}"


# ---------------------------------------------------------------- bolumler --
def b_ozet() -> str:
    def bic(s):
        satir = s[0]
        try:
            icerik = json.loads(satir[1])
        except Exception:  # noqa: BLE001
            return [f"  {satir[1][:600]}"]
        c = [f"  {icerik.get('executive_summary', '(özet yok)')}"]
        oncelik = icerik.get("priorities") or []
        if oncelik:
            c.append("\n  Öncelikler:")
            c += [f"    {i}. {x}" for i, x in enumerate(oncelik, 1)]
        risk = icerik.get("risks") or []
        if risk:
            c.append("\n  Riskler:")
            c += [f"    - {x}" for x in risk]
        return c
    return bolum(
        "1) YÖNETİCİ ÖZETİ (yapay zekâ, bu sabah üretildi)",
        "select konu, icerik from mart.gunluk_brief "
        "order by created_at desc limit 1;",
        bic, "bu sabah özet üretilmemiş — 08:15 koşumuna bak")


def b_para() -> str:
    def bic(s):
        r = s[0]
        return [
            f"  Gerçekleşmiş sipariş (tümü)   : {r[0]}",
            f"  Net ciro (KDV hariç)          : {r[1]} TL",
            f"  Ürün maliyeti                 : {r[2]} TL",
            f"  Bilinen katkı                 : {r[3]} TL",
            "  NOT: maliyet sahibin beyanıdır (400 TL/birim, KDV ve kargo dahil);",
            "       tedarikçi faturasıyla ölçülmüş değildir.",
        ]
    return bolum(
        "2) PARA",
        "select count(*), round(sum(net_ciro_kdv_haric),2), round(sum(cogs),2), "
        "round(sum(bilinen_bilesen_katkisi),2) from mart.siparis_ekonomi "
        "where gelir_durumu='REALIZED';",
        bic)


def b_satis() -> str:
    def bic(s):
        c = []
        for r in s:
            c.append(f"  {r[0]}  ·  {r[1]}  ·  {r[2]} TL  ·  {r[3]}")
        return c
    return bolum(
        "3) SON SİPARİŞLER (Wix)",
        "select to_char(olusturma,'DD.MM.YYYY HH24:MI'), kanal, toplam, ciro_sinifi "
        "from mart.siparis order by olusturma desc limit 5;",
        bic, "Wix'te hiç sipariş kaydı yok")


def b_elle() -> str:
    def bic(s):
        c = []
        for r in s:
            c.append(f"  {r[0]}  ·  {r[1]}  ·  {r[2]} TL  ·  tahsilat: {r[3]}")
        c.append("  (Bunlar Wix dışı, kapıda ödemeli satışlardır.)")
        return c
    return bolum(
        "4) ELLE SATIŞLAR (kapıda ödeme)",
        "select to_char(olusturma,'DD.MM.YYYY'), sehir, cod_tutar, "
        "coalesce(cod_durum,'bilinmiyor') from mart.gonderi "
        "where sinif='ELLE_SATIS' order by olusturma desc limit 6;",
        bic, "elle satış kaydı yok")


def b_reklam() -> str:
    def bic(s):
        r = s[0]
        son = r[1] or "hiç"
        return [
            f"  Son 7 günde harcama : {r[0]} TL",
            f"  En son harcama günü : {son}",
        ]
    return bolum(
        "5) REKLAM (Meta)",
        "select round(coalesce(sum(harcama),0),2), "
        "to_char(max(gun) filter (where harcama>0),'DD.MM.YYYY') "
        "from raw.meta_harcama where gun >= current_date-7;",
        bic)


def b_musteri() -> str:
    def bic(s):
        r = s[0]
        return [
            f"  Cevapsız konuşma : {r[0]}",
            f"  En uzun bekleyen : {r[1]} saat",
            "  NOT: 24 saati geçen konuşmalarda Messenger mesaj göndermeye",
            "       izin vermiyor; bunlar ancak kapatılarak çözülür.",
        ]
    return bolum(
        "6) BEKLEYEN MÜŞTERİ MESAJLARI",
        "select count(*), coalesce(round(max(bekleme_saat)),0) "
        "from mart.konusma_cevapsiz;",
        bic)


def b_gundem() -> str:
    def bic(s):
        return [f"  [{r[0]}] #{r[1]}  {r[2][:110]}" for r in s]
    return bolum(
        "7) SENİ BEKLEYEN KARARLAR",
        "select coalesce(oncelik,'--'), soru_id, soru from core.acik_soru "
        "where durum in ('OPEN','IN_PROGRESS','BLOCKED_NEEDS_HUMAN') "
        "order by case coalesce(oncelik,'P9') when 'P0' then 0 when 'P1' then 1 "
        "when 'P2' then 2 else 3 end, soru_id desc limit 12;",
        bic, "bekleyen karar yok")


def b_itibar() -> str:
    def bic(s):
        return [f"  {r[0]}  ·  {r[1]}" for r in s]
    return bolum(
        "8) BASINDA BİZ",
        "select kaynak_site, left(baslik,90) from core.basin_bahsi "
        "order by bulundu desc limit 8;",
        bic, "kayıtlı basın bahsi yok — otomatik tarama için arama anahtarı bekleniyor")


def b_departman() -> str:
    def bic(s):
        return [f"  {r[1]:>2} departman: {r[0]}" for r in s]
    return bolum(
        "9) DEPARTMAN DURUMU",
        "select durum, count(*) from core.departman group by durum order by 2 desc;",
        bic)


def b_sistem() -> str:
    basarisiz = kabuk("systemctl --failed --no-pager 2>/dev/null | grep -c '●' || true")
    timer = kabuk("systemctl list-timers --all --no-pager 2>/dev/null "
                  "| grep -Eic '(lcarlie|jarvis)[a-z0-9._-]*\\.timer' || true")
    disk = kabuk("df -h / | awk 'NR==2{print $5\" dolu (\"$4\" boş)\"}'")
    yuk = kabuk("uptime | sed 's/.*load average: //'")
    g = ["\n10) SİSTEM", "-" * 10,
         f"  Başarısız birim : {basarisiz or '?'}",
         f"  Çalışan zamanlayıcı : {timer or '?'}",
         f"  Disk : {disk or 'okunamadı'}",
         f"  Yük  : {yuk or 'okunamadı'}"]
    return "\n".join(g)


def b_site() -> str:
    son = kabuk(
        "journalctl -u lcarlie-site-nobeti.service --since '24 hours ago' "
        "--no-pager 2>/dev/null | grep -c 'CRITICAL' || true")
    uyari = kabuk(
        "journalctl -u lcarlie-site-nobeti.service --since '24 hours ago' "
        "--no-pager 2>/dev/null | grep -c 'WARNING' || true")
    g = ["\n11) SİTE NÖBETİ (son 24 saat)", "-" * 29,
         f"  Kritik bulgu : {son or '0'}",
         f"  Uyarı        : {uyari or '0'}"]
    if (son or "0") == "0" and (uyari or "0") == "0":
        g.append("  Son 24 saatte nöbet koşmamış olabilir — nöbet 07:15 ve 15:15'te çalışır.")
    return "\n".join(g)


def b_instagram() -> str:
    """Gunluk Instagram paketi (30.10.2026). Sahip sabah raporda gorsun."""
    def bic(s):
        g = [f"  Ürün: {s[0][0]}  ·  {len(s)} içerik  ·  panel: KATALOG > INSTAGRAM PLANI"]
        for r in s:
            bulgu = "  MEVZUAT BULGUSU" if r[4] != "TEMIZ" else ""
            g.append(f"  {r[1]}) {r[2]:<10} puan {r[5]:>3} · {r[6]:<11} · {r[7]}{bulgu}")
            g.append(f"       “{r[3][:90]}”")
        return g
    return bolum(
        "12) INSTAGRAM GÜNLÜK PAKET (bugün)",
        "select urun_slug, sira, bicim, kanca, denetim, coalesce(kanca_puani::text,'-'), "
        "coalesce(uzman_karari,'-'), durum from core.ig_gonderi_plani "
        "where kaynak='GUNLUK' and gun=current_date order by sira;",
        bic, "bugün paket üretilmedi -- lcarlie-ig-gunluk.timer 07:30'da koşar")


def rapor() -> str:
    bugun = dt.datetime.now().strftime("%d.%m.%Y %A")
    bas = [
        f"L'CARLIÉ GÜNLÜK RAPOR — {bugun}",
        "=" * 52,
        "Bu rapor sunucudaki ölçümlerden otomatik üretildi. Rakamların",
        "kaynağı yazılıdır; okunamayan bölüm 'okunamadı' der, boş geçilmez.",
    ]
    parcalar = [b_ozet(), b_para(), b_satis(), b_elle(), b_reklam(),
                b_musteri(), b_gundem(), b_itibar(), b_departman(),
                b_sistem(), b_site(), b_instagram()]
    son = ["", "=" * 52,
           "Panel: https://jarvis.lcarlie.shop",
           "Bu raporu üreten: lcarlie-gunluk-rapor.timer (her gün 09:00)"]
    return "\n".join(bas) + "\n" + "\n".join(parcalar) + "\n" + "\n".join(son)


def gonder(metin: str, alici: str) -> bool:
    konu = f"L'CARLIE gunluk rapor - {dt.datetime.now():%d.%m.%Y}"
    ileti = (f"To: {alici}\nFrom: {GONDEREN}\nSubject: {konu}\n"
             "Content-Type: text/plain; charset=UTF-8\n\n" + metin)
    p = subprocess.run(["msmtp", "--account=lcarlie", alici],
                       input=ileti, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        print(f"GONDERILEMEDI: {p.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaz", action="store_true", help="e-posta gonderme, ekrana yaz")
    ap.add_argument("--alici", default=ALICI_VARSAYILAN)
    a = ap.parse_args()
    metin = rapor()
    if a.yaz:
        print(metin)
        return 0
    ok = gonder(metin, a.alici)
    print(f"rapor {'gönderildi' if ok else 'GÖNDERİLEMEDİ'} -> {a.alici}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
