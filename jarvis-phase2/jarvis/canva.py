"""CANVA CONNECT — Jarvis'in kendi entegrasyonu.

Sahip 22.09.2026: *"Canva'yı bizim Jarvis'e bağlı, bir sürü özelliği ve
entegrasyonu var. Canva'yı bir araştır neler yapabilir neler yapamaz,
sonra bağla."*

ARAŞTIRMA SONUCU — ÖLÇÜLDÜ, TAHMİN DEĞİL
  · **"API key" YOK.** OAuth 2.0 + PKCE (SHA-256). Geliştirici portalında
    uygulama kaydı, client_id + client_secret, bir kereye mahsus tarayıcı
    yetkilendirmesi; sonra yenileme jetonuyla süresiz erişim.
  · **Autofill API ENTERPRISE ister** (belge birebir: "must act on behalf
    of a user who is a member of a Canva Enterprise organization").
    Denendi, `Not allowed to access brand template` hatası alındı.
  · **AMA GEREKMİYOR:** tasarımı doğrudan düzenleme ucu çalışıyor.
    Kanıtlandı: sahibin tasarımının kopyasında beş metin değiştirildi,
    tipografi ve yerleşim hiç bozulmadan.
  · **Varlık yükleme HAM İKİLİ kabul ediyor** (application/octet-stream).
    Herkese açık URL GEREKMİYOR -- bu, hazır bağlayıcının aşamadığı
    engeldi ve kendi entegrasyonumuzun asıl kazancı.
  · **Canva CLI (`@canva/cli`) YANLIŞ KAPI.** O Apps SDK içindir; kendi
    dokümanı diyor ki: "this CLI doesn't yet support REST API
    configuration for apps built with the Connect API."

UÇ ADRESLERİ DOĞRULANDI (curl ile, 22.09.2026)
  authorize  https://www.canva.com/api/oauth/authorize   -> 403 (var)
  token      https://api.canva.com/rest/v1/oauth/token   -> invalid_client
             (yani adres doğru, kimlik bekliyor)
  `/oauth/tokens` (çoğul) YANLIŞ: content-type reddediyor.

🔴 JETONLAR DİSKTE, MOD 600, ROOT. Erişim jetonu kısa ömürlü, yenileme
jetonu uzun. Yenileme jetonu kaybolursa sahibin tarayıcıdan yeniden
yetki vermesi gerekir -- o yüzden dosya izinleri gevşetilmez.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

AUTH_UC = "https://www.canva.com/api/oauth/authorize"
TOKEN_UC = "https://api.canva.com/rest/v1/oauth/token"
API = "https://api.canva.com/rest/v1"

# 🔴 BU DIZIN KEYFI DEGIL. jarvis-web.service `ProtectSystem=strict` ile
# koşuyor ve `ReadWritePaths` yalnızca burayı içeriyor; ayrıca
# `PrivateTmp=yes` olduğu için /tmp servis dışından paylaşılmıyor.
# Yolu değiştirmeden önce `systemctl show jarvis-web -p PrivateTmp
# -p ProtectSystem -p ReadWritePaths` çıktısına bak.
DURUM_DIZIN = Path(os.environ.get(
    "JARVIS_STATE", "/opt/lcarlie/jarvis-phase2/state"))

JETON_YOL = Path(os.environ.get("CANVA_JETON", str(DURUM_DIZIN / "canva.json")))
GECICI = Path(os.environ.get("CANVA_PKCE", str(DURUM_DIZIN / "canva-pkce.json")))

# 🔴 İstenen yetkiler DAR TUTULDU. Her scope, kötü bir günde yapılabilecek
# şeyin sınırıdır; "her ihtimale karşı" fazladan yetki almak, gereksiz
# risk taşımak demektir.
KAPSAM = (
    # 🔴 Sahip kararı (21.09.2026): "hepsini işaretle ne var ne yok".
    # Kaynak: resmî şartnamenin securitySchemes bloğu — 18 yetkiden
    # OIDC'ye ait 3'ü (openid/email/profile) çıkarıldı, kalan 15'i.
    "asset:read asset:write "
    "brandtemplate:content:read brandtemplate:content:write "
    "brandtemplate:meta:read "
    "collaboration:event "
    "comment:read comment:write "
    "design:content:read design:content:write design:meta:read "
    "folder:permission:write folder:read folder:write "
    "profile:read"
)

# 🔴 `brandtemplate:*` BILEREK ISTENMIYOR. Şartnamedeki <Availability>
# bloğu brand-template uçlarının tamamı için Canva Enterprise şartı
# koyuyor; üyeliğimiz Pro. Kullanılamayacak yetkiyi istemek, kazanç
# getirmeden yetki alanını genişletmek olur.

# 🔴 BU LİSTE BİLEREK BOŞ. Şartnamenin <Availability> metnine bakarak
# doldurmuştum; 22.09.2026'da gerçek hesapla ölçünce YANLIŞ olduğu çıktı:
# /brand-templates 200, /folders/root/items 200, /autofills 404 (403 değil)
# döndü — yani metin bizim hesabımız için bağlayıcı değilmiş.
# Gerçek kapı `x-required-capabilities` + hesabın yetkinlik listesi; onu
# _yetkinlik_kapisi() ölçüyor. Buraya bir şey eklemeden ÖNCE o ucu çağırıp
# gerçekten 403 döndüğünü gör.
KURUMSAL_UCLAR = ()

# Şartnamenin `x-required-capabilities` alanından çıkarıldı. Bunlar
# ÜYELİK değil PLAN kapısı: hesapta yoksa Canva 403 döner ve mesajı
# "requires one of capabilities [...]" biçimindedir.
# Birden fazla yazıyorsa BİRİ yeter (kaynak: docs/rest-apis/capabilities).
YETKINLIK_GEREKEN = {
    "/designs/{designId}/analytics": ("analytics",),
    "/image-to-design-imports": ("image_to_design_imports",),
    "/resizes": ("resize",),
}

AJAN = "lcarlie-jarvis/1.0"


class CanvaHatasi(Exception):
    """Sahibin okuyabileceği, Türkçe ve sebepli hata."""


# ─────────────────────────────────────────────────────────── kimlik
def _kimlik() -> tuple[str, str]:
    kimlik = os.environ.get("CANVA_CLIENT_ID")
    sir = os.environ.get("CANVA_CLIENT_SECRET")
    if not (kimlik and sir):
        try:
            from jarvis import providers
            cfg = providers.load_env()
            kimlik = kimlik or cfg.get("CANVA_CLIENT_ID")
            sir = sir or cfg.get("CANVA_CLIENT_SECRET")
        except Exception:  # noqa: BLE001
            pass
    if not (kimlik and sir):
        raise CanvaHatasi(
            "CANVA_CLIENT_ID / CANVA_CLIENT_SECRET yok. canva.dev geliştirici "
            "portalında entegrasyon oluşturup bu ikisini "
            "/opt/lcarlie/orchestrator/.env içine ekleyin.")
    return kimlik, sir


def _temel_yetki() -> str:
    k, s = _kimlik()
    return base64.b64encode(f"{k}:{s}".encode()).decode()


# ─────────────────────────────────────────────────────── yetkilendirme
def yetki_baglantisi(donus_url: str) -> str:
    """Sahibin bir kez tıklayacağı bağlantı. PKCE doğrulayıcısı saklanır."""
    dogrulayici = secrets.token_urlsafe(64)[:96]
    meydan = base64.urlsafe_b64encode(
        hashlib.sha256(dogrulayici.encode()).digest()).decode().rstrip("=")
    durum = secrets.token_urlsafe(24)

    # 🔴 Doğrulayıcı geri dönüşte LAZIM. Bellekte tutulamaz: geri dönüş
    # ayrı bir istek, hatta servis yeniden başlamış olabilir.
    GECICI.write_text(json.dumps({"dogrulayici": dogrulayici, "durum": durum,
                                  "donus": donus_url, "an": time.time()}),
                      encoding="utf-8")
    GECICI.chmod(0o600)

    kimlik, _ = _kimlik()
    p = urllib.parse.urlencode({
        "code_challenge": meydan,
        "code_challenge_method": "S256",
        "scope": KAPSAM,
        "response_type": "code",
        "client_id": kimlik,
        "state": durum,
        "redirect_uri": donus_url,
    })
    return f"{AUTH_UC}?{p}"


def _jeton_yaz(d: dict) -> None:
    d = dict(d)
    d["bitis"] = time.time() + float(d.get("expires_in") or 0) - 60
    JETON_YOL.parent.mkdir(parents=True, exist_ok=True)
    JETON_YOL.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    JETON_YOL.chmod(0o600)


def _jeton_oku() -> dict | None:
    if not JETON_YOL.is_file():
        return None
    try:
        return json.loads(JETON_YOL.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _token_istegi(govde: dict) -> dict:
    veri = urllib.parse.urlencode(govde).encode()
    istek = urllib.request.Request(
        TOKEN_UC, data=veri,
        headers={"Authorization": f"Basic {_temel_yetki()}",
                 "Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": AJAN})
    try:
        with urllib.request.urlopen(istek, timeout=30) as c:
            return json.loads(c.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        metin = ""
        try:
            metin = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise CanvaHatasi(f"jeton alınamadı (HTTP {e.code}): {metin}") from None


def geri_donus(kod: str, durum: str) -> dict:
    """Canva'dan dönen kodu jetona çevirir."""
    if not GECICI.is_file():
        raise CanvaHatasi("PKCE kaydı yok; yetkilendirmeye baştan başlayın")
    kayit = json.loads(GECICI.read_text(encoding="utf-8"))
    # 🔴 `state` KONTROL EDİLİR. Etmezsek başkasının başlattığı bir akışın
    # kodunu kabul edebiliriz (CSRF).
    if not secrets.compare_digest(str(durum), str(kayit.get("durum"))):
        raise CanvaHatasi("state uyuşmuyor — istek reddedildi")
    if time.time() - float(kayit.get("an") or 0) > 900:
        raise CanvaHatasi("yetkilendirme süresi doldu, baştan başlayın")

    kimlik, _ = _kimlik()
    d = _token_istegi({
        "grant_type": "authorization_code",
        "code": kod,
        "code_verifier": kayit["dogrulayici"],
        "client_id": kimlik,
        "redirect_uri": kayit["donus"],
    })
    _jeton_yaz(d)
    GECICI.unlink(missing_ok=True)
    return {"ok": True, "kapsam": d.get("scope", "")}


