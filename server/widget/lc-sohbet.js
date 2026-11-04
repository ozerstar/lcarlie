/* =====================================================================
   L'CARLIE - Site Canli Sohbet Widget'i
   Kaynak : Masaustu\01 LCARLIE\SITE-SOHBET-WIDGET.html
   Uretim : widget-yayinla.ps1  (14.09.2026 23:47)
   Adres  : https://n8n.lcarlie.shop/lc-sohbet.js

   Wix tarafinda SADECE su satir durur:
     <script src="https://n8n.lcarlie.shop/lc-sohbet.js" defer></script>
   ===================================================================== */
(function () {
  // 🔴 "Bir kez kuruldu" bayragi TEK BASINA YETMEZ.
  // Wix sayfa gecislerinde govdeyi yenileyebiliyor: balon DOM'dan silinir
  // ama JS baglami yasamaya devam eder. Duz bayrak kullanilirsa kod
  // "zaten kurdum" deyip geri doner ve balon BIR DAHA GELMEZ.
  // Bu yuzden bayrak yerine ELEMANIN VARLIGI kontrol edilir; ayrica
  // sayfa degisimlerine karsi periyodik olarak yeniden kurulur.
  var UC = 'https://n8n.lcarlie.shop/webhook/sohbet';

  // ---- Stil -----------------------------------------------------------
  var stil = document.createElement('style');
  stil.textContent = [
    '#lc-sohbet,#lc-sohbet *{box-sizing:border-box}',
    '#lc-sohbet{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;',
    '  position:fixed;right:16px;bottom:16px;z-index:2147483000}',
    '#lc-btn{width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;',
    '  background:#0f172a;color:#fff;font-size:24px;line-height:1;',
    '  box-shadow:0 8px 24px rgba(15,23,42,.28);transition:transform .15s ease}',
    '#lc-btn:hover{transform:scale(1.06)}',
    // 🔴 dvh: iOS/Android'de klavye acilinca 100vh KUCULMEZ; girdi ve
    // Gonder butonu klavyenin arkasinda kalir. dvh gercek gorunur alani verir.
    '#lc-pnl{display:none;flex-direction:column;',
    '  width:min(360px,calc(100vw - 32px));height:min(520px,calc(100vh - 100px));',
    '  height:min(520px,calc(100dvh - 100px));',
    '  background:#fff;border:1px solid #e2e8f0;border-radius:14px;',
    '  box-shadow:0 20px 50px rgba(15,23,42,.22);overflow:hidden}',
    '#lc-pnl.acik{display:flex}',
    // Dar ekranda panel tam ekran - 360px panelde urun adi + fiyat sigmiyordu
    '@media (max-width:640px){',
    '  #lc-sohbet{right:10px;bottom:calc(10px + env(safe-area-inset-bottom))}',
    '  #lc-pnl{width:calc(100vw - 20px);height:calc(100dvh - 80px)}',
    '  .lc-m{max-width:95%}',
    '}',
    '#lc-bas{background:#0f172a;color:#fff;padding:.85rem 1rem;',
    '  display:flex;align-items:center;justify-content:space-between}',
    '#lc-bas b{font-size:.95rem;letter-spacing:.04em}',
    '#lc-bas small{display:block;opacity:.75;font-size:.72rem;margin-top:2px}',
    // 🔴 Dokunma hedefi en az 44px olmali - 20x20 px cikis dugmesine
    // mobilde 2-3 kez iskalayarak basiliyordu.
    '#lc-kapat{background:none;border:0;color:#fff;font-size:20px;cursor:pointer;',
    '  opacity:.8;padding:.4rem .6rem;margin:-.4rem -.4rem;line-height:1}',
    // overscroll-behavior: sohbetin sonuna gelince ARKADAKI SAYFA kayiyordu
    '#lc-akis{flex:1;overflow-y:auto;padding:.9rem;background:#f8fafc;',
    '  overscroll-behavior:contain}',
    '.lc-m{max-width:85%;padding:.55rem .8rem;border-radius:12px;margin-bottom:.6rem;',
    '  font-size:.875rem;line-height:1.45;white-space:pre-wrap;word-break:break-word}',
    '.lc-bot{background:#fff;border:1px solid #e2e8f0;color:#0f172a}',
    '.lc-ben{background:#0f172a;color:#fff;margin-left:auto}',
    '.lc-bot a{color:#1d4ed8}',
    // Urun satiri: ad solda, fiyat sagda rozet halinde
    '.lc-urun{display:flex;align-items:baseline;justify-content:space-between;',
    '  gap:.5rem;padding:.45rem 0;border-bottom:1px solid #f1f5f9}',
    '.lc-urun:last-of-type{border-bottom:0}',
    '.lc-urun-ad{font-weight:600;font-size:.86rem;line-height:1.35}',
    '.lc-urun-fiyat{white-space:nowrap;font-size:.82rem;font-weight:700;color:#0f172a;',
    '  background:#f1f5f9;border-radius:6px;padding:.1rem .45rem}',
    '.lc-adim{font-size:.8rem;color:#64748b;margin-right:.3rem}',
    // Baglantilar cirkin URL yerine BUTON olarak cizilir
    '.lc-btnlar{display:flex;flex-direction:column;gap:.4rem;margin-top:.6rem}',
    '.lc-cta{display:block;text-align:center;text-decoration:none;',
    '  padding:.55rem .7rem;border-radius:9px;font-size:.84rem;font-weight:600}',
    // 🔴 '.lc-bot a' ozgullugu (0,1,1) '.lc-cta-ana'dan (0,1,0) YUKSEK.
    // Bu yuzden koyu butonlarin yazisi mavi kaliyordu (okunmuyordu).
    // Buton kurallari da '.lc-bot a...' ile yazilarak ayni duzeye cikarildi.
    '.lc-bot a.lc-cta-ana{background:#0f172a;color:#fff}',
    '.lc-bot a.lc-cta-ikincil{background:#fff;color:#0f172a;border:1px solid #cbd5e1}',
    '.lc-cta:hover{opacity:.9}',
    '.lc-uyari{font-size:.72rem;color:#64748b;line-height:1.4;margin-top:.5rem;',
    '  padding-top:.5rem;border-top:1px solid #f1f5f9}',
    // Hizli cevap secenekleri - musteri yazmadan tiklayabilsin
    '.lc-hizli{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.6rem}',
    '.lc-hizli button{background:#fff;border:1px solid #cbd5e1;color:#0f172a;',
    '  border-radius:999px;padding:.5rem .8rem;font-size:.8rem;cursor:pointer;',
    '  font-family:inherit;line-height:1.2;min-height:40px}',
    '.lc-hizli button:hover:not(:disabled){background:#0f172a;color:#fff;border-color:#0f172a}',
    // Secilmeyen secenekler SILINMEZ, soluklastirilir - musteri yanlis
    // butona basinca digerleri kayboluyordu ve geri getirmenin yolu yoktu.
    '.lc-hizli button:disabled{opacity:.4;cursor:default}',
    // 🔴 Odak halkasi: outline:none erisilebilirligi kiriyordu
    '#lc-sohbet :focus-visible{outline:2px solid #0f172a;outline-offset:2px}',
    '#lc-bas :focus-visible{outline-color:#fff}',
    '#lc-alt{display:flex;gap:.5rem;padding:.7rem;border-top:1px solid #e2e8f0;background:#fff}',
    // 🔴 16px SART: iOS Safari 16px'in altindaki girdiye odaklaninca
    // TUM SAYFAYI yakinlastiriyor ve musteri geri cikamiyor.
    '#lc-girdi{flex:1;border:1px solid #cbd5e1;border-radius:9px;padding:.5rem .7rem;',
    '  font-size:16px;font-family:inherit}',
    '#lc-girdi:focus{border-color:#0f172a}',
    '#lc-girdi:disabled{background:#f8fafc;color:#94a3b8}',
    '#lc-gonder{border:0;background:#0f172a;color:#fff;border-radius:9px;',
    '  padding:0 .95rem;cursor:pointer;font-size:.875rem;font-weight:600}',
    '#lc-gonder:disabled{opacity:.45;cursor:default}',
    '.lc-yaz{color:#64748b;font-size:.8rem;padding:.2rem .3rem}'
  ].join('');

  // ---- Oturum kimligi (kisisel veri degil, sadece konusmayi surdurur) --
  var oturum;
  try {
    oturum = localStorage.getItem('lc_oturum');
    if (!oturum) {
      oturum = 'web-' + Math.random().toString(36).slice(2, 10);
      localStorage.setItem('lc_oturum', oturum);
    }
  } catch (e) {
    oturum = 'web-' + Math.random().toString(36).slice(2, 10);
  }

  // ---- Kabi olustur ---------------------------------------------------
  function kur() {
    if (!document.body) return;
    if (document.getElementById('lc-sohbet')) return;
    // Stil de silinmis olabilir - yoksa tekrar ekle
    if (!document.getElementById('lc-stil')) {
      stil.id = 'lc-stil';
      document.head.appendChild(stil);
    }

    var kok = document.createElement('div');
    kok.id = 'lc-sohbet';
    // 🔴 Alt baslikta YAPAY ZEKA oldugu acikca yaziyor.
    // Musteri insan sandigi icin kisisel/tibbi soru soruyordu; ayrica
    // saglik sorularini insana aktardigimiz icin bunu bilmesi gerek.
    // role="dialog" + aria-live: ekran okuyucu botun cevabini duymuyordu.
    kok.innerHTML =
      '<div id="lc-pnl" role="dialog" aria-modal="false" aria-label="L\'CARLIÉ sohbet">' +
        '<div id="lc-bas"><div><b>L\'CARLIÉ</b>' +
        '<small>Yapay zekâ asistan · 7/24</small></div>' +
        '<button id="lc-kapat" aria-label="Sohbeti kapat">×</button></div>' +
        '<div id="lc-akis" role="log" aria-live="polite" aria-atomic="false"></div>' +
        '<div id="lc-alt">' +
          '<input id="lc-girdi" placeholder="Mesajınızı yazın…" autocomplete="off" ' +
          'maxlength="1000" enterkeyhint="send" aria-label="Mesajınız">' +
          '<button id="lc-gonder">Gönder</button>' +
        '</div>' +
      '</div>' +
      '<button id="lc-btn" aria-label="Sohbeti aç" aria-expanded="false">💬</button>';
    document.body.appendChild(kok);

    var pnl = document.getElementById('lc-pnl');
    var btn = document.getElementById('lc-btn');
    var akis = document.getElementById('lc-akis');
    var girdi = document.getElementById('lc-girdi');
    var gonder = document.getElementById('lc-gonder');
    var basladi = false;

    // -------------------------------------------------------------------
    // MESAJ CIZIMI
    //
    // 🔴 Ajan TEK bir duz metin dondurur - WhatsApp gibi kanallar buton
    // cizemedigi icin bu dogru. Web'de ise ayni metin cirkin duruyordu:
    // "https://www.wixapis.com/ecom/v1/checkout-templates/d0ace880-..."
    // gibi bir baglanti musteri gozunde teknik ve guvensiz; kimse tiklamaz.
    //
    // Cozum SUNUM katmaninda: metin ayristirilir, baglantilar anlamli
    // etiketli BUTONLARA cevrilir, urun+fiyat satirlari hizalanir.
    // Ajanin cevabi DEGISTIRILMEZ, sadece daha iyi gosterilir.
    //
    // Guvenlik: sunucudan gelen metin HICBIR ZAMAN innerHTML'e verilmez;
    // her parca textContent ile yazilir.
    // -------------------------------------------------------------------
    // Buton etiketi. Urun sayfasi baglantilarinda URUN ADI kullanilir -
    // yoksa iki urunlu listede yan yana iki ayni etiket cikiyordu.
    function butonEtiketi(u, sonUrunAdi) {
      if (u.indexOf('checkout-template') !== -1) return ['🛒 Üçlü rutini tek seferde al', 'ana'];
      if (u.indexOf('/product-page/') !== -1) {
        return [sonUrunAdi ? sonUrunAdi + ' — incele ve sipariş ver'
                           : 'Ürünü incele ve sipariş ver', 'ana'];
      }
      if (/lcarlie\.shop\/?$/.test(u))           return ['Tüm ürünleri incele', 'ikincil'];
      return ['Bağlantıyı aç', 'ikincil'];
    }

    // Uzun urun adini butona sigacak hale getir
    function kisalt(s, n) {
      s = String(s).replace(/\s+/g, ' ').trim();
      return s.length > n ? s.slice(0, n - 1).trim() + '…' : s;
    }

    // Hizli cevap secenekleri: tiklaninca o metni mesaj olarak gonderir.
    // islev verilirse yollamak yerine o calisir ("Tekrar gönder" gibi).
    function hizliCevaplariCiz(kap, secenekler, islev) {
      if (!secenekler || !secenekler.length) return;
      var kutu = document.createElement('div');
      kutu.className = 'lc-hizli';
      secenekler.forEach(function (s) {
        var b = document.createElement('button');
        b.type = 'button';
        b.textContent = s;
        b.onclick = function () {
          // 🔴 Secenekler SILINMEZ, devre disi birakilir.
          // Once kutu.remove() vardi: musteri yanlis butona basinca
          // digerleri kaliciyla kayboluyor, geri getirmenin yolu olmuyordu.
          Array.prototype.forEach.call(kutu.querySelectorAll('button'),
            function (x) { x.disabled = true; });
          if (islev) islev(); else yolla(s);
        };
        kutu.appendChild(b);
      });
      kap.appendChild(kutu);
    }

    function botMesajiCiz(kap, metin) {
      var URL_RE = /(https?:\/\/[^\s]+)/g;
      var butonlar = [];          // {url, etiket, tur}
      var hizli = [];             // "▸ " ile baslayan satirlar
      var gorulen = {};
      var sonUrun = null;         // en son gorulen urun adi

      String(metin).split('\n').forEach(function (satir) {
        // 🔴 "▸ " ile baslayan satir HIZLI CEVAP secenegidir.
        // Ajan bunu tek bir duz metin olarak gonderir; WhatsApp'ta duz
        // yazi olarak okunur, web'de tiklanabilir butona donusur.
        var hz = satir.match(/^\s*▸\s*(.+?)\s*$/);
        if (hz) { hizli.push(hz[1]); return; }
        var urlVardi = false;
        var temiz = satir.replace(URL_RE, function (u) {
          urlVardi = true;
          var son = u.replace(/[.,;:]+$/, '');
          if (!gorulen[son]) {
            gorulen[son] = 1;
            var e = butonEtiketi(son, sonUrun);
            butonlar.push({ url: son, etiket: e[0], tur: e[1] });
          }
          return '';
        }).trim();

        // 🔴 URL silininince cumle ortasinda CIFT BOSLUK kaliyordu:
        // "Bu ürünü  adresinden sipariş verebilirsiniz" gibi.
        if (urlVardi) temiz = temiz.replace(/\s{2,}/g, ' ').trim();

        // 🔴 Baglanti cikarilinca geriye "Üç adımı tek seferde almak için:"
        // gibi BOSTA KALAN baslik kaliyordu. Butonun etiketi zaten bunu
        // soyluyor; iki kez yazmak kotu goruniyor.
        // Kisa kalinti da atilir - butonun etiketi ayni seyi soyluyor.
        if (urlVardi && (!temiz || /[:：]$/.test(temiz) || temiz.length < 25)) return;

        if (!temiz) return;

        // "1) Temizle — LUCIDERM ... · 1.200 TL"  /  "• DERMAGUARD ... · 1.200 TL"
        var m = temiz.match(/^(\d\)|•)?\s*(.+?)\s*[·]\s*([\d.,]+\s*TL.*)$/);
        if (m) {
          // Butonda kullanilmak uzere urun adini akilda tut.
          // "1) Temizle — LUCIDERM ..." -> tire sonrasi asil urun adi.
          var adTam = m[2].split('—').pop();
          sonUrun = kisalt(adTam, 34);
          var satirEl = document.createElement('div');
          satirEl.className = 'lc-urun';
          var sol = document.createElement('div');
          sol.className = 'lc-urun-ad';
          if (m[1]) {
            var ad = document.createElement('span');
            ad.className = 'lc-adim';
            ad.textContent = m[1];
            sol.appendChild(ad);
          }
          sol.appendChild(document.createTextNode(m[2]));
          var sag = document.createElement('span');
          sag.className = 'lc-urun-fiyat';
          sag.textContent = m[3];
          satirEl.appendChild(sol);
          satirEl.appendChild(sag);
          kap.appendChild(satirEl);
          return;
        }

        // Gunes koruyucu zorunlu ibareleri - kucuk ve soluk, ama GORUNUR
        var p = document.createElement('div');
        if (/Yeterli miktarda uygulanmaması|Aşırı güneş maruziyeti|%100 koruma/.test(temiz)) {
          p.className = 'lc-uyari';
        }
        p.textContent = temiz;
        kap.appendChild(p);
      });

      hizliCevaplariCiz(kap, hizli);

      if (butonlar.length) {
        var kutu = document.createElement('div');
        kutu.className = 'lc-btnlar';
        butonlar.forEach(function (b) {
          var a = document.createElement('a');
          a.className = 'lc-cta lc-cta-' + b.tur;
          a.href = b.url;
          a.target = '_blank';
          a.rel = 'noopener';
          a.textContent = b.etiket;
          kutu.appendChild(a);
        });
        kap.appendChild(kutu);
      }
    }

    // -------------------------------------------------------------------
    // KONUSMA GECMISI
    // 🔴 Wix sayfa gecisinde panel yeniden kuruluyor ve sohbet BOSALIYORDU.
    // Sunucu musteriId ile hatirladigi icin bot konusmaya devam ediyor ama
    // musteri kendi yazdiklarini goremiyor - "benim mesajlarimi kim gordu?"
    // Son 20 mesaj tarayicida saklanir; sunucuya ekstra veri gitmez.
    // -------------------------------------------------------------------
    var gecmis = [];
    function gecmisiKaydet() {
      try {
        localStorage.setItem('lc_gecmis', JSON.stringify(gecmis.slice(-20)));
        localStorage.setItem('lc_acik', pnl.classList.contains('acik') ? '1' : '0');
      } catch (e) {}
    }
    function gecmisiOku() {
      try { return JSON.parse(localStorage.getItem('lc_gecmis') || '[]'); }
      catch (e) { return []; }
    }

    function ekle(metin, kim, kaydetme) {
      var d = document.createElement('div');
      d.className = 'lc-m ' + (kim === 'ben' ? 'lc-ben' : 'lc-bot');
      if (kim === 'ben') d.textContent = metin;
      else botMesajiCiz(d, metin);
      akis.appendChild(d);
      // Uzun cevabin SONUNA degil BASINA kaydir - musteri bastan okusun
      if (kim === 'bot' && d.offsetHeight > akis.clientHeight * 0.6) {
        akis.scrollTop = d.offsetTop - 8;
      } else {
        akis.scrollTop = akis.scrollHeight;
      }
      if (!kaydetme) { gecmis.push({ k: kim, m: metin }); }
      return d;
    }

    // Mobilde her cevaptan sonra odak vermek klavyeyi ziplatiyor ve yeni
    // gelen cevabi ekrandan itiyordu. Dokunmatik cihazda odak zorlanmaz.
    var dokunmatik = false;
    try { dokunmatik = window.matchMedia('(pointer:coarse)').matches; } catch (e) {}
    function odakVer() { if (!dokunmatik) { try { girdi.focus(); } catch (e) {} } }

    function kilitle(acik) {
      gonder.disabled = acik;
      girdi.disabled = acik;
      girdi.placeholder = acik ? 'Yanıt bekleniyor…' : 'Mesajınızı yazın…';
    }

    function yolla(metin, gizli) {
      if (!gizli) ekle(metin, 'ben');
      kilitle(true);

      var bekle = document.createElement('div');
      bekle.className = 'lc-yaz';
      bekle.setAttribute('aria-live', 'polite');
      bekle.textContent = 'yazıyor…';
      akis.appendChild(bekle);
      akis.scrollTop = akis.scrollHeight;

      // 🔴 ZAMAN ASIMI SART.
      // Once AbortController yoktu: sunucu takilirsa "yazıyor…" sonsuza
      // kadar kaliyor, gonder butonu bir daha ACILMIYORDU. Musteri
      // Enter'a basiyor, hicbir sey olmuyor, widget bozuk saniyor.
      var kontrol = null, zamanAsti = false;
      try { kontrol = new AbortController(); } catch (e) {}
      var sayac = setTimeout(function () {
        zamanAsti = true;
        if (kontrol) { try { kontrol.abort(); } catch (e) {} }
      }, 25000);

      var istek = { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mesaj: metin, musteriId: oturum }) };
      if (kontrol) istek.signal = kontrol.signal;

      fetch(UC, istek)
        .then(function (r) {
          // 🔴 r.ok kontrol edilmiyordu: hiz sinirina takilinca musteri
          // "yanıt veremiyorum" gorup tekrar deniyor, sebebini hic ogrenmiyordu.
          if (r.status === 429) { var e = new Error('limit'); e.tip = 'limit'; throw e; }
          if (!r.ok) { var e2 = new Error('sunucu'); e2.tip = 'sunucu'; throw e2; }
          return r.json();
        })
        .then(function (d) {
          clearTimeout(sayac);
          bekle.remove();
          ekle(d && d.cevap ? d.cevap
                            : 'Şu an yanıt veremiyorum, lütfen tekrar deneyin.', 'bot');
        })
        .catch(function (e) {
          clearTimeout(sayac);
          bekle.remove();
          var msj;
          if (zamanAsti)            msj = 'Yanıt beklenenden uzun sürdü. Tekrar denemek ister misiniz?';
          else if (e && e.tip === 'limit')
                                    msj = 'Kısa sürede çok sayıda mesaj aldık. Birkaç dakika sonra devam edebiliriz. Bu arada ürünlerimiz: https://lcarlie.shop';
          else                      msj = 'Bağlantı kurulamadı. Lütfen biraz sonra tekrar deneyin. Ürünlerimiz: https://lcarlie.shop';
          var d2 = ekle(msj, 'bot');
          // Zaman asimi veya baglanti hatasinda TEKRAR DENE secenegi ver
          if (d2 && (zamanAsti || !e || e.tip !== 'limit')) {
            hizliCevaplariCiz(d2, ['Tekrar gönder'], function () { yolla(metin); });
          }
        })
        .then(function () {
          kilitle(false);
          odakVer();
          gecmisiKaydet();
        });
    }

    // -------------------------------------------------------------------
    // 🔴 ACILIS EKRANI
    //
    // Once sohbet acilir acilmaz ajana "merhaba" gonderiliyordu ve musteri
    // daha hicbir sey sormadan 2.400 TL'lik uclu paket teklifi goruyordu.
    // Yardim degil reklam gibi duruyordu; ayrica "3) Koru - gunes koruma
    // adimi" urunsuz/fiyatsiz yarim kaliyor, 30 urunlu katalog 3 urun
    // varmis gibi gorunuyordu.
    //
    // Yeni acilis: kisa karsilama + ajanin NE yapabildigi + 3 secenek.
    // Uclu rutin artik DAYATILMIYOR, musteri isterse seciyor.
    // Bu ekran ajana istek atmaz - aninda gorunur.
    // -------------------------------------------------------------------
    var ACILIS_METNI =
      'Merhaba, L\'CARLIÉ\'ye hoş geldiniz.\n' +
      'Ürünlerimiz, içerikleri, kullanımı ve fiyatları hakkında bilgi verebilirim.';

    var ACILIS_SECENEKLERI = [
      'İhtiyacıma göre ürün öner',
      'Günlük bakım rutini',
      'Sipariş ve kargo'
    ];

    function acilisEkrani() {
      var d = document.createElement('div');
      d.className = 'lc-m lc-bot';
      ACILIS_METNI.split('\n').forEach(function (s) {
        var p = document.createElement('div');
        p.textContent = s;
        d.appendChild(p);
      });
      hizliCevaplariCiz(d, ACILIS_SECENEKLERI);
      akis.appendChild(d);
      akis.scrollTop = akis.scrollHeight;
    }

    function ac() {
      pnl.classList.add('acik');
      btn.style.display = 'none';
      btn.setAttribute('aria-expanded', 'true');
      odakVer();
      if (!basladi) {
        basladi = true;
        var eski = gecmisiOku();
        if (eski.length) {
          // Sayfa gecisinden sonra konusma kaldigi yerden devam eder
          gecmis = eski.slice();
          eski.forEach(function (x) { ekle(x.m, x.k, true); });
        } else {
          acilisEkrani();
        }
      }
      gecmisiKaydet();
    }
    function kapat() {
      pnl.classList.remove('acik');
      btn.style.display = '';
      btn.setAttribute('aria-expanded', 'false');
      gecmisiKaydet();
      try { btn.focus(); } catch (e) {}   // odak sayfanin basina atlamasin
    }

    btn.onclick = ac;
    document.getElementById('lc-kapat').onclick = kapat;
    // Klavye kullanicisi paneli Esc ile kapatabilmeli
    pnl.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); kapat(); }
    });

    // Sayfa gecisinden once acik idiyse acik gelsin
    try {
      if (localStorage.getItem('lc_acik') === '1') ac();
    } catch (e) {}
    gonder.onclick = function () {
      var t = girdi.value.trim();
      if (!t) return;
      girdi.value = '';
      yolla(t);
    };
    girdi.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); gonder.click(); }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', kur);
  } else {
    kur();
  }

  // Wix sayfa gecisi yaptiginda balon silinmis olabilir - 2 saniyede bir
  // varligini kontrol et, yoksa tekrar kur. Varsa hicbir sey yapmaz.
  setInterval(kur, 2000);
})();