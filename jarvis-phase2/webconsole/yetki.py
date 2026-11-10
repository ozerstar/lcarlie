"""Rol bazlı erişim: hangi rol hangi adrese ulaşabilir.

🔴 VARSAYILAN KAPALI. OFİS rolü yalnız aşağıda adıyla yazılmış adreslere
ulaşır. Panele sonradan eklenen her yeni uç ofise KAPALI doğar; açmak için
buraya bilerek yazılması gerekir. Tersi (açık doğup sonradan kapatmak),
unutulan her ucun ofise sızması demekti.

Kapı menüde değil SUNUCUDA: sekmeyi gizlemek adres çubuğuna yazılan isteği
durdurmaz.

Neden Jarvis sohbeti kapalı: Jarvis şirketin bütün verisini okur. Sohbet açık
olsaydı kapatılan her ekranın içeriği "geçen ay ne harcadık?" diye sorularak
alınabilirdi.
"""
from __future__ import annotations

import auth

# Statik dosyalar (html/js/css/görsel) veri taşımaz; veri hep /api/ ile gelir.
# Ama aşağıdaki önekler oturumla korunan VERİ dosyaları sunar -- statik değiller.
# /karo/ (saha harita karoları) ve /katalog-gorsel/ (ürün görselleri) bilerek
# açık: saha haritası ve cari ürün seçimi bunlarsız çalışmaz, gizli veri taşımazlar.
OFIS_KAPALI_ONEKLER = (
    "/kreatif/", "/tarayici/", "/ig-foy/", "/katalog-pdf/", "/gonderi-gorsel/",
    "/etiket/", "/canva/", "/google/", "/messenger-pilot",
)

OFIS_GET = frozenset({
    "/api/session",
    # Saha: hedef listesi, filtreler. Konum ekranları (/api/saha/konum*) YOK:
    # çalışan konumu kişisel veridir, yalnız yönetici görür.
    "/api/saha", "/api/saha/filtreler",
    # Cari: her çağrı oturumun kendi defterine bağlı (owner = kullanıcı adı),
    # yani ofis yalnız kendi açtığı carileri görür.
    "/api/cari/overview", "/api/cari/accounts", "/api/cari/statement",
    "/api/cari/drafts", "/api/cari/documents", "/api/cari/documents/content",
    "/api/cari/export",
    # Cari satış hareketinde ürün seçmek için. Maliyet/marj içermez; bayi
    # satış fiyatlarını içerir (sahada zaten söylenen fiyatlar).
    "/api/katalog",
    # 3D ofis ekranı. /api/panel/holding (ciro, marj) BİLEREK yok.
    "/api/office/events", "/api/office/activity", "/api/orchestration",
    "/api/panel/ofis", "/api/panel/ekip", "/api/panel/ajanlar",
    # Kendi cihazları ve bildirimleri.
    "/api/devices", "/api/push/config",
})

OFIS_POST = frozenset({
    "/api/logout", "/api/account/password",
    "/api/saha/ziyaret", "/api/saha/bilgi", "/api/saha/nokta", "/api/saha/rota",
    # Cari: kart açar/düzeltir, hareketi TASLAK olarak girer. Kesinleştirme
    # (drafts/post, entries), indirim, düzeltme, ters kayıt ve belge onayı
    # YÖNETİCİDE -- taslak bakiyeye işlemeden önce yönetici görür.
    "/api/cari/accounts", "/api/cari/accounts/update", "/api/cari/preview",
    "/api/cari/drafts/create", "/api/cari/drafts/update",
    "/api/cari/documents/upload",
    "/api/devices/revoke", "/api/devices/revoke-all",
    "/api/push/subscribe", "/api/push/unsubscribe",
})


def izinli(rol: str | None, yontem: str, yol: str) -> bool:
    if rol == auth.ROLE_ADMIN:
        return True
    if rol != auth.ROLE_OFIS:
        return False
    if not yol.startswith("/api/"):
        return not yol.startswith(OFIS_KAPALI_ONEKLER)
    return yol in (OFIS_GET if yontem == "GET" else OFIS_POST)


def gorunum(rol: str | None) -> dict:
    """Ön yüzün menüyü kurması için. Kapı bu değil; kapı izinli()."""
    if rol == auth.ROLE_ADMIN:
        return {"rol": rol, "sekmeler": None}
    return {"rol": rol, "sekmeler": ["saha"], "sayfalar": ["cari", "ofis"]}
