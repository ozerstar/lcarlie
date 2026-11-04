
/* Sunum katmanı: kayıtların kimliklerini ve kullanıcı girişlerini değiştirmez. */
(function(root){
 const names={"EXEC":"Üst yönetim","FINANCE":"Finans","TEKNOLOJI":"Teknoloji ve araçlar","WEB":"Web ve dönüşüm","BRAND":"Marka","PR":"Basın ve halkla ilişkiler","B2B":"Kurumsal satış","BIZDEV":"İş geliştirme","CRO":"Dönüşüm ve deneyim","ECOM":"E-ticaret ve sipariş","EXPORT":"İhracat","MARKETPLACE":"Pazaryerleri","PHARMACY":"Eczane ve kilit müşteriler","ART":"Sanat yönetimi","CONTENT":"İçerik","COPY":"Metin yazarlığı","CREATIVE_STRAT":"Kreatif strateji","UGC":"Video ve kullanıcı içerikleri","CRM":"Müşteri ilişkileri","CS":"Müşteri hizmetleri","CUSTOMER_INT":"Müşteri araştırması","RETENTION":"Müşteri bağlılığı","DATA_BI":"Veri ve iş zekâsı","EXPERIMENT":"Deneyler","FORECAST":"Tahminleme","DECISION_MEM":"Karar hafızası","LEGAL":"Hukuk ve kişisel veriler","QUALITY":"Kalite","RED_TEAM":"İç denetim","REGULATORY":"Mevzuat ve ürün iddiaları","HR":"İnsan kaynakları","COMPETITOR_INT":"Rakip araştırması","MARKET_INT":"Pazar araştırması","TASARIM":"Tasarım ve üretim","YAYIN":"Yayın ve editoryal","GOOGLE_ADS":"Google arama reklamları","INFLUENCER":"İçerik üreticileri","INSTAGRAM":"Instagram","META_MEDIA":"Meta reklamları","SEO":"Arama görünürlüğü","SOCIAL":"Organik sosyal medya","TIKTOK":"TikTok ve kısa video","FULFILLMENT":"Sipariş hazırlama ve kargo","INVENTORY":"Stok ve envanter","PROCUREMENT":"Satın alma","SUPPLY":"Tedarik zinciri","AI_OPS":"Otomasyon ve yapay zekâ","SECURITY":"Güvenlik","PRODUCT":"Ürün yönetimi","RND":"Araştırma ve yeni ürün","ALTYAPI":"TECDYNASTY · Teknoloji ve yazılım","COMMERCIAL":"Ticaret","CREATIVE":"Goril Ajans · Yaratıcı üretim","CUSTOMER":"Müşteri","DATA":"Veri","EXECUTIVE":"Üst yönetim","GOVERNANCE":"Yönetişim","INSAN_VE_ORGANIZASYON":"İnsan ve organizasyon","INTELLIGENCE":"Araştırma","KREATIF":"Goril Ajans · Tasarım ve yayın","MARKETING":"Pazarlama","OPERATIONS":"Operasyon","PLATFORM":"Platform","arac_envanteri_uzmani":"Araç Envanteri Uzmanı","arac_arastirmacisi":"Araç Araştırmacısı","surum_takipcisi":"Sürüm ve Bağımlılık Takipçisi","web_gelistirici":"Web Geliştirici","sayfa_donusum":"Sayfa Dönüşüm Uzmanı","site_izleme":"Site İzleme Sorumlusu","marka_kimlik":"Marka Kimlik Sorumlusu","marka_mimarisi":"Marka Mimarisi Uzmanı","marka_deneyimi":"Marka Deneyimi Uzmanı","marka_sagligi":"Marka Sağlığı Analisti","brand_voice":"Müşteri Dili Uzmanı","brand_positioning":"Konumlandırma Uzmanı","brand_strategy":"Marka Stratejisti","halkla_iliskiler_muduru":"Halkla İlişkiler Müdürü","basin_iliskileri":"Basın İlişkileri Uzmanı","kriz_iletisimi":"Kriz İletişimi Sorumlusu","itibar_izleme":"İtibar ve Şikâyet İzleme","isbirligi_sorumlusu":"İş Birliği ve Influencer Sorumlusu","field_b2b_sales":"Kurumsal Satış Uzmanı","firsat_takibi":"Fırsat Takip Uzmanı","bizdev":"İş Geliştirme Uzmanı","CRO_SPECIALIST":"Dönüşüm Uzmanı","ecommerce_sales":"Satış Analisti","kanal_kapsama":"Kanal Kapsama Uzmanı","pazaryeri_uzmani":"Pazaryeri Uzmanı","art_format":"Görsel Format Analisti","content_cadence":"İçerik Ritmi Analisti","creative_copy":"Başlık ve CTA Analisti","COPYWRITER":"Metin Yazarı","creative_intelligence":"Kreatif İstihbarat","creative_decision":"Kreatif Karar Uzmanı","creative_hypothesis":"Kreatif Hipotez Uzmanı","creative_coverage":"İçerik kapsamı","CREATIVE_DIRECTOR":"Kreatif Direktör","CREATIVE_INTELLIGENCE":"Kreatif İstihbarat (ajans)","video_brief":"Video Brief Analisti","crm_customer":"Müşteri İlişkileri Uzmanı","musteri_hizmetleri":"Müşteri Hizmetleri Takipçisi","musteri_istihbarati":"Müşteri İçgörü Uzmanı","tekrar_satin_alma":"Tekrar Satın Alma Uzmanı","data_measurement":"Ölçüm ve Veri Uzmanı","research":"Araştırma","deney_izleme":"Deney Hazırlık Uzmanı","growth":"Büyüme Uzmanı","strategy":"Strateji","managing_director":"Genel Müdür (sentez)","is_planlama":"İş Planlama Müdürü","GROWTH_STRATEGIST":"Büyüme Stratejisti","finance":"Finans Uzmanı","accounting_control":"Muhasebe Kontrol","karar_hafizasi":"Karar Hafızası Uzmanı","sikayet_kok_neden":"Şikâyet Kök Neden Uzmanı","karar_denetcisi":"Karar Sonuç Denetçisi","veri_guven_denetcisi":"Veri Güvenilirlik Denetçisi","oneri_denetcisi":"Öneri Takip Denetçisi","model_denetcisi":"Model Başarı Denetçisi","red_team":"Kırmızı Takım","alan_tutarlilik":"Platform Tutarlılık Denetçisi","iddia_envanteri":"İddia Envanteri Uzmanı","yetki_denetcisi":"Yetki ve Sınır Denetçisi","regulatory_quality":"Mevzuat ve Kalite Uzmanı","ik_organizasyon":"İK ve Organizasyon Sorumlusu","ik_kaynak":"İK Kaynak Bağlantı Uzmanı","ik_is_takibi":"İK İş Takip Uzmanı","ik_gelisim":"İK Gelişim Uzmanı","price_position":"Fiyat Konumu Analisti","competitor_intelligence":"Rakip İstihbaratı","COMPETITOR_CREATIVE":"Rakip Kreatif","market_findings":"Pazar Bulgu Uzmanı","market_intelligence":"Pazar İstihbaratı","dizgi_baski":"Dizgi ve Baskı Sorumlusu","tasarim_direktoru":"Tasarım Direktörü","produksiyon_muduru":"Kreatif Prodüksiyon Müdürü","sablon_sorumlusu":"Şablon Sorumlusu","grafik_tasarimci":"Grafik Tasarımcı","dizgi_uzmani":"Dizgi ve Tipografi Uzmanı","varlik_sorumlusu":"Görsel Varlık Sorumlusu","kesim_uzmani":"Ürün Kesim ve Rötuş Uzmanı","video_editoru":"Video Editörü","marka_muhafizi":"Marka Muhafızı","tasarim_metin_yazari":"Kreatif Metin Yazarı","tasarim_mevzuat":"Tasarım Mevzuat Denetçisi","meta_kreatif":"Meta Reklam Kreatifçisi","sosyal_editor":"Sosyal Medya Editörü","baski_uzmani":"Baskı ve Katalog Uzmanı","tasarim_performans":"Kreatif Performans Analisti","kurumsal_editor":"Kurumsal İçerik Editörü","katalog_editoru":"Katalog Editörü","kitap_editoru":"Kitap Editörü","yayin_hukuk":"Yayın Hukuk ve Mevzuat Denetçisi","kaynakca_sorumlusu":"Kaynakça ve Doğrulama Sorumlusu","instagram_olcum":"Instagram İçerik Ölçüm Uzmanı","meta_performance":"Meta Reklam Analisti","creative_fatigue":"Kreatif Yorgunluk Analisti","META_PERFORMANCE":"Meta Performans (ajans)","seo_icerik":"SEO İçerik Uzmanı","seo_anahtar":"Anahtar Kelime Uzmanı","seo_teknik":"Teknik SEO Uzmanı","social_media":"Sosyal Medya Uzmanı","social_engagement":"Sosyal Etkileşim Analisti","SOCIAL_CONTENT":"Sosyal İçerik","operations":"Operasyon Uzmanı","stok_kapsama":"Stok Kapsama Denetçisi","ai_prompt_engineering":"AI ve Motor Sorumlusu","erisim_denetcisi":"Erişim ve Yetki Denetçisi","baglanti_denetcisi":"Bağlantı ve Kimlik Denetçisi","product_portfolio":"Ürün ve Portföy Uzmanı","yeni_urun_on_arastirma":"Yeni Ürün Ön Araştırmacısı","arac_envanteri":"Araç envanteri","capabilities":"Yapılabilen işler","urun_seo":"Ürün arama görünürlüğü","urun_karti":"Ürün kartları","sayfa_olcum":"Sayfa ölçümleri","ecommerce_funnel":"Satış yolu","system":"Sistem durumu","provenance":"Bilginin dayanağı","tasarim_sablonlari":"Tasarım şablonları","tasarim_isleri":"Tasarım işleri","urun_bilgi":"Ürün bilgileri","operations_shipments":"Kargo hareketleri","content_performance":"İçerik sonuçları","customer_voice":"Müşteri görüşleri","ecommerce_price":"Ürün fiyatları","gunluk_brief":"Günlük çalışma özeti","basin_bahsi":"Basındaki haberler","market_research":"Pazar araştırması","crm_unanswered":"Yanıt bekleyen müşteriler","decision_summary":"Karar özeti","sales_orders":"Siparişler","sales_items":"Satılan ürünler","agenda":"Gündem","decision_outcomes":"Karar sonuçları","platform_fiyat_matrisi":"Kanallara göre fiyatlar","urun_alan_karsilastirma":"Ürün bilgisi karşılaştırması","kreatif_performans":"Tasarım sonuçları","advertising_performance":"Reklam sonuçları","creative_decisions":"İçerik kararları","creative_hypotheses":"Sınanacak içerik fikirleri","crm_customers":"Müşteri kayıtları","open_work":"Açık işler","advertising_spend":"Reklam harcamaları","departments":"Birim kayıtları","evidence_readiness":"Kanıtların yeterliliği","financial":"Mali kayıtlar","financial_cash":"Nakit durumu","own_proposals":"Ekip önerileri","learning_loop":"Öğrenme döngüsü","data_quality":"Veri kalitesi","action_contract":"İşlem koşulları","capability_state":"İş yapabilme durumu","model_kademe":"Yanıt hizmeti durumu","ecommerce_profitability":"Ürün kârlılığı","siparis_tum_zaman":"Tüm siparişler","KISMI":"Kısmi bağlantı","TANIMLI":"Kaynak tanımlı","BAGLI_DEGIL":"Kaynak bağlı değil","data":"Veri incelemesi","agency":"Üretim çalışması","READY":"Hazır","SUCCEEDED":"Tamamlandı","SUCCESS":"Tamamlandı","FAILED":"Tamamlanamadı","RUNNING":"Çalışıyor","PENDING":"Bekliyor","PROPOSED":"Önerildi","IN_PROGRESS":"Çalışma sürüyor","WAITING":"Bekliyor","UNKNOWN":"Bilinmiyor","NOT_VERIFIED":"Henüz doğrulanmadı","LOW":"Düşük","MEDIUM":"Orta","HIGH":"Yüksek","CONNECTED":"Bağlı","DISCONNECTED":"Bağlı değil","ACTIVE":"Etkin","INACTIVE":"Etkin değil","team":"Ekip","dashboard":"Genel görünüm","retry":"Yeniden dene","loading":"Yükleniyor","error":"İşlem tamamlanamadı","failed":"Tamamlanamadı","completed":"Tamamlandı","source_missing":"Kaynak bağlantısı eksik","source_partial":"Kaynak bağlantısı kısmi"};
 const english=/\b(the|your|please|unable|failed|cannot|could|request|response|provider|unexpected|invalid|error|is|are|this|with|from|has|have|not|found|retry|timeout)\b/gi;
 function foreign(value){const s=String(value||'');const words=s.match(/[a-zA-ZçğıöşüİÇĞÖŞÜ]+/g)||[];return (s.match(english)||[]).length>=Math.max(3,words.length*.17);}
 function text(value){
  let s=String(value??'');if(!s.trim())return s;
  if(/failed to fetch|networkerror|syntaxerror|typeerror|internal server error|no model provider could answer|unexpected token/i.test(s))return error(s);
  if(/^(https?:\/\/|[\w.+-]+@[\w.-]+\.)/.test(s.trim()))return s;
  if(names[s.trim()])s=s.replace(s.trim(),names[s.trim()]);
  const wording={"Influencer":"İçerik Üreticisi","influencer":"içerik üreticisi","workflow":"iş akışı","Workflow":"İş akışı","Feedback":"Geri bildirim","feedback":"geri bildirim","dashboard":"genel görünüm","Dashboard":"Genel görünüm","brief":"iş özeti","Brief":"İş özeti","mockup":"tasarım taslağı","Mockup":"Tasarım taslağı"};s=s.replace(/\b(?:Influencer|influencer|workflow|Workflow|Feedback|feedback|dashboard|Dashboard|brief|Brief|mockup|Mockup)\b/g,k=>wording[k]);
  s=s.replace(/\b(?:core|mart|raw|public)\.([a-z][a-z0-9_]*)\b/g,(_,k)=>names[k]||'Şirket veri kaynağı');
  s=s.replace(/office:team-cycle:[^\s,;]+/g,'Son ekip faaliyet kaydı');
  s=s.replace(/\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b/g,k=>names[k]||'Açıklaması henüz tanımlanmamış kayıt');
  s=s.replace(/\b[A-Z][A-Z0-9_]{1,}\b/g,k=>names[k]||k);
  s=s.replace(/\(([^()]*)\)/g,(_,v)=>'— '+v.trim()+' —');
  if(foreign(s))return 'Bu içerik için Türkçe açıklama henüz hazırlanamadı. Kaynağın okunması, işlemin tamamlandığı anlamına gelmez. Yeniden deneyebilirsiniz.';
  return s;
 }
 function error(value,fallback='İşlem tamamlanamadı. Biraz sonra yeniden deneyin. Sorun sürerse bağlantı durumunu kontrol edin.'){
  const s=String(value||'');
  if(/abort|timeout|timed out|zaman aş|süre.*dol/i.test(s))return 'Yanıt bekleme süresi doldu. Soru tamamlanamadı; yeniden deneyebilirsiniz.';
  if(/401|unauthor|authentication|oturum.*(gerek|sona)/i.test(s))return 'Oturumunuz sona erdi. Yeniden giriş yapın.';
  if(/403|forbidden|csrf|permission/i.test(s))return 'Bu işlem için oturum doğrulanamadı. Sayfayı yenileyip tekrar deneyin.';
  if(/model|provider|quota|rate.limit|429|overload/i.test(s))return 'Yanıt hizmeti şu anda kullanılamıyor. Soru için yanıt üretilemedi; biraz sonra yeniden deneyin.';
  if(/fetch|network|connection|502|503|504|unexpected|json|syntaxerror|typeerror|traceback|internal|not found|<html/i.test(s))return fallback;
  return s&&!foreign(s)&&/[çğıöşüİ]/i.test(s)?text(s):fallback;
 }
 root.JarvisDil=Object.freeze({text,error,foreign,names});
})(globalThis);