def _erisim_jetonu() -> str:
    d = _jeton_oku()
    if not d:
        raise CanvaHatasi("Canva'ya henüz yetki verilmedi — panelden bağlayın")
    if time.time() < float(d.get("bitis") or 0):
        return d["access_token"]
    if not d.get("refresh_token"):
        raise CanvaHatasi("yenileme jetonu yok — yeniden yetki verilmeli")
    yeni = _token_istegi({"grant_type": "refresh_token",
                          "refresh_token": d["refresh_token"]})
    # 🔴 Canva yenilemede YENİ bir refresh_token döndürebilir; eskisini
    # korursak bir sonraki yenileme patlar ve bağlantı sessizce ölür.
    if not yeni.get("refresh_token"):
        yeni["refresh_token"] = d["refresh_token"]
    _jeton_yaz(yeni)
    return yeni["access_token"]


# ────────────────────────────────────────────────────────────── API
def _cagir(yol: str, *, metot: str = "GET", govde: dict | None = None,
           ham: bytes | None = None, ek_baslik: dict | None = None) -> dict:
    _yetkinlik_kapisi(yol)
    for kalip in KURUMSAL_UCLAR:
        if kalip.split("{")[0] in yol:
            raise CanvaHatasi(
                f"{yol} ucu Canva Enterprise gerektiriyor; üyeliğimiz Pro. "
                "(Kaynak: resmî şartnamedeki <Availability> bloğu.)")
    baslik = {"Authorization": f"Bearer {_erisim_jetonu()}", "User-Agent": AJAN}
    veri = None
    if ham is not None:
        veri = ham
        baslik["Content-Type"] = "application/octet-stream"
    elif govde is not None:
        veri = json.dumps(govde).encode()
        baslik["Content-Type"] = "application/json"
    baslik.update(ek_baslik or {})

    istek = urllib.request.Request(f"{API}{yol}", data=veri, headers=baslik,
                                   method=metot)
    try:
        with urllib.request.urlopen(istek, timeout=120) as c:
            gelen = c.read().decode("utf-8")
            return json.loads(gelen) if gelen else {}
    except urllib.error.HTTPError as e:
        metin = ""
        try:
            metin = e.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001
            pass
        if e.code == 403 and "capabilities" in metin:
            raise CanvaHatasi(
                f"{metot} {yol}: hesabın planı bu ucu kaldırmıyor. "
                f"Canva'nın yanıtı: {metin}") from None
        raise CanvaHatasi(f"{metot} {yol} → HTTP {e.code}: {metin}") from None


