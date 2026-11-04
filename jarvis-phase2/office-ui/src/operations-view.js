import {displayText,errorText} from './turkish.js';

const statuses={open:'Açık',progress:'Üzerinde çalışılıyor',blocked:'Girdi bekliyor',resolved:'Takip kapatıldı'};
const when=v=>{if(!v)return 'Henüz doğrulanmadı';const d=new Date(v);return Number.isNaN(d.getTime())?'Geçerli zaman bilgisi bulunmuyor':d.toLocaleString('tr-TR');};
const value=v=>v===null||v===undefined||!Number.isFinite(Number(v))?'Bilgi yok':new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(Number(v));
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=displayText(text);if(cls)e.className=cls;return e;}
function button(text,fn){const b=node('button',text);b.type='button';b.onclick=fn;return b;}

export class OperationsView{
 constructor({csrf,departments,scene,onChange}){
  Object.assign(this,{csrf,departments,scene,onChange});this.data=null;this.tab='work';this.department='';this.product='';this.request=null;
  this.dialog=node('dialog',undefined,'ops-dialog');this.dialog.setAttribute('aria-label','Şirket çalışma merkezi');
  document.body.append(this.dialog);this.dialog.addEventListener('close',()=>{this.scene()?.setSuspended(false);this.opener?.focus();});
 }
 async api(path,body){
  const response=await fetch(path,{credentials:'same-origin',signal:AbortSignal.timeout(90000),headers:{Accept:'application/json',...(body?{'Content-Type':'application/json','X-CSRF-Token':this.csrf()||''}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})}).catch(error=>{throw Error(errorText(error.message));});
  let data;try{data=await response.json();}catch{throw Error('Sunucu anlaşılır bir yanıt veremedi. Yeniden deneyin.');}
  if(!response.ok)throw Error(data.error||'İşlem tamamlanamadı. Sayfayı yenileyin.');return data;
 }
 async load(force=false){
  if(this.request)return this.request;
  if(!force&&this.data&&Date.now()-this.loadedAt<60000)return this.data;
  this.request=this.api('/api/panel/ofis').then(data=>{this.data=data;this.loadedAt=Date.now();this.scene()?.setOperations(data);this.onChange?.(data);return data;}).finally(()=>this.request=null);
  return this.request;
 }
 async open(tab='work',department='',product=''){
  this.tab=tab;this.department=department;this.product=product;this.opener=document.activeElement;
  if(!this.dialog.open){this.dialog.showModal();this.scene()?.setSuspended(true);}this.dialog.replaceChildren(node('p','Şirket kayıtları yükleniyor…'),button('Kapat',()=>this.dialog.close()));
  try{await this.load();this.render();}catch(e){this.dialog.replaceChildren(node('p',e.message),button('Yeniden dene',()=>this.open(tab,department,product)),button('Kapat',()=>this.dialog.close()));}
 }
 render(){
  const header=node('header',undefined,'ops-header');header.append(node('div','L’carlie · Çalışma merkezi'),button('Kapat',()=>this.dialog.close()));
  const nav=node('nav',undefined,'ops-tabs');nav.setAttribute('aria-label','Çalışma merkezi bölümleri');
  for(const [key,label] of [['work','Çalışma tahtası'],['connections','Bağlantılar'],['hr','İK takibi'],['products','Ürünler']]){const b=button(label,()=>{this.tab=key;this.product='';this.render();});b.setAttribute('aria-pressed',this.tab===key);nav.append(b);}
  const filters=node('div',undefined,'ops-filters');const select=node('select');select.setAttribute('aria-label','Birim filtresi');select.append(new Option('Bütün birimler',''));
  for(const d of this.departments())select.append(new Option(d.ad,d.kod));select.value=this.department;select.onchange=()=>{this.department=select.value;this.render();};
  const refresh=button('Kayıtları yenile',async()=>{refresh.disabled=true;try{await this.load(true);this.render();}catch(e){this.notice(e.message);}finally{refresh.disabled=false;}});
  filters.append(select,refresh,node('small','Okuma: '+when(this.data.generated_at)));
  const content=node('div',undefined,'ops-content');this.content=content;
  this.dialog.replaceChildren(header,nav,filters,content);
  for(const r of Object.values(this.data.reads||{}))if(!r.ok)content.append(node('p',displayText(r.source)+' okunamadı. Bu bölümdeki sonuçlar eksik olabilir.','ops-warning'));
  if(this.tab==='connections')this.connections();else if(this.tab==='products')this.products();else this.work(this.tab==='hr');
 }
 notice(text){let n=this.dialog.querySelector('.ops-notice');if(!n){n=node('p',undefined,'ops-notice');n.setAttribute('role','status');this.dialog.append(n);}n.textContent=displayText(text);}
 work(hr){
  this.content.append(node('h2',hr?'İnsan kaynakları ve iş takibi':'Birim çalışma tahtası'),node('p',this.data.limits,'ops-muted'));
  const items=this.data.items.filter(i=>!this.department||i.department===this.department);
  const open=items.filter(i=>i.status!=='resolved');
  const summary=node('div',undefined,'ops-metrics');for(const [label,count] of [['Açık takip',open.length],['Sorumlu eksik',open.filter(i=>!i.owner).length],['Tarihi eksik',open.filter(i=>!i.due).length],['Geciken',open.filter(i=>i.overdue).length]])summary.append(node('strong',count+' · '+label));this.content.append(summary);
  if(this.department)this.content.append(button('Birim müdürüne dön',()=>{this.dialog.close();this.scene()?.focus(this.department);}));
  if(!hr&&(!this.department||this.department==='DECISION_MEM')){const decisions=node('details');decisions.append(node('summary','Şirket kararları · '+(this.data.decisions||[]).length+' kaynak kaydı'));for(const d of this.data.decisions||[]){const record=node('details',undefined,'ops-card');record.append(node('summary',displayText(d.karar_tipi||'Şirket kararı')+' · '+displayText(d.durum||'Durum belirtilmemiş')));for(const [label,key] of [['Kayıt zamanı','observed_at'],['Ürün','urun'],['Kanal','kanal'],['Onay hazırlığı','onay_hazirligi'],['İç denetim sonucu','red_team_sonucu'],['Kanıt kalitesi','kanit_kalitesi']])record.append(node('p',label+': '+(d[key]??'Bilgi yok')));record.append(node('small','Kaynak: şirket karar ve onay kayıtları'));decisions.append(record);}this.content.append(decisions);}
  const list=node('div',undefined,'ops-grid');this.content.append(list);
  if(!items.length)list.append(node('p','Bu birime atanmış takip kaydı bulunmuyor. Şirket genelindeki sahipsiz işleri Bütün birimler görünümünden atayabilirsiniz.'));
  for(const item of items.filter(i=>!hr||i.issues.length||['failure','staff','source'].includes(i.kind)||i.status==='resolved')){
   const card=node('article',undefined,'ops-card');card.append(node('small',(item.new?'Yeni veya değişen kayıt · ':'')+statuses[item.status]),node('h3',item.title),node('p',item.detail));
   const d=this.departments().find(d=>d.kod===item.department);const owner=(this.data.members[item.department]||[]).find(m=>m.key===item.owner);
   card.append(node('p',(d?.ad||'Birim atanmamış')+' · '+(owner?.name||'Sorumlu atanmamış')),node('p','Teslim: '+(item.due?new Date(item.due+'T12:00:00').toLocaleDateString('tr-TR'):'Belirlenmemiş')));
   if(item.status!=='resolved')card.append(node('p',item.issues.join(' · '),'ops-warning'));
   if(!item.observed)card.append(node('p','Bu okumada kaynak satırı görülmedi. Önceki takip korunuyor; işin tamamlandığı doğrulanmadı.','ops-warning'));
   if(item.note)card.append(node('p','Çözüm notu: '+item.note));
   card.append(node('small','Kaynak: '+item.source),button('Kaydı aç ve takibi düzenle',()=>this.editor(item)));
   if(item.new)card.append(button('Gördüm',async()=>{try{await this.api('/api/office/acknowledge',{id:item.id});item.new=false;this.render();}catch(e){this.notice(e.message);}}));
   list.append(card);
  }
  this.content.append(node('p','İK değerlendirmesi iş kayıtlarına dayanır. Mola ve ofis animasyonları performans ölçümü değildir. Aynı hata ancak ayrı ekip döngülerinde tekrarlandıysa işaretlenir.','ops-muted'));
 }
 editor(item){
  const form=node('form',undefined,'ops-editor');form.append(node('h2','İş kaydı ve çözüm takibi'),node('h3',item.title),node('p',item.detail),node('p','Sonraki adım: '+(item.action||'Henüz tanımlanmamış')));
  const dep=node('select'),owner=node('select'),due=node('input'),status=node('select'),note=node('textarea');due.type='date';due.value=item.due||'';note.value=item.note||'';note.maxLength=1500;
  dep.append(new Option('Birim seçin',''));for(const d of this.departments())dep.append(new Option(d.ad,d.kod));dep.value=item.department||'';dep.required=true;
  const fill=()=>{owner.replaceChildren(new Option('Sorumlu atanmamış',''));for(const m of this.data.members[dep.value]||[])owner.append(new Option(m.name,m.key));};fill();owner.value=item.owner||'';dep.onchange=fill;
  for(const [key,label] of Object.entries(statuses))status.append(new Option(label,key));status.value=item.status;
  for(const [label,control] of [['Birim',dep],['Sorumlu',owner],['Teslim tarihi',due],['Çözüm durumu',status],['Çözüm açıklaması',note]]){const l=node('label',label);control.setAttribute('aria-label',label);l.append(control);form.append(l);}
  const save=node('button','Takibi kaydet');save.type='submit';form.append(save,button('Listeye dön',()=>this.render()),node('p','Bu işlem ofis takibini günceller. Kaynak sistemdeki işi tamamlamaz ve dışarıya mesaj göndermez.'));
  form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{await this.api('/api/office/followup',{id:item.id,version:item.version,department:dep.value,owner:owner.value,due:due.value,status:status.value,note:note.value});await this.load(true);this.render();this.notice('Takip kaydı kaydedildi.');}catch(e){this.notice(e.message);}finally{save.disabled=false;}};
  this.content.replaceChildren(form);dep.focus();
 }
 connections(){
  this.content.append(node('h2','Kaynak bağlantıları'),node('p','Kaynak tanımı, başarılı okuma ve verinin güncelliği ayrı gösterilir. Aynı uyarıyı gördüm olarak işaretlediğinizde içerik değişene kadar yeniden yeni sayılmaz.','ops-muted'));
  const grid=node('div',undefined,'ops-grid');this.content.append(grid);
  for(const c of this.data.connections.filter(c=>!this.department||c.department===this.department)){
   const card=node('article',undefined,'ops-card');card.append(node('h3',c.name),node('strong',c.state),node('p','Kaynak: '+c.source),node('p',c.permission),node('p',c.action),node('p','Son başarılı ekip sorgusu: '+when(c.check?.last_success)));
   if(c.check){card.append(node('p',c.check.note));for(const r of c.check.results)card.append(node('p',r.name+' · '+(r.ok?r.count+' kayıt okundu':'Okunamadı')));}
   const test=button('Okuma denetimini çalıştır',async()=>{test.disabled=true;test.textContent='Denetleniyor…';try{c.check=await this.api('/api/office/source-check',{department:c.department});this.render();this.notice(c.check.ok?'Ekip sorguları okundu. Dış hesabın tüm yetkileri ayrıca doğrulanmalıdır.':'Okuma tamamlanamadı veya atanmış sorgu bulunamadı. Kaynak ve izinleri kontrol edin.');}catch(e){this.notice(e.message);}finally{test.disabled=false;test.textContent='Okuma denetimini çalıştır';}});card.append(test);grid.append(card);
  }
  const details=node('details');details.append(node('summary','Kaynakların kayıtlı doğrulama tarihleri'));
  for(const p of this.data.provenance||[])details.append(node('p',displayText(p.entity_id)+' · Kayıtlı doğrulama: '+when(p.observed_at)));
  details.append(node('p','Bu tarihler kaynağın kendi doğrulama kaydıdır. Sayfanın yenilenmesi bu tarihleri güncel hale getirmez.'));this.content.append(details);
 }
 products(){
  this.content.append(node('h2','Gerçek ürün portföyü'),node('p','Fotoğraflar mevcut katalogdan, fiyat ve stoklar şirket kaynaklarından alınır. Görseli eşleşmeyen ürüne temsili ürün fotoğrafı atanmaz.','ops-muted'));
  const search=node('input');search.type='search';search.placeholder='Ürün ara';search.setAttribute('aria-label','Ürün ara');const grid=node('div',undefined,'ops-products');this.content.append(search,grid);
  const render=()=>{grid.replaceChildren();const query=search.value.toLocaleLowerCase('tr-TR');let products=this.data.products.filter(p=>p.name.toLocaleLowerCase('tr-TR').includes(query)&&(!this.product||p.id===this.product));
   for(const p of products){const card=node('article',undefined,'ops-card');if(p.image){const img=node('img');img.src=p.image;img.loading='lazy';img.alt=p.name;img.onerror=()=>img.replaceWith(node('p','Katalog fotoğrafı yüklenemedi.'));card.append(img);}else card.append(node('div','Fotoğraf eşleşmesi bulunamadı','ops-no-image'));
    card.append(node('h3',p.name));const table=node('dl');for(const [label,v] of [['İnternet mağazası fiyatı',value(p.website_price)],['İnternet mağazası stoku',value(p.website_stock)],['Pazaryeri fiyatı',value(p.marketplace_price)],['Pazaryeri stoku',value(p.marketplace_stock)],['Birim maliyet',value(p.cost)],['Maliyet kaynağı',p.cost_source],['Kayıtlı net ciro',value(p.net_revenue)],['Brüt marj oranı',p.gross_margin===null?'Bilgi yok':'%'+value(p.gross_margin)],['Maliyet kapsamı',p.coverage===null?'Bilgi yok':'%'+value(p.coverage)]])table.append(node('dt',label),node('dd',v));card.append(table,node('p',p.note,'ops-muted'));
    const gaps=[!p.image?'Görsel eşleşmesi eksik':'',p.cost===null?'Maliyet eksik':'',p.website_stock===null?'Stok bilgisi eksik':'',p.website_price===null?'Fiyat bilgisi eksik':''].filter(Boolean);if(gaps.length)card.append(node('p',gaps.join(' · '),'ops-warning'));
    grid.append(card);
   }if(!products.length)grid.append(node('p','Eşleşen ürün bulunamadı.'));};search.oninput=render;render();
  if(this.product)this.content.prepend(button('Bütün ürünleri göster',()=>{this.product='';this.render();}));
  this.content.append(node('p','Ürün kaynağı okuma zamanı: '+when(this.data.reads.urun_karti?.at)+'. Para birimi ve satış dönemi kaynakta belirtilmediği yerde varsayılmaz.','ops-muted'));
 }
}
