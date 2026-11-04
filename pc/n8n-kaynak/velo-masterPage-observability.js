// =============================================================================
// L'CARLIE - GENERIC OBSERVABILITY LAYER  (Velo / masterPage.js)  CR-017
//
// 🔴 DURUM: YAZILDI, DAGITILMADI. Yayin icin iki karar bekliyor (raporda).
//
// AMAC: Wix native entegrasyonunun URETMEDIGI davranis event'lerini, URUN
//       BAGIMSIZ ve TICARETE DOKUNMADAN olcmek.
//
// 🔴 KURALLAR (CR-017 - bu dosyanin her satiri bunlara uyar):
//    · DOM selector / click scraping YOK
//    · Urun adi / slug / buton ID HARD-CODE YOK
//    · Native Wix event'i varsa DUPLICATE URETILMEZ
//    · Yalniz GERCEK enstrumantasyon acigi doldurulur
//    · Ticaret davranisi DEGISTIRILMEZ - sadece olcum eklenir
//    · Eksik alan UYDURULMAZ
//
// 🔴 NEDEN RUNTIME FEATURE-DETECTION VAR:
//    Velo frontend cart-event API'sinin bu sitede (Stores Catalog V1, klasik
//    Editor) hangi imzayla bulundugunu DOKUMANTASYONDAN DOGRULAYAMADIM.
//    Bu oturumda iki kez varsayimdan yanildim; bu yuzden kod hicbir API'nin
//    varligini VARSAYMIYOR. Her yetenek once kontrol edilir, yoksa sessizce
//    devre disi kalir ve NEDENI konsola yazilir. Boylece eksik API sitede
//    HATA URETMEZ - yalnizca o event olculmez (ve olculmedigi bilinir).
//
// 🔴 GERI ALMA: OLCUM_ACIK = false yapmak TEK adimda her seyi durdurur.
//    Ayrica tum kod try/catch icinde; bir hata magazayi ETKILEYEMEZ.
// =============================================================================

import wixLocationFrontend from 'wix-location-frontend';
import wixWindowFrontend from 'wix-window-frontend';

// --- KILL SWITCH -------------------------------------------------------------
const OLCUM_ACIK = true;

// 🔴 NATIVE WIX'IN ZATEN GONDERDIGI EVENT'LER - BURADAN URETILMEZ.
//    17.09.2026'da tarayicida olculdu. Bu liste degisirse once OLCULMELI;
//    tahminle guncellenmemeli. Duplicate uretmemek bu listeye baglidir.
const NATIVE_GONDERILEN = ['page_view', 'view_item_native_product_page'];

function log(...a) { try { console.log('[LCARLIE-OBS]', ...a); } catch (e) {} }

// --- dataLayer'a KANONIK event --------------------------------------------
// 🔴 Eksik alan UYDURULMAZ: undefined/null alanlar payload'a HIC KONMAZ.
//    Sifir ile "bilinmiyor" ayni sey degildir.
function olcumGonder(eventAdi, veri) {
  if (!OLCUM_ACIK) return;
  try {
    window.dataLayer = window.dataLayer || [];
    const p = { event: eventAdi };
    if (veri && veri.currency != null) p.currency = veri.currency;
    if (veri && veri.value != null) p.value = veri.value;
    if (veri && veri.transaction_id != null) p.transaction_id = veri.transaction_id;
    if (veri && Array.isArray(veri.items) && veri.items.length) {
      p.items = veri.items.map(function (it) {
        const o = {};
        if (it.item_id != null) o.item_id = it.item_id;
        if (it.item_name != null) o.item_name = it.item_name;
        if (it.quantity != null) o.quantity = it.quantity;
        if (it.price != null) o.price = it.price;
        return o;
      });
    }
    window.dataLayer.push(p);
    log('gonderildi', eventAdi, p);
  } catch (e) { log('gonderim hatasi', e); }
}

// --- Wix line item -> kanonik item ------------------------------------------
// 🔴 URUN KIMLIGI ID ILE: productId/catalogItemId. Urun ADI yalniz
//    item_name olarak tasinir, ESLESTIRME ANAHTARI olarak ASLA kullanilmaz.
function itemCevir(li) {
  if (!li) return null;
  const o = {};
  const id = li.productId
          || (li.catalogReference && li.catalogReference.catalogItemId)
          || li._id || li.id;
  if (id != null) o.item_id = String(id);

  const ad = (li.name && (li.name.original || li.name.translated)) || li.name || li.productName;
  if (ad != null && typeof ad === 'string') o.item_name = ad;

  const adet = (li.quantityInfo && li.quantityInfo.requestedQuantity) || li.quantity;
  if (adet != null) o.quantity = Number(adet);

  const fiyat = (li.pricing && li.pricing.unitPrice && li.pricing.unitPrice.amount)
             || (li.price && li.price.amount) || li.price;
  if (fiyat != null && !isNaN(Number(fiyat))) o.price = Number(fiyat);

  return (o.item_id || o.item_name) ? o : null;
}

