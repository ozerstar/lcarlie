(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const app = $('appView');
  if (!app || !$('edDate')) return;

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
      get('/api/isler'),get('/api/actions'),get('/api/mobile/reminders'),get('/api/satislar'),get('/api/status')
    ]);
    if(app.hidden) return;
    const data=results.map((r)=>r.status==='fulfilled'?r.value:null);
    const [jobs,proposals,reminders,sales,status]=data;
    const counts=jobs?.sayilar || {};
    const pending=Array.isArray(proposals?.pending)?proposals.pending:null;
    const reminderList=Array.isArray(reminders?.reminders)?reminders.reminders:null;
    const waiting=['bekleyen','calisan','hata'].every((key)=>Number.isFinite(Number(counts[key])))
      ? Number(counts.bekleyen)+Number(counts.calisan)+Number(counts.hata):null;
    count(waiting,'edWaiting'); count(jobs?Number(counts.biten):null,'edDone');
    count(pending?.length,'edApprovals'); count(pending?.length,'edDecisionCount');
    const today=new Date().toLocaleDateString('sv-SE');
    const orders=Array.isArray(sales?.siparisler)?sales.siparisler.filter((o)=>String(o.gun||'').slice(0,10)===today).length:null;
    count(orders,'edOrders');
    const focus=pending?.length ? [`${pending.length} karar seni bekliyor`,'Önerileri inceleyip uygun olanlara karar ver.','Onayları incele','gorevler']
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
    else if(!pending.length) decisions.innerHTML='<p>Bekleyen karar yok.</p>';
    else pending.slice(0,3).forEach((p)=>row(decisions,JarvisMetin.safeTitle(p?.payload?.reason||p?.title,'İncelenecek yeni karar'),'İncelemek için onaylara git'));
    $('edSystemState').textContent=status?'Sistem verileri alındı':'Sistem durumu okunamadı';
    document.querySelector('.ed-system-light')?.classList.toggle('is-warn',!status);
  }
  const watcher=new MutationObserver(()=>{if(!app.hidden) refresh();});
  watcher.observe(app,{attributes:true,attributeFilter:['hidden']});
  if(!app.hidden) refresh();
  setInterval(()=>{if(!document.hidden)refresh();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