def varlik_yukle(dosya: Path, ad: str | None = None) -> dict:
    """Dosyayı Canva kitaplığına yükler — HERKESE AÇIK URL GEREKMEZ.

    🔴 BU FONKSİYON İÇİN KENDİ ENTEGRASYONUMUZU KURDUK. Hazır bağlayıcı
    yalnız URL'den yükleyebiliyordu; ürün kesimimizi internete açmadan
    Canva'ya sokmanın başka yolu yoktu.
    """
    dosya = Path(dosya)
    if not dosya.is_file():
        raise CanvaHatasi(f"dosya yok: {dosya}")
    # Canva sınırı: ad en fazla 50 karakter (kodlanmamış hâliyle).
    ad = (ad or dosya.stem)[:50]
    b64 = base64.b64encode(ad.encode("utf-8")).decode()
    is_ = _cagir("/asset-uploads", metot="POST", ham=dosya.read_bytes(),
                 ek_baslik={"Asset-Upload-Metadata":
                            json.dumps({"name_base64": b64})})
    return _is_bekle(f"/asset-uploads/{is_['job']['id']}", "asset")


def _is_bekle(yol: str, anahtar: str, azami_sn: int = 180) -> dict:
    """Canva'nın asenkron işlerini bekler (yükleme, dışa aktarma)."""
    basla = time.time()
    while time.time() - basla < azami_sn:
        d = _cagir(yol)
        is_ = d.get("job") or {}
        durum = is_.get("status")
        if durum == "success":
            # 🔴 ANAHTAR ADAYLARI. Sonuç `job.result` altında ve alan adı
            # tekil/çoğul değişebiliyor (image-to-design → "design",
            # export → "urls"). Ölçülmedik bir adı tahmin etmek yerine
            # makul adayları sırayla deniyoruz.
            sonuc = is_.get("result")
            sonuc = sonuc if isinstance(sonuc, dict) else is_
            for aday in (anahtar, anahtar.rstrip("s"), anahtar + "s"):
                if aday in sonuc:
                    return sonuc[aday]
            # 🔴 SESSİZCE YANLIŞ VERİ DÖNDÜRME. Eskiden burada `is_`
            # dönüyordu; içindeki `id` iş kimliğiydi, tasarım kimliği
            # sanılıp sonraki çağrılar "not_found" veriyordu.
            raise CanvaHatasi(
                f"iş bitti ama '{anahtar}' alanı yok. Gelen alanlar: "
                f"{sorted(sonuc)}. Şartname değişmiş olabilir.")
        if durum == "failed":
            raise CanvaHatasi(f"iş başarısız: {is_.get('error')}")
        time.sleep(2)
    raise CanvaHatasi(f"iş {azami_sn} saniyede bitmedi: {yol}")


