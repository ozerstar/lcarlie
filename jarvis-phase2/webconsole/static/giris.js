document.documentElement.lang = "tr";
(function(){
  /* Departman listesi ve üye sayıları 27.09.2026'da roster'dan ölçüldü. */
  var D = [
    ["TASARIM","Tasarım",16,"core.tasarim_sablon","kreatif",["YAYIN","BRAND","KREATİF"]],
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
    ["B2B","Saha Satış",1,"saha ziyaret",'pazar',["BIZDEV","FULFILLMENT","MARKETPLACE"]],
    ["CONTENT","İçerik",1,"içerik takvimi","kreatif",["SOCIAL","SEO","COPY"]],
    ["CRM","Müşteri İlişkileri",1,"lcarlie.konusma","musteri",["RETENTION","QUALITY","ECOM"]],
    ["CRO","Dönüşüm",1,"GA4 huni","pazar",["WEB","META_MEDIA","ECOM"]],
    ["ECOM","E-ticaret",1,"raw.wix_urun","musteri",["CRO","FINANCE","MARKETPLACE"]],
    ["FULFILLMENT","Operasyon",1,"BasitKargo","musteri",["B2B","FINANCE","MARKETPLACE"]],
    ["PRODUCT","Ürün Portföyü",1,"mart.urun_karti","yonetim",["REGULATORY","MARKET_INT","EXEC"]],
    ["QUALITY","Kalite",1,"şikâyet kök neden","musteri",["CRM","PR","RETENTION"]],
    ["RETENTION","Sadakat",1,"tekrar satın alma","musteri",["CRM","QUALITY","ECOM"]]
  ];
  var RENK = {kreatif:"--d-2", pazar:"--d-1", denetim:"--d-3",
              yonetim:"--d-6", musteri:"--d-4", sistem:"--d-5"};
  var SVG="http://www.w3.org/2000/svg", CX=280, CY=280, R=214;
  var halka=document.getElementById("halka"), kenarlar=document.getElementById("kenarlar");
  var dugumler=[], koord={};

  D.forEach(function(d,i){
    var a=(i/D.length)*Math.PI*2 - Math.PI/2;
    var x=CX+Math.cos(a)*R, y=CY+Math.sin(a)*R;
    koord[d[0]]={x:x,y:y};
    var ln=document.createElementNS(SVG,"line");
    ln.setAttribute("class","kenar"); ln.setAttribute("data-ic",d[0]);
    ln.setAttribute("x1",CX); ln.setAttribute("y1",CY);
    ln.setAttribute("x2",x);  ln.setAttribute("y2",y);
    kenarlar.appendChild(ln);

    var g=document.createElementNS(SVG,"g");
    g.setAttribute("class","dugum"); g.setAttribute("tabindex","0");
    g.setAttribute("role","button"); g.setAttribute("aria-pressed","false");
    g.setAttribute("aria-label",d[1]+", "+d[2]+" üye");
    g.setAttribute("data-k",d[0]);
    var c=document.createElementNS(SVG,"circle");
    c.setAttribute("cx",x); c.setAttribute("cy",y);
    c.setAttribute("r", 7 + Math.min(d[2],16)*0.72);
    c.setAttribute("stroke","var("+RENK[d[4]]+")");
    g.appendChild(c);
    var t=document.createElementNS(SVG,"text");
    var disari = x>=CX;
    t.setAttribute("x", x + (disari? 14 : -14));
    t.setAttribute("y", y+2.6);
    t.setAttribute("text-anchor", disari? "start":"end");
    t.setAttribute("transform","rotate("+(0)+" "+x+" "+y+")");
    t.textContent=d[1].toLocaleUpperCase("tr");
    g.appendChild(t);
    halka.appendChild(g);
    dugumler.push(g);
  });

  var ad=document.getElementById("d-ad"), rol=document.getElementById("d-rol"),
      uye=document.getElementById("d-uye"), kay=document.getElementById("d-kaynak"),
      dur=document.getElementById("d-durum"), bag=document.getElementById("d-baglar"),
      meta=document.getElementById("secim-meta"), nokta=document.getElementById("d-nokta");
  var AD={}; D.forEach(function(d){AD[d[0]]=d;});

  function sec(k){
    var d=AD[k]; if(!d) return;
    dugumler.forEach(function(g){ g.setAttribute("aria-pressed", g.getAttribute("data-k")===k ? "true":"false"); });
    [].forEach.call(kenarlar.children,function(l){
      var komsu = d[5].indexOf(l.getAttribute("data-ic"))>-1;
      l.setAttribute("class","kenar"+((l.getAttribute("data-ic")===k||komsu)?" vurgu":""));
    });
    ad.textContent=d[1];
    rol.textContent="Bu departman "+d[3]+" kaynağını okur. Kaynağı olmayan üye panelde konuşmaz.";
    uye.textContent=d[2]; kay.textContent=d[3]; dur.textContent="çalışıyor";
    nokta.className="nk ok";
    meta.textContent=d[0];
    bag.innerHTML="";
    d[5].forEach(function(b){
      var el=document.createElement("button");
      el.className="rozet"; el.type="button";
      el.textContent = AD[b] ? AD[b][1] : b;
      if(AD[b]) el.addEventListener("click",function(){ sec(b); });
      bag.appendChild(el);
    });
  }

  dugumler.forEach(function(g,i){
    g.addEventListener("click",function(){ sec(g.getAttribute("data-k")); });
    g.addEventListener("keydown",function(e){
      if(e.key==="Enter"||e.key===" "){ e.preventDefault(); sec(g.getAttribute("data-k")); }
      else if(e.key==="ArrowRight"||e.key==="ArrowDown"){ e.preventDefault(); dugumler[(i+1)%dugumler.length].focus(); }
      else if(e.key==="ArrowLeft"||e.key==="ArrowUp"){ e.preventDefault(); dugumler[(i-1+dugumler.length)%dugumler.length].focus(); }
    });
  });

  sec("TASARIM");
})();
