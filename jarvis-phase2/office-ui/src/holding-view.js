import { displayText } from './turkish.js';
import { familyName } from './labels.js';
function el(tag,text,cls=''){const n=document.createElement(tag);n.textContent=displayText(text);n.className=cls;return n;}
const number=value=>value==null?'Belirsiz':new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(value);
const when=value=>{const d=new Date(value);return value&&!Number.isNaN(d.valueOf())?d.toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'}):'Zaman bilgisi yok';};
export async function openHolding(departments,onSelect){
 const dialog=document.getElementById('holdingDialog'), body=document.getElementById('holdingBody');
 const previousFocus=document.activeElement;
 dialog.hidden=false;body.replaceChildren(el('p','Kaynaklar okunuyor…'));
 const close=document.getElementById('closeHolding');close.onclick=()=>{dialog.hidden=true;previousFocus?.focus();};close.focus();
 let data;
 try {
  const response=await fetch('/api/panel/holding',{credentials:'same-origin',headers:{Accept:'application/json'}});
  if(!response.ok)throw Error('Holding verileri alınamadı. Oturumu ve kaynakları kontrol edin.');
  data=await response.json();
 } catch(error){body.replaceChildren(el('p',error.message));return;}
 body.replaceChildren();
 body.append(el('p',`Kontrol: ${when(data.generated_at)} · Kayıtları inceler; dış işlem yapmaz.`,'holding-note'));
 const tabs=el('nav','','holding-tabs'), content=el('section','','holding-content');
 tabs.setAttribute('aria-label','Holding görünümleri');body.append(tabs,content);
 const showDepartment=code=>{dialog.hidden=true;onSelect(code,null,true);};
 function organisation(){
  const org=data.organisation||{};
  content.append(el('p',org.note||org.error||'Şirket/marka atamaları kaynak kaydından gelir.','holding-note'));
  const entities=new Map((org.entities||[]).map(e=>[e.id,e]));
  for(const entity of [...(org.entities||[]).filter(e=>(org.groups||[]).some(g=>g.entity_id===e.id)),{id:null,name:'Ortak / şirket ataması yapılmamış'}]){
   const groups=(org.groups||[]).filter(g=>g.entity_id===entity.id);
   if(!groups.length)continue;
   const path=[];let cur=entity;const seen=new Set();
   while(cur&&!seen.has(cur.id)){seen.add(cur.id);path.unshift(cur.name);cur=entities.get(cur.parent_id);}
   content.append(el('h3',path.join(' → ')));
   const grid=el('div','','holding-grid');content.append(grid);
   for(const group of groups){
    const card=el('article','','holding-card');card.append(el('h4',familyName(group.family)));
    for(const code of group.departments){
     const d=departments.find(x=>x.kod===code);const b=el('button',`${d?.ad||code} · ${d?.kadro?.length??'—'} üye`);b.type='button';b.onclick=()=>showDepartment(code);card.append(b);
    }grid.append(card);
   }
  }
  content.append(el('p','Şirket/marka ataması olmayan birimler gizlenmez. Organizasyon düzeni veri erişim yetkisi vermez.','holding-note'));
 }
 function work(){
  content.append(el('p',data.note,'holding-note'));
  for(const [title,rows,type] of [['Gündem',data.agenda||[],'agenda'],['Açık iş kayıtları',data.open_work||[],'work']]){
   content.append(el('h3',`${title} · gösterilen ${rows.length} kayıt`));
   if(!rows.length)content.append(el('p','Kayıt bulunamadı; kaynak durumu aşağıda gösterilir.'));
   for(const row of rows){
    const card=el('article','','holding-card');
    card.append(el('strong',type==='agenda'?row.soru:row.anahtar),el('p',type==='agenda'?row.neden_onemli:row.detay));
    card.append(el('small',type==='agenda'?`#${row.soru_id} · ${row.oncelik||'Öncelik yok'} · ${row.durum||'Durum bilinmiyor'} · Oluşturulma: ${when(row.olusturma)}`:`${row.tur||'Tür yok'} · Kaynak zamanı: ${when(row.zaman)}`));
    if(type==='work')card.append(el('p',row.yapilacak||'Sonraki adım belirtilmemiş'));
    const code=String(row.hedef||'');const d=departments.find(x=>x.kod===code);
    if(d){const b=el('button',`${d.ad||code} birimini aç`);b.type='button';b.onclick=()=>showDepartment(code);card.append(b);}
    else if(type==='agenda')card.append(el('small',`Hedef: ${code||'Belirtilmemiş'} · Departman ataması doğrulanmadı`));
    content.append(card);
   }
  }
 }
 function products(){
  content.append(el('p','Kayıtlı ürün gelirleri ve maliyet kapsamı. Tahmini veya doğrulanmamış maliyetle kesin kâr ve sermaye tahsisi sonucu üretilmez. Tutarların para birimi bu kaynakta ayrı alan olarak sunulmuyor.','holding-note'));
  const table=el('table','','holding-table'),head=el('thead'),tr=el('tr');
  for(const label of ['Ürün','Net ciro kaydı','Brüt marj kaydı','Maliyet kapsamı','Maliyet niteliği'])tr.append(el('th',label));
  head.append(tr);table.append(head);const tbody=el('tbody');table.append(tbody);
  for(const row of data.portfolio||[]){const r=el('tr');for(const value of [row.name,number(row.revenue),number(row.margin_recorded),row.coverage==null?'Belirsiz':number(row.coverage)+'%',row.reliability+' · '+row.cost_source])r.append(el('td',value));tbody.append(r);}
  content.append(table);
  if(!tbody.children.length)content.append(el('p','Ürün portföyü verisi alınamadı veya kaynak boş.'));
 }
 const views=[['Organizasyon',organisation],['İş takibi',work],['Ürün portföyü',products]];
 for(const [title,render] of views){const b=el('button',title);b.type='button';b.onclick=()=>{content.replaceChildren();for(const x of tabs.children)x.setAttribute('aria-pressed',String(x===b));render();};tabs.append(b);}
 tabs.firstChild.click();
 const sources=el('details'),sum=el('summary','Kaynak durumları');sources.append(sum);
 for(const s of data.sources||[])sources.append(el('p',`${s.query}: ${s.status==='read'?`${s.count} kayıt okundu`:'Okunamadı'} · ${s.source||'Kaynak yok'}`));body.append(sources);
 const ads=data.google_ads_targets;
 if(ads)body.append(el('p',`Google Ads hedef hesapları: ${(ads.accounts||[]).join(' / ')} · ${ads.email} · Bağlantı henüz doğrulanmadı.`,'holding-note'));
}
