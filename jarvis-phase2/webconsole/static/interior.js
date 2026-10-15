/* Jarvis bölüm sayfaları: kısa yol, görsel akış ve kaynağa bağlı özetler. */
(() => {
  'use strict';
  const PAGES = {
    analiz: ['Analiz', 'Bir isteği adımlara ayır, kanıtları gör, sonra karar ver.', 'izleme', ['Talebi yaz', 'Planı incele', 'Çalıştır']],
    asistan: ['Asistan', 'Hatırlatıcılarını, gündemi ve bekleyen kararları yönet.', 'izleme', ['Hatırlatıcı', 'Gündem', 'Onaylar']],
    raporlar: ['Raporlar', 'Bulguları ve dayandıkları kayıtları bir arada incele.', 'izleme', ['Bulgular', 'Kaynaklar', 'Karar']],
    gorevler: ['Görevler', 'Çalışmaları takip et; önerileri inceleyip karar ver.', 'is', ['Çalışmalar', 'Öneriler', 'Döngüler']],
    fiyat: ['Fiyat', 'Ürünleri karşılaştır; değişikliği önce gör, sonra onaya gönder.', 'is', ['Ürünleri süz', 'Önizle', 'Onaya gönder']],
    eticaret: ['E-ticaret', 'Ürün bilgilerinin kanallar arasında nerede ayrıştığını gör.', 'is', ['Ürünü seç', 'Alanları karşılaştır', 'Düzeltmeyi incele']],
    satislar: ['Satışlar', 'Gönderilerin ve doğrulanan satışların gerçek kaydını izle.', 'is', ['Gönderiler', 'Açıklamalar', 'Doğrulama']],
    kargo: ['Kargo', 'Gönderileri takip et; ücretli barkod adımını ayrıca onayla.', 'is', ['Gönderiyi seç', 'Fiyatı gör', 'Barkodu onayla']],
    gelenkutusu: ['Gelen kutusu', 'Müşteri konuşmalarını ve kimin yanıtlayacağını gör.', 'is', ['Mesajı aç', 'Sahibini gör', 'Yanıtla']],
    musteri: ['Müşteriler', 'Sipariş geçmişini, tekrar alışverişi ve iadeleri incele.', 'is', ['Kişiyi seç', 'Geçmişi gör', 'İadeyi incele']],
    uretilenler: ['Üretilenler', 'Kreatif fikirleri, görselleri ve dosyaları tek yerde bul.', 'kreatif', ['Çalışmalar', 'Görseller', 'Ayrıntılar']],
    kreatifParti: ['Kreatif', 'Haftalık fikirleri incele; görsel üretimi için karar ver.', 'kreatif', ['Partiler', 'Fikirler', 'Onay']],
    reklam: ['Reklam', 'Gerçek performansla biçimleri ve çağrı düğmelerini karşılaştır.', 'kreatif', ['Düğme', 'Biçim', 'Kreatif']],
    tasarim: ['Tasarım', 'Şablonlardan çıkan işleri ve onay durumunu takip et.', 'kreatif', ['Şablon', 'Üretim', 'Onay']],
    ekip: ['Ekip', 'Ekip üyelerinin işlerini ve konuşmalarını görünür tut.', 'org', ['Üyeler', 'İşler', 'Durum']],
    ajanlar: ['Ajanlar', 'Jarvis’in kullandığı motorları ve görevlerini gör.', 'org', ['Motorlar', 'Görevler', 'Durum']],
    hafiza: ['Hafıza', 'Jarvis’in sakladığı notları gör, ekle veya sil.', 'org', ['Not ekle', 'Kayıtları gör', 'Yönet']],
    veri: ['Veri', 'Kaynakların ve sorguların güncel durumunu incele.', 'org', ['Kaynaklar', 'Sorgular', 'Durum']],
    katalog: ['Katalog', 'Ürün kartlarını bul, sunum notlarını ve ilgiyi kaydet.', 'org', ['Ürün seç', 'Not al', 'Sunum']],
    saha: ['Saha', 'Ziyaret hedeflerini filtrele, haritada gör ve rota oluştur.', 'org', ['Hedefleri süz', 'Haritayı aç', 'Rota çıkar']],
    isler: ['İşler', 'Görsel üretim isteğini ve iş kuyruğundaki durumunu izle.', 'org', ['İstek yaz', 'Kuyruğu izle', 'Çıktıyı gör']],
    sistem: ['Sistem', 'Makinelerin ölçümlerini ve model kademelerini kontrol et.', 'org', ['Makineler', 'Ölçümler', 'Kademeler']],
    ayarlar: ['Ayarlar', 'Çalışma alanının durumunu ve erişim tercihlerini gör.', 'org', ['Durum', 'Tercihler', 'Erişim']],
  };
  const ids = {
    analiz:'Analiz',asistan:'Asistan',raporlar:'Raporlar',gorevler:'Gorevler',fiyat:'Fiyat',eticaret:'Eticaret',satislar:'Satislar',kargo:'Kargo',gelenkutusu:'GelenKutusu',musteri:'Musteri',uretilenler:'Uretilenler',kreatifParti:'KreatifParti',reklam:'Reklam',tasarim:'Tasarim',ekip:'Ekip',ajanlar:'Ajanlar',hafiza:'Hafiza',veri:'Veri',katalog:'Katalog',saha:'Saha',isler:'Isler',sistem:'Sistem',ayarlar:'Ayarlar'
  };
  const groupNames={izleme:'Günlük çalışma',is:'Şirket işleri',kreatif:'Kreatif stüdyo',org:'Çalışma altyapısı'};
  const chartViews=new Set(['satislar','fiyat','eticaret','isler','kargo','musteri','sistem']);
  const loaded=new Map();
  const app=document.getElementById('appView');
  if(!app) return;

  for(const [name, data] of Object.entries(PAGES)) {
    const view=document.getElementById('view'+ids[name]);
    if(!view) continue;
    view.classList.add('iv-view','iv-'+data[2]);
    const hero=document.createElement('header');hero.className='iv-hero';
    const copy=document.createElement('div');copy.className='iv-copy';
    const category=document.createElement('p');category.className='iv-category';category.textContent=groupNames[data[2]];
    const title=document.createElement('h1');title.textContent=data[0];
    const description=document.createElement('p');description.className='iv-description';description.textContent=data[1];
    const tools=document.createElement('div');tools.className='iv-tools';
    const go=document.createElement('button');go.type='button';go.className='iv-go';go.textContent='Bölüme geç ↓';
    go.addEventListener('click',()=>view.querySelector(':scope > .panel')?.scrollIntoView({behavior:'smooth',block:'start'}));
    const ask=document.createElement('button');ask.type='button';ask.className='iv-ask';ask.textContent='Jarvis’e sor ✦';
    ask.addEventListener('click',()=>{const input=document.getElementById('chatInput');if(input){input.value=data[0]+' bölümünün durumunu kısaca açıkla.';input.focus();}});
    tools.append(go,ask);copy.append(category,title,description,tools);
    const art=document.createElement('div');art.className='iv-art';art.setAttribute('aria-hidden','true');
    hero.append(copy,art);
    const flow=document.createElement('div');flow.className='iv-flow';flow.setAttribute('aria-label','Bu ekranda');
    const flowLabel=document.createElement('span');flowLabel.className='iv-flow-label';flowLabel.textContent='Bu ekranda';flow.append(flowLabel);
    data[3].forEach((step,index)=>{const part=document.createElement('span');part.className='iv-flow-step';const num=document.createElement('b');num.textContent=String(index+1).padStart(2,'0');part.append(num,document.createTextNode(step));flow.append(part);});
    view.prepend(flow);view.prepend(hero);
    const originalCount=view.querySelector('.panel-count');
    if(originalCount && !originalCount.textContent.includes('/api')){
      const badge=document.createElement('span');badge.className='iv-count';badge.hidden=true;hero.append(badge);
      const update=()=>{const value=originalCount.textContent.trim();badge.hidden=!value||value==='—'||value==='yükleniyor…';badge.textContent=value;};
      new MutationObserver(update).observe(originalCount,{subtree:true,childList:true,characterData:true});update();
    }
    const intro=view.querySelector(':scope > .panel .sect-body > p.fm-sub, :scope > .panel .sect-body > p.hf-giris, :scope > .panel .analiz-body > p.rp-note');
    if(intro){const details=document.createElement('details');details.className='iv-explain';const summary=document.createElement('summary');summary.textContent='Bu bölüm nasıl çalışır?';details.append(summary,intro);const parent=view.querySelector(':scope > .panel .sect-body, :scope > .panel .analiz-body');parent?.prepend(details);}
    if(chartViews.has(name)){
      const chart=document.createElement('section');chart.className='iv-chart';chart.setAttribute('aria-label','Gerçek veriden görsel özet');chart.innerHTML='<div class="iv-chart-head"><h2>Görsel özet</h2><span>Kaynak yükleniyor…</span></div><p class="iv-chart-empty">Veriler hazırlanıyor…</p>';
      flow.after(chart);
    }
    if(name==='uretilenler'||name==='katalog'){
      const gallery=document.createElement('section');gallery.className='iv-gallery';gallery.setAttribute('aria-label',name==='uretilenler'?'Son üretilen görseller':'Ürün görselleri');
      flow.after(gallery);
      const content=view.querySelector(':scope > .panel');let lastImages='';
      const updateGallery=()=>{
        const images=[...content.querySelectorAll('img[src]')].filter(img=>img.getAttribute('src')?.startsWith('/gonderi-gorsel/')||img.getAttribute('src')?.startsWith('/katalog-gorsel/')).slice(0,6);
        const key=images.map(img=>img.getAttribute('src')).join('|');if(key===lastImages)return;lastImages=key;
        gallery.replaceChildren();gallery.hidden=!images.length;if(!images.length)return;
        const heading=document.createElement('div');heading.className='iv-gallery-head';const h=document.createElement('h2');h.textContent=name==='uretilenler'?'Son görseller':'Katalogdan seçmeler';const note=document.createElement('span');note.textContent='Kaydedilmiş görseller';heading.append(h,note);gallery.append(heading);
        const grid=document.createElement('div');grid.className='iv-gallery-grid';gallery.append(grid);
        images.forEach(img=>{
          const link=document.createElement('a');link.className='iv-gallery-card';link.href=img.getAttribute('src');link.target='_blank';link.rel='noopener';
          const thumb=document.createElement('img');thumb.src=img.getAttribute('src');thumb.alt=img.alt||'Kaydedilmiş görsel';thumb.loading='lazy';
          const label=document.createElement('span');const card=img.closest('.ur-kart,.kat-kart,.kat-urun,.kat-satir');const raw=card?.innerText?.split('\n').map(x=>x.trim()).find(Boolean)||img.getAttribute('src').split('/').pop();label.textContent=raw.replaceAll('-', ' ').slice(0,46);
          link.append(thumb,label);grid.append(link);
        });
      };
      new MutationObserver(updateGallery).observe(content,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});updateGallery();
    }
    new MutationObserver(()=>{if(!view.hidden && !app.hidden) activate(name,view);}).observe(view,{attributes:true,attributeFilter:['hidden']});
  }

  async function get(path){const response=await fetch(path,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!response.ok)throw new Error(String(response.status));return response.json();}
  function showBars(view,title,note,items){
    const box=view.querySelector('.iv-chart');if(!box)return;
    box.replaceChildren();const head=document.createElement('div');head.className='iv-chart-head';
    const h=document.createElement('h2');h.textContent=title;const source=document.createElement('span');source.textContent='Gerçek kayıtlardan';head.append(h,source);box.append(head);
    if(!items.length){const p=document.createElement('p');p.className='iv-chart-empty';p.textContent='Bu grafik için henüz kayıt yok.';box.append(p);return;}
    const max=Math.max(1,...items.map((x)=>x[1]));const graph=document.createElement('div');graph.className='iv-bars';graph.setAttribute('role','img');graph.setAttribute('aria-label',title+': '+items.map(x=>x[0]+' '+x[1]).join(', '));
    items.forEach(([label,value])=>{const row=document.createElement('div');row.className='iv-bar-row';const name=document.createElement('span');name.textContent=label;const track=document.createElement('span');track.className='iv-bar-track';const bar=document.createElement('span');bar.className='iv-bar-fill';bar.style.width=(value?Math.max(3,value/max*100):0)+'%';track.append(bar);const amount=document.createElement('strong');amount.textContent=String(value);row.append(name,track,amount);graph.append(row);});
    const caption=document.createElement('p');caption.className='iv-chart-note';caption.textContent=note;box.append(graph,caption);
  }
  function error(view){const p=view.querySelector('.iv-chart-empty');const head=view.querySelector('.iv-chart-head span');if(head)head.textContent='Şu anda alınamadı';if(p)p.textContent='Görsel özet yüklenemedi. Aşağıdaki bölümden kayıtları yine inceleyebilirsiniz.';}
  async function activate(name,view){
    if(!chartViews.has(name))return;
    const last=loaded.get(name)||0;if(Date.now()-last<30000)return;loaded.set(name,Date.now());
    try{
      if(name==='satislar'){
        const body=await get('/api/satislar');const orders=Array.isArray(body.siparisler)?body.siparisler:[];const byMonth=new Map();
        orders.forEach(o=>{const key=String(o.gun||'').slice(0,7);if(/^\d{4}-\d{2}$/.test(key))byMonth.set(key,(byMonth.get(key)||0)+1);});
        const months=[...byMonth].sort((a,b)=>a[0].localeCompare(b[0])).slice(-6).map(([key,n])=>[new Intl.DateTimeFormat('tr-TR',{month:'short',year:'numeric'}).format(new Date(key+'-01T12:00:00')),n]);
        showBars(view,'Kaydedilen gönderiler / ay','Yalnız bu sisteme alınmış gönderiler gösterilir; toplam şirket cirosu değildir.',months);
      } else if(name==='fiyat'){
        const body=await get('/api/fiyat-matrisi');const rows=Array.isArray(body.rows)?body.rows:[];const groups=[['Zarar','ZARAR'],['Kritik','KRITIK'],['Düşük marj','DUSUK'],['Uygun','OK'],['Eksik veri',null]];
        const missing=new Set(['KOMISYON_YOK','MALIYET_YOK','FIYAT_YOK']);showBars(view,'Fiyat satırlarının durumu','Bir ürün birden fazla platformda bulunabilir; sayılar platform satırlarını gösterir.',rows.length?groups.map(([label,key])=>[label,rows.filter(r=>key?r.marj_uyari===key:missing.has(r.marj_uyari)).length]):[]);
      } else if(name==='eticaret'){
        const body=await get('/api/urun-alanlari');const rows=Array.isArray(body.rows)?body.rows:[];const counts=new Map();rows.forEach(r=>counts.set(r.durum||'Belirsiz',(counts.get(r.durum||'Belirsiz')||0)+1));
        const labels={FARKLI:'Farklı',AYNI:'Aynı',SADECE_WIX:'Yalnız Wix',YALNIZ_WIX:'Yalnız Wix',SADECE_TRENDYOL:'Yalnız Trendyol',YALNIZ_TRENDYOL:'Yalnız Trendyol',IKISINDE_DE_YOK:'İkisinde de yok'};
        showBars(view,'Ürün alanlarının karşılaştırması','Her satır bir ürün alanıdır; fark, tek başına hata anlamına gelmez.',[...counts].sort((a,b)=>b[1]-a[1]).slice(0,6).map(([key,n])=>[labels[String(key).toUpperCase()]||String(key).replaceAll('_',' ').toLocaleLowerCase('tr-TR'),n]));
      } else if(name==='isler'){
        const body=await get('/api/isler');const s=body.sayilar||{};const entries=[['Sırada',s.bekleyen],['Hazırlanıyor',s.calisan],['Bitti',s.biten],['Kontrol gerekli',s.hata]].filter(([,n])=>n!==null&&n!==undefined&&Number.isFinite(Number(n))).map(([label,n])=>[label,Number(n)]);
        showBars(view,'Görsel üretim kuyruğu','Kayıt sayıları iş kuyruğundan alınır; hazırlanan görsel sayısı değildir.',entries);
      } else if(name==='kargo'){
        const body=await get('/api/kargo');const rows=Array.isArray(body.gonderiler)?body.gonderiler:[];
        showBars(view,'Gönderilerin yolu','Her gönderi yalnız bir aşamada sayılır.',rows.length?[['Barkod bekliyor',rows.filter(g=>!g.barkod).length],['Hazır',rows.filter(g=>g.barkod&&!g.kargoya_verildi).length],['Yolda',rows.filter(g=>g.kargoya_verildi&&!g.teslim_edildi).length],['Teslim edildi',rows.filter(g=>g.teslim_edildi).length]]:[]);
      } else if(name==='musteri'){
        const body=await get('/api/musteri');const total=Number(body.toplam_musteri);const repeat=Number(body.tekrar_eden);
        showBars(view,'Müşteri ilişkisi','Tekrar eden müşteri, birden fazla sipariş kaydı olan kişidir.',Number.isFinite(total)&&Number.isFinite(repeat)?[['Bir kez görünen',Math.max(0,total-repeat)],['Tekrar eden',repeat]]:[]);
      } else if(name==='sistem'){
        const body=await get('/api/sistem');const machines=body?.makineler||{};const statuses=Object.entries({Sunucu:machines.sunucu,'PC-1':machines.pc1,'PC-2':machines.pc2}).filter(([,m])=>m&&typeof m==='object').map(([label,m])=>[label,m.durum==='TAZE'?1:0]);
        showBars(view,'Ölçüm güncelliği','1 = güncel ölçüm alındı. 0 = güncel ölçüm yok; makinenin kapalı olduğunu göstermez.',statuses);
      }
    }catch(_){loaded.delete(name);error(view);}
  }
  if(!app.hidden){const active=Object.keys(PAGES).find(name=>{const v=document.getElementById('view'+ids[name]);return v&&!v.hidden;});if(active)activate(active,document.getElementById('view'+ids[active]));}
})();