/* Kullanıcıya gösterilen iş adları. Üretim komutları kuyrukta aynen kalır. */
(function (root) {
  'use strict';
  const sections = {
    ritual: 'Ritüel', bebek: 'Bebek', mahrem: 'Mahrem bakım', bariyer: 'Cilt bariyeri',
    vucut: 'Vücut', yuz: 'Yüz', kapak: 'Kapak',
  };
  const technical = /\b(?:extreme macro|editorial|texture|continuous surface|shallow focus|photorealistic|soft diffused light|soft even light|fine water film|matte silk|muslin weave|render|live capability|data contract|step\(s\)|internal server error|traceback|syntaxerror|typeerror|HTTP\s*\d+)\b|\b(?:SUCCEEDED|PENDING|PROPOSED|FAILED|RUNNING)\b|\{\s*"/i;
  function needsSummary(value) { return technical.test(String(value || '')) || /\b[a-z]+(?:_[a-z]+)+\b/.test(String(value || '')); }
  function safeTitle(value, fallback) {
    const title = String(value || '').trim();
    return !title ? fallback : needsSummary(title) ? fallback : title;
  }
  function jobTitle(job) {
    const request = String(job?.istem || '').trim();
    if (String(job?.isteyen || '').startsWith('katalog/bolum-acilisi')) {
      const section = sections[String(job?.id || '').replace(/^ktb?-/, '')];
      return section ? `Katalog görseli: ${section}` : 'Katalog bölüm görseli';
    }
    if (!needsSummary(request)) return request || 'Başlıksız iş';
    if (/sage green|eucalyptus|mineral surface/i.test(request)) return 'Adaçayı tonlarında mineral yüzey görseli';
    if (/cotton muslin|milk white fibres|muslin weave/i.test(request)) return 'Beyaz pamuklu kumaş görseli';
    if (/matte silk|muted plum|deep rose/i.test(request)) return 'Gül ve erik tonlarında ipek kumaş görseli';
    if (/terracotta clay|burnt ochre|fine fissures/i.test(request)) return 'Toprak tonlarında çatlak kil görseli';
    return 'Görsel hazırlama işi';
  }
  function source(job) {
    const value = String(job?.isteyen || '');
    if (value.startsWith('katalog/')) return 'Katalog çalışması';
    if (value === 'mobil-operator') return 'Telefondan istendi';
    if (value === 'panel' || value === 'operator') return 'Panelden istendi';
    return value ? 'Otomatik çalışma' : '';
  }
  function errorText(value, fallback) {
    const message = String(value || '').trim();
    return message && !needsSummary(message) && (/[çğıöşüİ]/i.test(message) || /\b(?:hatalı|eksik|geçersiz|bulunamadı|zorunlu|lütfen|izin|erişim|başarısız)\b/i.test(message))
      ? message : fallback;
  }
  const codes = {
    OK:'Hazır', PASS:'Geçti', FAIL:'Tamamlanamadı', FAILED:'Tamamlanamadı',
    CONNECTED:'Bağlı', DISCONNECTED:'Bağlı değil', PRODUCED:'Üretildi',
    CURRENT:'Güncel', FRESH:'Güncel', STALE:'Güncel değil', UNKNOWN:'Bilinmiyor',
    READY:'Hazır', ACTIVE:'Etkin', INACTIVE:'Etkin değil', UNAVAILABLE:'Kullanılamıyor',
    NEEDS_DATA:'Veri gerekli', DATA_UNAVAILABLE:'Veri yok',
    LOW:'Düşük', MEDIUM:'Orta', HIGH:'Yüksek', CRITICAL:'Kritik',
    ecommerce:'E-ticaret', advertising:'Reklam', crm:'Müşteri ilişkileri',
    operations:'Operasyon', finance:'Finans', sales:'Satış',
    SHOP_NOW:'Mağazaya git', VIEW_INSTAGRAM_PROFILE:'Profili aç', MESSAGE_PAGE:'Mesaj gönder',
  };
  function label(value, fallback = 'Bilgi') {
    const raw = String(value || '').trim();
    if (!raw) return fallback;
    if (codes[raw]) return codes[raw];
    if (/^[A-Z][A-Z0-9_ -]+$/.test(raw) || /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/.test(raw)) return fallback;
    return safeTitle(raw, fallback);
  }
  root.JarvisMetin = Object.freeze({jobTitle, source, safeTitle, needsSummary, errorText:root.JarvisDil.error, label:(value,fallback)=>root.JarvisDil.text(label(value,fallback)), text:root.JarvisDil.text});
})(globalThis);

/* Son gösterim sınırı bütün panel bölümlerinde aynı sözlüğü kullanır. */
(function(){
 function excluded(el){return !el||el.closest('script,style,input,textarea,svg,[contenteditable="true"],.chat-msg.user,.message.user,.bubble.user,.bubble.me,.conversation-item.user,[data-role="user"],[data-original-text]');}
 function clean(node){
  if(node.nodeType===3){if(!excluded(node.parentElement)){const s=JarvisDil.text(node.nodeValue);if(s!==node.nodeValue)node.nodeValue=s;}return;}
  if(node.nodeType!==1||excluded(node))return;
  for(const attr of ['title','aria-label','placeholder'])if(node.hasAttribute(attr)){const old=node.getAttribute(attr),s=JarvisDil.text(old);if(s!==old)node.setAttribute(attr,s);}
  for(const child of [...node.childNodes])clean(child);
 }
 function start(){clean(document.body);new MutationObserver(records=>{for(const r of records){if(r.type==='characterData')clean(r.target);else for(const n of r.addedNodes)clean(n);}}).observe(document.body,{subtree:true,childList:true,characterData:true});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