function satirlariAl(cart) {
  if (!cart) return [];
  return cart.lineItems || cart.items || [];
}
function paraBirimi(cart) {
  try { return (cart && (cart.currency || (cart.subtotal && cart.subtotal.currency))) || undefined; }
  catch (e) { return undefined; }
}

// --- CART ANLIK GORUNTUSU (delta icin) --------------------------------------
// 🔴 add_to_cart, CART DURUM DEGISIMINDEN turetilir - tiklamadan DEGIL.
//    Anahtar: line item kimligi. Miktar ARTISI kadar event uretilir;
//    AZALIS ve SILME add_to_cart DEGILDIR ve hicbir event uretmez.
let oncekiSepet = null;

function sepetHaritasi(cart) {
  const m = {};
  satirlariAl(cart).forEach(function (li) {
    const it = itemCevir(li);
    if (!it || !it.item_id) return;
    const anahtar = String(li._id || li.id || it.item_id);
    m[anahtar] = { item: it, adet: Number(it.quantity || 0) };
  });
  return m;
}

function sepetDegisiminiIsle(yeniCart) {
  try {
    const yeni = sepetHaritasi(yeniCart);
    if (oncekiSepet === null) { oncekiSepet = yeni; return; }   // ilk okuma: temel

    const eklenen = [];
    Object.keys(yeni).forEach(function (k) {
      const oncekiAdet = oncekiSepet[k] ? oncekiSepet[k].adet : 0;
      const fark = yeni[k].adet - oncekiAdet;
      if (fark > 0) {
        const it = Object.assign({}, yeni[k].item, { quantity: fark });  // GERCEK DELTA
        eklenen.push(it);
      }
      // fark <= 0 -> azalis/degisiklik yok: add_to_cart DEGILDIR, event YOK
    });

    oncekiSepet = yeni;

    if (eklenen.length) {
      const veri = { items: eklenen, currency: paraBirimi(yeniCart) };
      const toplam = eklenen.reduce(function (s, it) {
        return (it.price != null && it.quantity != null) ? s + it.price * it.quantity : s;
      }, 0);
      // 🔴 value yalniz TUM kalemlerin fiyati biliniyorsa yazilir; kismi
      //    toplam yaniltici olurdu.
      const hepsiFiyatli = eklenen.every(function (it) { return it.price != null; });
      if (hepsiFiyatli && toplam > 0) veri.value = Number(toplam.toFixed(2));
      olcumGonder('add_to_cart', veri);
    }
  } catch (e) { log('sepet delta hatasi', e); }
}

// --- SAYFA ROLU  (registry'den, slug TAHMINI DEGIL) -------------------------
// 🔴 SAYFA -> URUN eslesmesi Wix CMS koleksiyonundan okunur (SayfaUrunKayit):
//      sayfaYolu (text) · urunId (text) · sayfaRolu (text)
//    Koleksiyon YOKSA ozel landing view_item URETILMEZ. Slug'a bakarak
//    urun TAHMIN EDILMEZ - CR-017 bunu acikca yasakliyor.
async function sayfaKaydiniAl(yol) {
  try {
    const wixData = await import('wix-data');
    const r = await wixData.query('SayfaUrunKayit').eq('sayfaYolu', yol).limit(1).find();
    return (r && r.items && r.items[0]) || null;
  } catch (e) {
    log('sayfa registry okunamadi (koleksiyon yok olabilir) - ozel landing view_item URETILMEYECEK', e && e.message);
    return null;
  }
}

// --- CUSTOM LANDING view_item ------------------------------------------------
// 🔴 NATIVE URUN SAYFASINDA CALISMAZ: orada Wix zaten view_item gonderiyor
//    (17.09.2026'da olculdu) ve duplicate uretmek YASAK.
async function ozelLandingViewItem() {
  try {
    const yol = wixLocationFrontend.path ? '/' + wixLocationFrontend.path.join('/') : '';
    const kayit = await sayfaKaydiniAl(yol);
    if (!kayit || !kayit.urunId) return;
    if (kayit.sayfaRolu === 'NATIVE_URUN') return;   // native = Wix gonderiyor

    const wixData = await import('wix-data');
    const u = await wixData.get('Stores/Products', kayit.urunId);
    if (!u) return;

    const it = {};
    it.item_id = String(kayit.urunId);
    if (u.name != null) it.item_name = u.name;
    it.quantity = 1;
    if (u.discountedPrice != null) it.price = Number(u.discountedPrice);
    else if (u.price != null) it.price = Number(u.price);

    const veri = { items: [it] };
    if (it.price != null) veri.value = it.price;
    if (u.currency != null) veri.currency = u.currency;
    olcumGonder('view_item', veri);
  } catch (e) { log('ozel landing view_item hatasi', e); }
}

