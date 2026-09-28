/* L'CARLIÉ Jarvis — giriş ekranı
   Departman listesi ve kadro sayıları 27.09.2026'da roster'dan ölçüldü.
   Ağaç halkası yavaşça döner; adlar kendi ışınları boyunca dizilir. */
(function(){
  "use strict";

  /* kod, ad, kadro, okuduğu kaynak, aile, bağlı ekipler */
  var D = [
    ["TASARIM","Tasarım",16,"core.tasarim_sablon","kreatif",["YAYIN","BRAND","CREATIVE_STRAT"]],
    ["BRAND","Marka",7,"marka hafıza dosyası","kreatif",["TASARIM","COPY","PR"]],
    ["CREATIVE_STRAT","Kreatif Strateji",6,"mart.kreatif_performans","kreatif",["COPY","META_MEDIA","BRAND"]],
    ["EXEC","Yönetim",5,"mart.anlik_gorunum","yonetim",["FINANCE","PRODUCT","DATA_BI"]],
    ["PR","Halkla İlişkiler",5,"itibar izleme","kreatif",["BRAND","SOCIAL","QUALITY"]],
    ["RED_TEAM","Red Team",5,"karar kayıtları","denetim",["REGULATORY","DATA_BI","EXEC"]],
    ["YAYIN","Yayın",5,"katalog.json","kreatif",["TASARIM","REGULATORY","COPY"]],
    ["REGULATORY","Mevzuat",4,"jarvis.compliance","denetim",["YAYIN","PRODUCT","RED_TEAM"]],
    ["COMPETITOR_INT","Rakip İstihbarat",3,"grounded arama","pazar",["MARKET_INT","META_MEDIA","PRODUCT"]],
    ["META_MEDIA","Meta Reklam",3,"mart.kreatif_performans","pazar",["CREATIVE_STRAT","CRO","SOCIAL"]],
    ["SEO","SEO",3,"site tarama","pazar",["WEB","CONTENT","COPY"]],
    ["SOCIAL","Sosyal Medya",3,"raw.ig_medya","pazar",["CONTENT","PR","CREATIVE_STRAT"]],
    ["TEKNOLOJI","Teknoloji",3,"araç envanteri","sistem",["WEB","SECURITY","AI_OPS"]],
    ["WEB","Web",3,"GA4 / Umami","sistem",["SEO","CRO","TEKNOLOJI"]],
    ["BIZDEV","İş Geliştirme",2,"fırsat kayıtları","pazar",["B2B","MARKETPLACE","EXEC"]],
    ["COPY","Metin",2,"katalog metinleri","kreatif",["BRAND","YAYIN","SEO"]],
    ["DATA_BI","Veri",2,"mart şeması","denetim",["EXEC","RED_TEAM","WEB"]],
    ["FINANCE","Finans",2,"mart.gunluk_ozet","yonetim",["EXEC","ECOM","FULFILLMENT"]],
    ["MARKETPLACE","Pazaryeri",2,"kanal kapsama","pazar",["ECOM","BIZDEV","FULFILLMENT"]],
    ["MARKET_INT","Pazar İstihbarat",2,"dış araştırma","pazar",["COMPETITOR_INT","PRODUCT","EXEC"]],
    ["SECURITY","Güvenlik",2,"erişim kayıtları","sistem",["TEKNOLOJI","WEB","AI_OPS"]],
    ["AI_OPS","AI Operasyon",1,"model katmanı","sistem",["TEKNOLOJI","DATA_BI","SECURITY"]],
    ["ART","Görsel Yönetim",1,"aset kütüğü","kreatif",["TASARIM","BRAND","CONTENT"]],
    ["B2B","Saha Satış",1,"saha ziyaret","pazar",["BIZDEV","FULFILLMENT","MARKETPLACE"]],
    ["CONTENT","İçerik",1,"içerik takvimi","kreatif",["SOCIAL","SEO","COPY"]],
    ["CRM","Müşteri İlişkileri",1,"lcarlie.konusma","musteri",["RETENTION","QUALITY","ECOM"]],
    ["CRO","Dönüşüm",1,"GA4 huni","pazar",["WEB","META_MEDIA","ECOM"]],
    ["ECOM","E-ticaret",1,"raw.wix_urun","musteri",["CRO","FINANCE","MARKETPLACE"]],
    ["FULFILLMENT","Operasyon",1,"BasitKargo","musteri",["B2B","FINANCE","MARKETPLACE"]],
    ["PRODUCT","Ürün Portföyü",1,"mart.urun_karti","yonetim",["REGULATORY","MARKET_INT","EXEC"]],
    ["QUALITY","Kalite",1,"şikâyet kök neden","musteri",["CRM","PR","RETENTION"]],
    ["RETENTION","Sadakat",1,"tekrar satın alma","musteri",["CRM","QUALITY","ECOM"]]
  ];

  var AILE = {kreatif:"Kreatif", pazar:"Pazar", denetim:"Denetim",
              yonetim:"Yönetim", musteri:"Müşteri", sistem:"Sistem"};

  var SVG = "http://www.w3.org/2000/svg", CX = 280, CY = 280, R = 152;
  var halka = document.getElementById("halka");
  var kenarlar = document.getElementById("kenarlar");
  var dugumler = [], AD = {};
  D.forEach(function(d){ AD[d[0]] = d; });

  D.forEach(function(d, i){
    var a = (i / D.length) * Math.PI * 2 - Math.PI / 2;
    var x = CX + Math.cos(a) * R, y = CY + Math.sin(a) * R;

    var ln = document.createElementNS(SVG, "line");
    ln.setAttribute("class", "tel-hat");
    ln.setAttribute("data-ic", d[0]);
    ln.setAttribute("x1", CX); ln.setAttribute("y1", CY);
    ln.setAttribute("x2", x);  ln.setAttribute("y2", y);
    kenarlar.appendChild(ln);

    var g = document.createElementNS(SVG, "g");
    g.setAttribute("class", "dugum");
    g.setAttribute("tabindex", "0");
    g.setAttribute("role", "button");
    g.setAttribute("aria-pressed", "false");
    g.setAttribute("aria-label", d[1] + ", " + d[2] + " kişi");
    g.setAttribute("data-k", d[0]);

    var c = document.createElementNS(SVG, "circle");
    c.setAttribute("cx", x); c.setAttribute("cy", y);
    c.setAttribute("r", (4.6 + Math.min(d[2], 16) * 0.58).toFixed(2));
    g.appendChild(c);

    /* ad, kendi ışını boyunca dışa doğru dizilir: 32 adda çakışma olmaz.
       Sol yarıda 180 derece çevrilir ki ters okunmasın. */
    var derece = a * 180 / Math.PI;
    var sol = Math.cos(a) < 0;
    var bosluk = 10 + Number(c.getAttribute("r"));
    var t = document.createElementNS(SVG, "text");
    t.setAttribute("x", (x + (sol ? -bosluk : bosluk)).toFixed(1));
    t.setAttribute("y", (y + 2.5).toFixed(1));
    t.setAttribute("text-anchor", sol ? "end" : "start");
    t.setAttribute("transform", "rotate(" + (sol ? derece + 180 : derece).toFixed(2) +
                   " " + x.toFixed(1) + " " + y.toFixed(1) + ")");
    t.textContent = d[1].toLocaleUpperCase("tr");
    g.appendChild(t);

    halka.appendChild(g);
    dugumler.push(g);
  });

  var yan = {
    aile:   document.getElementById("d-aile"),
    ad:     document.getElementById("d-ad"),
    rol:    document.getElementById("d-rol"),
    uye:    document.getElementById("d-uye"),
    kaynak: document.getElementById("d-kaynak"),
    durum:  document.getElementById("d-durum"),
    baglar: document.getElementById("d-baglar"),
    meta:   document.getElementById("secim-meta")
  };

  function sec(k, odakla){
    var d = AD[k];
    if(!d){ return; }

    dugumler.forEach(function(g){
      g.setAttribute("aria-pressed", g.getAttribute("data-k") === k ? "true" : "false");
    });
    Array.prototype.forEach.call(kenarlar.children, function(l){
      var ic = l.getAttribute("data-ic");
      var vurgulu = (ic === k) || d[5].indexOf(ic) > -1;
      l.setAttribute("class", "tel-hat" + (vurgulu ? " vurgu" : ""));
    });

    yan.aile.textContent = (AILE[d[4]] || d[4]).toLocaleUpperCase("tr");
    yan.ad.textContent = d[1];
    yan.rol.textContent = "Bu departman " + d[3] + " kaynağını okur. Kaynağı olmayan üye panelde konuşmaz.";
    yan.uye.textContent = d[2] + " kişi";
    yan.kaynak.textContent = d[3];
    yan.durum.textContent = "çalışıyor";
    yan.meta.textContent = d[0];

    yan.baglar.textContent = "";
    d[5].forEach(function(b){
      var el = document.createElement("button");
      el.className = "rozet";
      el.type = "button";
      el.textContent = AD[b] ? AD[b][1] : b;
      if(AD[b]){ el.addEventListener("click", function(){ sec(b); }); }
      yan.baglar.appendChild(el);
    });

    if(odakla){
      var hedef = dugumler.filter(function(g){ return g.getAttribute("data-k") === k; })[0];
      if(hedef){ hedef.focus(); }
    }
  }

  dugumler.forEach(function(g, i){
    g.addEventListener("click", function(){ sec(g.getAttribute("data-k")); });
    g.addEventListener("keydown", function(e){
      if(e.key === "Enter" || e.key === " "){
        e.preventDefault(); sec(g.getAttribute("data-k"));
      } else if(e.key === "ArrowRight" || e.key === "ArrowDown"){
        e.preventDefault(); dugumler[(i + 1) % dugumler.length].focus();
      } else if(e.key === "ArrowLeft" || e.key === "ArrowUp"){
        e.preventDefault(); dugumler[(i - 1 + dugumler.length) % dugumler.length].focus();
      }
    });
  });

  /* ---- departman dizini: tam kadro, satıra dokununca ağaçta seçilir ---- */
  var dizin = document.getElementById("dizin");
  if(dizin){
    D.forEach(function(d){
      var b = document.createElement("button");
      b.type = "button";
      b.className = "dizin-satir";
      b.setAttribute("data-k", d[0]);
      var ad = document.createElement("span");
      ad.textContent = d[1];
      var ai = document.createElement("span");
      ai.className = "dizin-aile";
      ai.textContent = AILE[d[4]] || d[4];
      var sy = document.createElement("span");
      sy.className = "dizin-sayi";
      sy.textContent = d[2];
      b.appendChild(ad); b.appendChild(ai); b.appendChild(sy);
      b.addEventListener("click", function(){
        sec(d[0]);
        var bolum = document.getElementById("ekip");
        if(bolum){ bolum.scrollIntoView({block:"start"}); }
        sec(d[0], true);
      });
      dizin.appendChild(b);
    });
  }

  sec("TASARIM");
})();
