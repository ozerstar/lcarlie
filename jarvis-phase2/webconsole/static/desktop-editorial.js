(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const app = $('appView');
  if (!app || !$('edDate')) return;

  $('edNavSearch')?.addEventListener('click', () => $('quickSearch')?.click());
  const heroVoice = $('edVoice');
  const coreVoice = $('coreBtn');
  const coreHint = $('coreHint');
  const syncVoice = () => {
    if (!heroVoice || !coreVoice || !coreHint) return;
    const hint = coreHint.textContent.trim();
    const unsupported = hint === 'SES YOK';
    const listening = coreVoice.getAttribute('aria-pressed') === 'true';
    heroVoice.disabled = unsupported;
    heroVoice.setAttribute('aria-pressed', String(listening));
    heroVoice.setAttribute('aria-label', listening ? 'Jarvis sesli konuşmayı durdur' : 'Jarvis ile sesli konuşmayı başlat');
    $('edVoiceStatus').textContent = unsupported ? 'Sesli görüşme bu tarayıcıda kullanılamıyor'
      : hint === 'DÜŞÜNÜYOR' || hint === 'CEVAP HAZIRLANIYOR' ? 'Yanıt hazırlanıyor'
      : hint === 'SUSTURMAK İÇİN BAS' ? 'Jarvis konuşuyor · durdurmak için dokun'
      : listening ? 'Dinliyor · bitirmek için dokun' : 'Konuşmak için dokun';
  };
  heroVoice?.addEventListener('click', () => coreVoice?.click());
  if (coreVoice && coreHint) {
    new MutationObserver(syncVoice).observe(coreVoice, {attributes:true, attributeFilter:['aria-pressed']});
    new MutationObserver(syncVoice).observe(coreHint, {childList:true, characterData:true, subtree:true});
    syncVoice();
  }

  function navigate(view) {
    document.querySelector(`#mainNav .nav-item[data-view="${view}"]`)?.click();
  }
  document.querySelectorAll('[data-ed-view]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.edView)));
  document.querySelectorAll('[data-ed-ask]').forEach((button) => button.addEventListener('click', () => {
    const input = $('chatInput');
    input.value = button.dataset.edAsk;
    input.focus();
    input.scrollIntoView({block:'nearest'});
  }));
  const nav = $('mainNav');
  nav?.addEventListener('click', (event) => {
    if (event.target.closest('.nav-item')) nav.classList.remove('is-acik');
  });

  const date = new Date();
  const hour = date.getHours();
  $('edGreeting').textContent = hour < 11 ? 'Günaydın.' : hour < 18 ? 'İyi günler.' : 'İyi akşamlar.';
  $('edDate').textContent = new Intl.DateTimeFormat('tr-TR', {weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(date);
  $('edToday').textContent = new Intl.DateTimeFormat('tr-TR',{day:'numeric',month:'long'}).format(date);

  function calendar(reminders) {
    const now = new Date();
    $('edMonth').textContent = new Intl.DateTimeFormat('tr-TR',{month:'long',year:'numeric'}).format(now);
    const first = new Date(now.getFullYear(),now.getMonth(),1);
    const days = new Date(now.getFullYear(),now.getMonth()+1,0).getDate();
    const offset = (first.getDay()+6)%7;
    const dates = new Set(reminders.map((r) => {
      const d = new Date(r.due_at);
      return Number.isNaN(d.getTime()) ? -1 : d.getMonth()===now.getMonth() && d.getFullYear()===now.getFullYear() ? d.getDate() : -1;
    }));
    $('edCalendar').replaceChildren();
    for(let i=0;i<offset;i++) $('edCalendar').append(document.createElement('span'));
    for(let day=1;day<=days;day++) {
      const cell=document.createElement('span'); cell.textContent=String(day);
      if(day===now.getDate()) cell.classList.add('ed-today');
      if(dates.has(day)) cell.classList.add('ed-has-reminder');
      $('edCalendar').append(cell);
    }
  }
  calendar([]);

  async function get(path) {
    const res=await fetch(path,{credentials:'same-origin',headers:{Accept:'application/json'}});
    if(!res.ok) throw new Error(String(res.status));
    return res.json();
  }
  function row(container,title,sub) {
    const item=document.createElement('div'); item.className='ed-rail-item';
    const strong=document.createElement('strong'); strong.textContent=title;
    const small=document.createElement('small'); small.textContent=sub;
    item.append(strong,small); container.append(item);
  }
  function count(value,id) { $(id).textContent=Number.isFinite(value)?String(value):'—'; }
  async function refresh() {
    if(app.hidden) return;
    const results=await Promise.allSettled([
      get('/api/isler'),get('/api/actions'),get('/api/mobile/reminders'),get('/api/satislar'),get('/api/status'),get('/api/ekip-ozet'),
      get('/api/reklam-yoneticisi?aralik=bugun&ozet=1')
    ]);
    if(app.hidden) return;
    const data=results.map((r)=>r.status==='fulfilled'?r.value:null);
    const [jobs,proposals,reminders,sales,status,ekip,gun]=data;
    const counts=jobs?.sayilar || {};
    const pending=Array.isArray(proposals?.pending)?proposals.pending:null;
    const reminderList=Array.isArray(reminders?.reminders)?reminders.reminders:null;
    const waiting=['bekleyen','calisan','hata'].every((key)=>Number.isFinite(Number(counts[key])))
      ? Number(counts.bekleyen)+Number(counts.calisan)+Number(counts.hata):null;
    count(waiting,'edWaiting'); count(jobs?Number(counts.biten):null,'edDone');
    // Karar sayısı iki kaynaktan: öneri kuyruğu + tasarım onayları (asistan sayfasında ikisi birlikte görünür).
    const tasarimOnay=Number.isFinite(Number(ekip?.tasarim_onay))?Number(ekip.tasarim_onay):0;
    const kararToplam=pending?pending.length+tasarimOnay:null;
    count(kararToplam,'edApprovals'); count(kararToplam,'edDecisionCount');
    $('edApprovalsSub').textContent=pending?`${pending.length} öneri · ${tasarimOnay} tasarım`:'Öneri ve tasarım onayları';
    count(ekip?Number(ekip.teslim_bugun):null,'edTeamDone'); count(ekip?Number(ekip.acik):null,'edTeamOpen');
    $('edTeamDoneSub').textContent=!ekip?'Ekip verisi okunamadı'
      : ekip.teslim_bugun?`${ekip.departman_bugun} departman · ${ekip.kismi_bugun} kısmi`:'Bugün henüz teslim yok';
    const today=new Date().toLocaleDateString('sv-SE');
    // 25.11: "Bugünkü sipariş" yalnız site siparişini sayıyordu (Trendyol vb. yoktu).
    // Tüm kanal sayısı reklam yöneticisinin satış defterinden gelir; okunamazsa eski yol.
    const gunOzet=gun&&gun.durum==='OK'&&gun.ozet&&gun.ozet.defter_durum==='OK'?gun.ozet:null;
    const orders=gunOzet&&Number.isFinite(Number(gunOzet.tum_siparis))?Number(gunOzet.tum_siparis)
      :Array.isArray(sales?.siparisler)?sales.siparisler.filter((o)=>String(o.gun||'').slice(0,10)===today).length:null;
    count(orders,'edOrders');
    bugunSeridi(gun,kararToplam,pending,tasarimOnay,today);
    const focus=kararToplam ? [`${kararToplam} karar seni bekliyor`,'Öneri ve tasarım onaylarını inceleyip karar ver.','Onayları incele','asistan']
      : waiting>0 ? [`${waiting} iş takip ediliyor`,'Sıradaki ve hazırlanan işlerin durumuna göz at.','İşleri aç','isler']
      : reminderList?.length ? [`${reminderList.length} hatırlatıcı kayıtlı`,'Yaklaşan planını sağdaki listeden görebilirsin.','Asistana sor','asistan']
      : ['Bugün için bekleyen karar görünmüyor','Yeni bir konu varsa Jarvis ile başlayabilirsin.','Asistanı aç','asistan'];
    $('edFocusTitle').textContent=focus[0]; $('edFocusDetail').textContent=focus[1];
    $('edFocusAction').firstChild.textContent=focus[2]+' '; $('edFocusAction').dataset.edView=focus[3];
    $('edUpdated').textContent=new Intl.DateTimeFormat('tr-TR',{hour:'2-digit',minute:'2-digit'}).format(new Date())+' güncellendi';
    const jobBox=$('edJobs');jobBox.replaceChildren();
    if(!jobs) jobBox.innerHTML='<p>İşler şu anda okunamadı.</p>';
    else if(!Array.isArray(jobs.isler)||!jobs.isler.length) jobBox.innerHTML='<p>İş kuyruğunda kayıt yok.</p>';
    else jobs.isler.slice(0,4).forEach((job)=>{
      const line=document.createElement('div');line.className='ed-row';
      const dot=document.createElement('span');dot.className='ed-dot';
      const title=document.createElement('span');title.textContent=JarvisMetin.jobTitle(job);
      const state=document.createElement('small');state.textContent=({bekleyen:'Sırada',calisan:'Hazırlanıyor',biten:'Bitti',hata:'Kontrol gerekli'})[job.asama]||'Durum bilinmiyor';
      line.append(dot,title,state);jobBox.append(line);
    });
    const remindersBox=$('edReminders');remindersBox.replaceChildren();
    count(reminderList?.length,'edReminderCount');calendar(reminderList||[]);
    if(!reminderList) remindersBox.innerHTML='<p>Hatırlatıcılar okunamadı.</p>';
    else if(!reminderList.length) remindersBox.innerHTML='<p>Henüz hatırlatıcı eklenmemiş.</p>';
    else reminderList.slice().sort((a,b)=>new Date(a.due_at)-new Date(b.due_at)).slice(0,3).forEach((item)=>{
      const d=new Date(item.due_at);row(remindersBox,item.text||'Hatırlatıcı',Number.isNaN(d.getTime())?'Tarih yok':new Intl.DateTimeFormat('tr-TR',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(d));
    });
    const decisions=$('edDecisions');decisions.replaceChildren();
    if(!pending) decisions.innerHTML='<p>Onaylar okunamadı.</p>';
    else if(!pending.length&&!tasarimOnay) decisions.innerHTML='<p>Bekleyen karar yok.</p>';
    else {
      pending.slice(0,3).forEach((p)=>row(decisions,JarvisMetin.safeTitle(p?.payload?.reason||p?.title,'İncelenecek yeni karar'),'İncelemek için onaylara git'));
      if(tasarimOnay) row(decisions,`${tasarimOnay} tasarım onayınızı bekliyor`,'Asistan › Onaylar ve imzalar');
    }
    $('edSystemState').textContent=status?'Sistem verileri alındı':'Sistem durumu okunamadı';
    document.querySelector('.ed-system-light')?.classList.toggle('is-warn',!status);
  }
  /* "Bugün" şeridi (25.11.2026): satış, reklam harcaması, bekleyen onay, uyarı.
     Rakam yalnız API'den gelir; okunamayan alan "—" ve sebebiyle kalır. */
  function tl(n){return Number(n).toLocaleString('tr-TR',{maximumFractionDigits:Math.abs(n)>=100?0:2})+' TL';}
  function kpi(id,deger,alt,ton){
    const kutu=$(id); if(!kutu) return;
    kutu.querySelector('strong').textContent=deger; kutu.querySelector('small').textContent=alt;
    if(ton) kutu.dataset.ton=ton; else delete kutu.dataset.ton;
  }
  function bugunSeridi(gun,kararToplam,pending,tasarimOnay,today){
    if(!$('gnSatis')) return;
    const ok=gun&&gun.durum==='OK'; const o=ok?gun.ozet||{}:null;
    if(!ok) kpi('gnSatis','—','Satış defteri şu anda okunamadı');
    else if(o.defter_durum!=='OK'||o.tum_siparis===null||o.tum_siparis===undefined) kpi('gnSatis','—','Satış defteri okunamadı');
    else {
      const ciro=Number(o.tum_ciro||0);
      const alt=ciro>0?'Tüm kanallar · '+tl(ciro):(o.tum_siparis>0?'Tüm kanallar · tutar pazaryerinden henüz gelmedi':'Tüm kanallar · henüz sipariş yok');
      kpi('gnSatis',o.tum_siparis+' sipariş',alt,o.tum_siparis>0?'iyi':null);
    }
    if(!ok) kpi('gnReklam','—','Reklam verisi okunamadı');
    else {
      const meta=(gun.platformlar||[]).find((p)=>p.kod==='meta');
      const yas=gun.olcum&&Number.isFinite(Number(gun.olcum.meta_yas_dk))?Number(gun.olcum.meta_yas_dk):null;
      const alt='Meta · '+(meta&&meta.acik!==null&&meta.acik!==undefined?meta.acik+' reklam açık':'')+(yas!==null?' · '+yas+' dk önce ölçüldü':'');
      const sifirSiparis=o.harcama>0&&o.tum_siparis===0;
      kpi('gnReklam',tl(o.harcama||0),alt,sifirSiparis&&o.harcama>=500?'dikkat':null);
    }
    if(kararToplam===null) kpi('gnOnay','—','Onaylar okunamadı');
    else kpi('gnOnay',String(kararToplam),pending.length+' öneri · '+tasarimOnay+' tasarım',kararToplam>0?'dikkat':null);
    const liste=$('gnUyarilar'); liste.replaceChildren();
    if(!ok){kpi('gnUyari','—','Uyarılar okunamadı'); liste.hidden=true;}
    else {
      const bugunku=(gun.uyarilar||[]).filter((u)=>String(u.zaman||'').slice(0,10)===today);
      const sira={KRITIK:0,UYARI:1,BILGI:2};
      bugunku.sort((a,b)=>(sira[a.seviye]??3)-(sira[b.seviye]??3));
      const ciddi=bugunku.filter((u)=>u.seviye==='KRITIK'||u.seviye==='UYARI');
      const kritik=bugunku.some((u)=>u.seviye==='KRITIK');
      const bilgi=bugunku.length-ciddi.length;
      kpi('gnUyari',String(ciddi.length),ciddi.length?(kritik?'Kritik uyarı var — reklamlara bak':'Uyarı var — reklamlara bak')
        :(bilgi?'Kritik uyarı yok · '+bilgi+' bilgi notu':'Bugün uyarı yok'),kritik?'kritik':ciddi.length?'dikkat':null);
      const ad={KRITIK:'Kritik',UYARI:'Uyarı',BILGI:'Bilgi'};
      bugunku.slice(0,3).forEach((u)=>{
        const li=document.createElement('li'); li.dataset.seviye=u.seviye||'BILGI'; li.dataset.originalText='1'; // metin dönüştürücü parantezi "—" yapıyordu
        const b=document.createElement('b'); b.textContent=ad[u.seviye]||'Not';
        const sp=document.createElement('span'); sp.textContent=String(u.metin||'').replace(/\s*\($/,'');
        li.append(b,sp); liste.append(li);
      });
      liste.hidden=!bugunku.length;
    }
    $('gnOlcum').textContent=ok&&gun.olcum&&gun.olcum.defter?'Satış defteri '+new Intl.DateTimeFormat('tr-TR',{hour:'2-digit',minute:'2-digit'}).format(new Date(gun.olcum.defter))+' itibarıyla':'';
  }
  document.querySelectorAll('[data-gn-view]').forEach((b)=>b.addEventListener('click',()=>{navigate(b.dataset.gnView);}));
  const watcher=new MutationObserver(()=>{if(!app.hidden) refresh();});
  watcher.observe(app,{attributes:true,attributeFilter:['hidden']});
  if(!app.hidden) refresh();
  setInterval(()=>{if(!document.hidden)refresh();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