// --- view_cart  (GERCEK sepet goruntulemesi) --------------------------------
// 🔴 "Sepette urun var" YETMEZ - sepetin GORUNTULENMESI gerekir.
async function sepetGoruntulendi(cart) {
  try {
    const items = satirlariAl(cart).map(itemCevir).filter(Boolean);
    if (!items.length) return;                       // bos sepet goruntulemesi event degil
    const veri = { items: items, currency: paraBirimi(cart) };
    const hepsiFiyatli = items.every(function (it) { return it.price != null && it.quantity != null; });
    if (hepsiFiyatli) {
      const t = items.reduce(function (s, it) { return s + it.price * it.quantity; }, 0);
      if (t > 0) veri.value = Number(t.toFixed(2));
    }
    olcumGonder('view_cart', veri);
  } catch (e) { log('view_cart hatasi', e); }
}

// --- begin_checkout  (GERCEK checkout baslangici) ---------------------------
// 🔴 BUTON TIKLAMASI TAHMINI KULLANILMAZ. Odeme sayfasina ULASMAK
//    checkout'un baslamasidir; sepet icerigi gercek veriden okunur.
async function checkoutBasladi(cart) {
  try {
    const items = satirlariAl(cart).map(itemCevir).filter(Boolean);
    if (!items.length) return;
    const veri = { items: items, currency: paraBirimi(cart) };
    const hepsiFiyatli = items.every(function (it) { return it.price != null && it.quantity != null; });
    if (hepsiFiyatli) {
      const t = items.reduce(function (s, it) { return s + it.price * it.quantity; }, 0);
      if (t > 0) veri.value = Number(t.toFixed(2));
    }
    olcumGonder('begin_checkout', veri);
  } catch (e) { log('begin_checkout hatasi', e); }
}

// --- purchase  -> BILEREK UYGULANMADI ---------------------------------------
// 🔴 CR-017 kurali: "Native Wix event varsa duplicate uretme."
//    Wix'in purchase gonderip gondermedigi OLCULMEDI (gercek siparis
//    gerektirir). Olcmeden eklemek CIFT CIRO riski yaratir - GA4 tarafinda
//    iki purchase, iki transaction_id gorunur ve mutabakat bozulur.
//    Once olculecek, sonra gerekiyorsa eklenecek.
//    Ayrica: purchase ASLA tiklamadan uretilmeyecek; kaynak gercek Wix
//    order/checkout tamamlanmasi olacak ve transaction_id ZORUNLU.

// =============================================================================
// BAGLAMA  -  her yetenek once KONTROL edilir, varsayilmaz
// =============================================================================
$w.onReady(function () {
  if (!OLCUM_ACIK) { log('olcum KAPALI'); return; }

  (async function () {
    try {
      let ecom = null;
      try { ecom = await import('wix-ecom-frontend'); }
      catch (e) { log('wix-ecom-frontend YOK - sepet event-leri olculemeyecek'); }

      // 1) Sepet degisimi -> add_to_cart
      // 🔴 API imzasi dogrulanmadigi icin bilinen adlar TEK TEK denenir;
      //    hicbiri yoksa sessizce devre disi kalir ve NEDENI yazilir.
      let baglandi = false;
      if (ecom) {
        const adaylar = ['onCartChange', 'onCartChanged', 'cart'];
        for (const ad of adaylar) {
          try {
            if (ad === 'cart' && ecom.cart && typeof ecom.cart.onChange === 'function') {
              ecom.cart.onChange(sepetDegisiminiIsle); baglandi = true; break;
            }
            if (typeof ecom[ad] === 'function') {
              ecom[ad](sepetDegisiminiIsle); baglandi = true; break;
            }
          } catch (e) { /* sonraki adaya gec */ }
        }
      }
      if (!baglandi) log('sepet degisim olayi BAGLANAMADI - add_to_cart OLCULMEYECEK (uydurma event URETILMEZ)');

      // 2) Sayfa roluyle view_cart / begin_checkout / ozel landing view_item
      const yol = wixLocationFrontend.path ? '/' + wixLocationFrontend.path.join('/') : '/';
      const kayit = await sayfaKaydiniAl(yol);
      const rol = kayit && kayit.sayfaRolu;

      let sepet = null;
      if (ecom && typeof ecom.getCurrentCart === 'function') {
        try { sepet = await ecom.getCurrentCart(); } catch (e) { log('sepet okunamadi', e && e.message); }
      }
      if (sepet) { oncekiSepet = sepetHaritasi(sepet); }   // delta icin temel

      if (rol === 'SEPET' && sepet) await sepetGoruntulendi(sepet);
      if (rol === 'ODEME' && sepet) await checkoutBasladi(sepet);
      if (rol === 'OZEL_LANDING' || rol === 'KAMPANYA_LANDING') await ozelLandingViewItem();

      log('hazir · sayfa rolu:', rol || '(kayitli degil)', '· sepet olayi:', baglandi);
    } catch (e) { log('baslatma hatasi', e); }
  })();
});