def tasarim_kopyala(tasarim_id: str, baslik: str | None = None) -> dict:
    # 🔴 `type` ŞART. Şartname: type yoksa istek `type_and_asset` sayılır
    # ve design_id dikkate ALINMAZ -- hata da vermez, yanlış iş yapar.
    govde: dict[str, Any] = {"type": "design", "design_id": tasarim_id}
    if baslik:
        govde["title"] = baslik[:255]
    return _cagir("/designs", metot="POST", govde=govde)


def disa_aktar(tasarim_id: str, tur: str = "jpg", kalite: int = 90) -> list[str]:
    bicim: dict[str, Any] = {"type": tur}
    if tur == "jpg":
        bicim["quality"] = kalite
    is_ = _cagir("/exports", metot="POST",
                 govde={"design_id": tasarim_id, "format": bicim})
    sonuc = _is_bekle(f"/exports/{is_['job']['id']}", "urls")
    return sonuc if isinstance(sonuc, list) else (sonuc.get("urls") or [])


def durum() -> dict:
    """Panel için: bağlı mıyız, jeton ne zaman biter."""
    d = _jeton_oku()
    if not d:
        return {"bagli": False, "sebep": "yetki verilmedi"}
    kalan = float(d.get("bitis") or 0) - time.time()
    return {
        "bagli": True,
        "kapsam": d.get("scope", ""),
        "erisim_kalan_sn": int(kalan),
        "yenilenebilir": bool(d.get("refresh_token")),
        "yetkinlikler": _YETKINLIK_ONBELLEK,
    }

# ═══════════════════════════════════════════ şartnameden çıkan yetenekler

