/* Presentation branding only: never changes routes, credentials, identifiers or inputs. */
(()=>{'use strict';
 const brand=value=>String(value||'').replace(/\bJarvis[’']e\b/g,'L’carlie’ye').replace(/\bJarvis[’']i\b/g,'L’carlie’yi').replace(/(^|[^\w./@-])(?:Jarvis|JARVIS|jarvis)(?=$|[^\w./@-])/g,'$1L’carlie');
 const excluded=element=>!element||element.closest('script,style,code,pre,[contenteditable="true"],.chat-msg.user,.message.user,.bubble.user,.bubble.me,[data-role="user"],[data-original-text]');
 function clean(node){
  if(node.nodeType===3){if(!excluded(node.parentElement)&&!node.parentElement.closest('input,textarea')){const next=brand(node.nodeValue);if(next!==node.nodeValue)node.nodeValue=next;}return;}
  if(node.nodeType!==1||excluded(node))return;
  for(const attr of ['title','aria-label','placeholder','alt']){const old=node.getAttribute(attr);if(old){const next=brand(old);if(next!==old)node.setAttribute(attr,next);}}
  for(const child of node.childNodes)clean(child);
 }
 function start(){document.documentElement.dataset.lcarlieTheme='botanical';document.title=brand(document.title);clean(document.body);
  new MutationObserver(records=>{for(const record of records){if(record.type==='characterData')clean(record.target);else if(record.type==='attributes')clean(record.target);else for(const node of record.addedNodes)clean(node);}}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder','alt']});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();

/* Shared navigation uses the existing page controls; no business records are changed. */
(() => {
  'use strict';
  function start() {
    if (document.getElementById('lcNavigation')) return;
    const mobile = location.pathname.startsWith('/mobile/');
    const home = () => mobile || matchMedia('(max-width:760px)').matches ? '/mobile/index.html' : '/';
    const sections = [
      ['home','Ana sayfa'],['analiz','Analiz'],['asistan','Asistan'],['raporlar','Raporlar'],
      ['gorevler','Görevler'],['fiyat','Fiyatlar'],['eticaret','E-ticaret'],['satislar','Satışlar'],
      ['kargo','Kargo'],['gelenkutusu','Gelen kutusu'],['musteri','Müşteriler'],['uretilenler','Üretilenler'],
      ['kreatifParti','Kreatif çalışmalar'],['reklam','Reklam'],['tasarim','Tasarım ve üretim'],
      ['ekip','Ekip'],['ajanlar','Ajanlar'],['hafiza','Hafıza'],['veri','Veri'],['katalog','Katalog'],
      ['saha','Saha'],['isler','İşler'],['sistem','Sistem'],['ayarlar','Ayarlar']
    ];
    const tabs = [['home','Ana sayfa'],['chat','Asistanla konuş'],['jobs','Görevler'],['approvals','Onaylar'],
      ['creative','Görseller'],['system','Sistem durumu'],['settings','Ayarlar'],['more','Diğer bölümler']];
    const routes = [['/cari.html','Cari hesaplar'],['/belgeler.html','Fiş ve faturalar'],['/office.html','L’carlie Ofisi'],['/image-jobs.html','Görsel işleri']];
    const desktop = !!document.getElementById('mainNav');
    const bar = document.createElement('nav');
    bar.id = 'lcNavigation';bar.setAttribute('aria-label','Sayfa gezinmesi');
    bar.innerHTML = '<button type="button" id="lcBack" aria-label="Önceki sayfaya dön">← <span>Geri</span></button><span id="lcPageLabel">L’carlie</span><button type="button" id="lcMenu" aria-haspopup="dialog" aria-expanded="false" aria-controls="lcMenuDialog"><span aria-hidden="true">☰</span> Menü</button>';
    const menu = document.createElement('dialog');menu.id='lcMenuDialog';menu.setAttribute('aria-labelledby','lcMenuTitle');
    menu.innerHTML='<div class="lc-menu-head"><h2 id="lcMenuTitle">L’carlie menüsü</h2><button type="button" id="lcMenuClose" aria-label="Menüyü kapat">Kapat ×</button></div><label class="lc-menu-search">Bölüm ara<input type="search" id="lcMenuSearch" placeholder="Örneğin cari, ofis, satış…" autocomplete="off"></label><nav id="lcMenuLinks" aria-label="Tüm bölümler"></nav><p id="lcMenuEmpty" hidden>Bu adla bir bölüm bulunamadı.</p>';
    document.body.prepend(bar);document.body.append(menu);document.documentElement.classList.add('lc-has-navigation');
    const back=bar.querySelector('#lcBack'), trigger=bar.querySelector('#lcMenu'), label=bar.querySelector('#lcPageLabel');
    const list=menu.querySelector('#lcMenuLinks'), search=menu.querySelector('#lcMenuSearch'), empty=menu.querySelector('#lcMenuEmpty');
    function closeMenu(){menu.close();trigger.setAttribute('aria-expanded','false');trigger.focus({preventScroll:true});}
    function addGroup(title, items, kind) {
      const group=document.createElement('section');group.className='lc-menu-group';
      const heading=document.createElement('h3');heading.textContent=title;group.append(heading);
      for(const [key,name] of items){
        const link=document.createElement('a');link.textContent=name;link.dataset.search=name.toLocaleLowerCase('tr-TR');
        link.href=kind==='view'?'/?view='+encodeURIComponent(key):kind==='tab'?'/mobile/index.html?tab='+key:key;
        link.dataset.kind=kind;link.dataset.key=key;
        link.addEventListener('click',event=>{
          const control=kind==='view'&&desktop?document.querySelector('#mainNav .nav-item[data-view="'+key+'"]'):
            kind==='tab'&&mobile?document.querySelector('[data-tab="'+key+'"]'):null;
          const authenticatedSurface=desktop?!document.getElementById('appView')?.hidden:mobile?!document.getElementById('app')?.hidden:true;
          if(control && !control.disabled && authenticatedSurface){event.preventDefault();closeMenu();control.click();}
        });group.append(link);
      }list.append(group);
    }
    if(mobile)addGroup('Mobil çalışma alanı',tabs,'tab');
    addGroup('Hesaplar ve ofis',routes,'route');
    addGroup('Bütün bölümler',mobile?sections.filter(([key])=>!['home','gorevler','sistem','ayarlar'].includes(key)):sections,'view');
    const currentView=()=>desktop?document.querySelector('#mainNav .nav-item.is-active')?.dataset.view:
      mobile?[...document.querySelectorAll('#app > .tab-panel:not([hidden])')].find(e=>e.id!=='chat-panel')?.id.replace(/-panel$/,''):null;
    let current=currentView(), trail=[], replaying=false;
    function sync(){
      const next=currentView();
      if(next&&next!==current){if(current&&!replaying)trail.push(current);current=next;}
      const title=(mobile?tabs:sections).find(([key])=>key===current)?.[1];
      label.textContent=title||routes.find(([url])=>url===location.pathname)?.[1]||'L’carlie';
      for(const link of list.querySelectorAll('a')){
        const active=(link.dataset.kind===(mobile?'tab':'view')&&link.dataset.key===current)||link.dataset.key===location.pathname;
        if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
      }
    }
    // Observe only the existing navigation state, not our own labels or menu.
    const observer=new MutationObserver(sync);
    if(desktop)observer.observe(document.getElementById('mainNav'),{subtree:true,attributes:true,attributeFilter:['class']});
    if(mobile)document.querySelectorAll('#app > .tab-panel').forEach(node=>observer.observe(node,{attributes:true,attributeFilter:['hidden']}));
    trigger.addEventListener('click',()=>{
      search.value='';for(const node of list.querySelectorAll('section,a'))node.hidden=false;empty.hidden=true;sync();
      menu.showModal();trigger.setAttribute('aria-expanded','true');search.focus();
    });
    menu.querySelector('#lcMenuClose').addEventListener('click',closeMenu);
    menu.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenu();}});
    menu.addEventListener('cancel',event=>{event.preventDefault();closeMenu();});
    menu.addEventListener('click',event=>{if(event.target===menu){const r=menu.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeMenu();}});
    search.addEventListener('input',()=>{
      const q=search.value.trim().toLocaleLowerCase('tr-TR');let found=0;
      for(const link of list.querySelectorAll('a')){link.hidden=!link.dataset.search.includes(q);if(!link.hidden)found++;}
      for(const group of list.querySelectorAll('section'))group.hidden=![...group.querySelectorAll('a')].some(a=>!a.hidden);
      empty.hidden=found>0;
    });
    back.addEventListener('click',()=>{
      if(mobile&&!document.getElementById('chat-panel')?.hidden){document.getElementById('chat-close')?.click();return;}
      if(desktop&&!document.getElementById('cmdBar')?.hidden){document.getElementById('chatClose')?.click();return;}
      sync();const previous=trail.pop();
      if(previous){
        const control=document.querySelector(desktop?'#mainNav .nav-item[data-view="'+previous+'"]':'[data-tab="'+previous+'"]');
        if(control){replaying=true;control.click();current=previous;sync();setTimeout(()=>{replaying=false;},0);return;}
      }
      let localPrevious=false;try{localPrevious=new URL(document.referrer).origin===location.origin;}catch(_){}
      if(localPrevious&&history.length>1)history.back();else location.assign(home());
    });
    sync();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