_YETKINLIK_ONBELLEK: list[str] | None = None


def _yetkinlik_kapisi(yol: str) -> None:
    """Hesabın planı bu ucu kaldırmıyorsa çağrıyı yapmadan söyler."""
    if _YETKINLIK_ONBELLEK is None:
        return              # bilmiyoruz; engellemek tahmin olurdu
    for kalip, gerekli in YETKINLIK_GEREKEN.items():
        if kalip.split("{")[0] in yol:
            if not set(gerekli) & set(_YETKINLIK_ONBELLEK):
                raise CanvaHatasi(
                    f"{yol} ucu şu yetkinliklerden birini istiyor: "
                    f"{', '.join(gerekli)} — hesabın planında yok. "
                    "(Kaynak: şartnamedeki x-required-capabilities + "
                    "/users/me/capabilities yanıtı.)")
            return


def yetenekler(tazele: bool = False) -> list[str]:
    """Hesabın NE YAPABİLDİĞİNİ Canva'ya sorar; tahmin etmeye son.

    GET /v1/users/me/capabilities. Pro mu Enterprise mi olduğumuzu
    belgeden değil hesabın kendisinden öğrenmenin tek yolu bu.
    """
    global _YETKINLIK_ONBELLEK
    if _YETKINLIK_ONBELLEK is not None and not tazele:
        return _YETKINLIK_ONBELLEK
    d = _cagir("/users/me/capabilities")
    _YETKINLIK_ONBELLEK = d.get("capabilities") or []
    return _YETKINLIK_ONBELLEK


def olcekle(tasarim_id: str, en: int, boy: int,
            baslik: str | None = None) -> dict:
    """Tasarımı başka bir ölçüye taşır. Tek kreatif -> feed/story/reels.

    Instagram: feed 1080x1350 (4:5), kare 1080x1080, story/reels
    1080x1920. Şartname sınırı: her kenar 40-8000 px, alan ≤ 25 MP.
    """
    if not (40 <= en <= 8000 and 40 <= boy <= 8000):
        raise CanvaHatasi(f"ölçü sınır dışı: {en}x{boy} (40-8000 px)")
    if en * boy > 25_000_000:
        raise CanvaHatasi(f"alan çok büyük: {en * boy} px² (en çok 25 MP)")
    govde: dict[str, Any] = {
        "design_id": tasarim_id,
        "design_type": {"type": "custom", "width": en, "height": boy},
    }
    if baslik:
        govde["title"] = baslik[:255]
    is_ = _cagir("/resizes", metot="POST", govde=govde)
    return _is_bekle(f"/resizes/{is_['job']['id']}", "design")


def gorselden_tasarim(varlik_id: str, baslik: str) -> dict:
    """Bizim ürettiğimiz JPG'yi DÜZENLENEBİLİR Canva tasarımına çevirir.

    Asıl kazanç bu: kompozit çıktımız Canva'da düz bir resim değil,
    katmanları oynatılabilir bir tasarım olarak açılır. Önce
    varlik_yukle() ile asset_id alınır.

    ⚠ Şartnamede önizleme (preview) işaretli: habersiz değişebilir.
    """
    is_ = _cagir("/image-to-design-imports", metot="POST",
                 govde={"image": {"asset_id": varlik_id},
                        "title": baslik[:255]})
    return _is_bekle(f"/image-to-design-imports/{is_['job']['id']}", "designs")


def yorum_yaz(tasarim_id: str, metin: str) -> dict:
    """Sahibin itirazını TASARIMIN ÜSTÜNE yazar.

    🔴 Bu, kreatif_itiraz zincirinin eksik halkasıydı: itiraz bizim
    veritabanımızda duruyor ama tasarımcı Canva'ya baktığında görmüyor.
    İnsan beyanını taşıdığı için metin OLDUĞU GİBİ gider, özetlenmez.
    """
    metin = (metin or "").strip()
    if not metin:
        raise CanvaHatasi("boş yorum yazılmaz")
    return _cagir(f"/designs/{tasarim_id}/comments", metot="POST",
                  govde={"message_plaintext": metin[:2000]})


def sayfalar(tasarim_id: str, adet: int = 10) -> list[dict]:
    """Tasarımın sayfalarını okur (⚠ önizleme uç)."""
    d = _cagir(f"/designs/{tasarim_id}/pages?limit={min(adet, 100)}")
    return d.get("items") or []
