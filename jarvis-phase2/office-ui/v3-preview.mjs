import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {createServer} from 'vite';
const snapshot=JSON.parse(await fs.readFile('../../../office-preview-data.json','utf8'));
const agents=JSON.parse(await fs.readFile('../../../office-preview-agents.json','utf8'));
const output='../../../../outputs/v3/';
const server=await createServer({configFile:'vite.config.js',server:{host:'127.0.0.1',port:5176,strictPort:true}});await server.listen();
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--disk-cache-size=1','--media-cache-size=1','--disable-gpu-shader-disk-cache']});
try{
 const shot=async(page,name)=>{await page.screenshot({clip:await page.locator('#sceneFrame').boundingBox(),path:output+name,timeout:60000});};
 const page=await browser.newPage({viewport:{width:1600,height:1000},deviceScaleFactor:1.25});const errors=[];page.on('pageerror',e=>errors.push(e.message));let failure='provider';
 await page.route('**/api/**',async r=>{
  const url=new URL(r.request().url()).pathname;
  if(url==='/api/office/events')return r.fulfill({contentType:'text/event-stream',body:'event: snapshot\ndata: {"active":{}}\n\n'});
  if(url==='/api/ekip/sor')return failure==='html'?r.fulfill({status:503,contentType:'text/html',body:'<html>Service unavailable</html>'}):r.fulfill({contentType:'application/json',body:JSON.stringify({hata:'no model provider could answer'})});
  let data={};if(url==='/api/session')data={authenticated:true};if(url==='/api/panel/ekip')data=snapshot;if(url==='/api/panel/ajanlar')data=agents;
  await r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 await page.goto('http://127.0.0.1:5176/office.html');await page.locator('#departmentCount').filter({hasText:'50'}).waitFor();await page.locator('#officeLife').uncheck();await page.waitForTimeout(300);console.log('Ofis açıldı');
 assert.equal(await page.locator('#sceneFallback').isVisible(),false);
 const sizing=await page.evaluate(()=>{const a=document.querySelector('#scene canvas').getBoundingClientRect(),b=document.querySelector('#sceneOverlay').getBoundingClientRect();return {cw:a.width,ow:b.width,ch:a.height,oh:b.height};});assert.equal(sizing.cw,sizing.ow);assert.equal(sizing.ch,sizing.oh);
 await page.locator('#floorSelect').selectOption('all');await page.waitForTimeout(500);
 assert.equal(await page.locator('.scene-label').count(),50);
 const labels=await page.locator('.scene-label strong').allTextContents();assert(labels.includes('Google arama reklamları'));assert(labels.every(s=>!s.includes('_')&&s!=='EXEC'));
 await page.locator('#officeLife').uncheck();await shot(page,'01-turkce-etiketler.png');console.log('Etiketler doğrulandı');await page.locator('#floorSelect').selectOption('center');
 await page.locator('#search').fill('Ürün yönetimi');await page.locator('#departments .department-row').first().click();
 await page.locator('[data-room-use="board"]').click();await page.locator('#closeDetail').click();await page.locator('#officeLife').check();await page.waitForTimeout(5500);
 await shot(page,'02-akilli-tahta-ve-mobilyalar.png');console.log('Akıllı tahta doğrulandı');
 await page.locator('#departments .department-row').first().click();await page.locator('[data-room-use="storage"]').click();await page.locator('#closeDetail').click();await page.waitForTimeout(6500);
 await shot(page,'03-dolap-kullanimi.png');
 await page.locator('#departments .department-row').first().click();await page.locator('[data-room-use="meeting"]').click();await page.locator('#closeDetail').click();await page.waitForTimeout(5500);
 await shot(page,'04-toplanti-alani.png');
 await page.locator('#departments .department-row').first().click();await page.locator('[data-room-use="rest"]').click();
 await page.locator('.manager-question').fill('Son durum nedir?');await page.locator('.manager-send').click();await page.locator('.conversation-item.manager').waitFor();
 assert.match(await page.locator('.conversation-item.manager').last().innerText(),/Yanıt hizmeti şu anda kullanılamıyor/);
 failure='html';await page.locator('.manager-question').fill('Yeniden kontrol et');await page.locator('.manager-send').click();await page.waitForTimeout(300);assert.match(await page.locator('.conversation-item.manager').last().innerText(),/ulaşılamadı/);
 await page.screenshot({path:output+'05-turkce-yanit-durumu.png',fullPage:true});
 const visibleText=await page.locator('body').innerText();assert(!/no model provider|Unexpected token|Failed to fetch|GOOGLE_ADS|DATA_BI|ecommerce_profitability/.test(visibleText));
 assert.equal(await page.locator('#memberCount').innerText(),'108');assert.deepEqual(errors,[]);
  await page.locator('#showRetail').click();await page.locator('#officeLife').uncheck();await page.waitForTimeout(500);await shot(page,'06-marka-alanlari.png');
 for(const [key,file] of [['showroom','07-urun-sergi-alani.png'],['store','08-magaza.png'],['stand','09-tanitim-standi.png']]){await page.locator('#retailView').selectOption(key);await page.waitForTimeout(400);await shot(page,file);console.log(file);}
 await page.locator('#floorSelect').selectOption('family:KREATIF');await page.locator('#search').fill('Tasarım');await page.locator('#departments .department-row').first().click();await page.locator('#closeDetail').click();await page.waitForTimeout(400);await shot(page,'10-goril-ajans.png');
 await page.locator('#search').fill('Teknoloji');await page.locator('#departments .department-row').first().click();await page.locator('#closeDetail').click();await page.waitForTimeout(400);await shot(page,'11-tecdynasty.png');
 await page.close();
 // The furniture animation remains independent of real employee counts.
 const p=await browser.newPage({viewport:{width:760,height:700}});await p.goto('http://127.0.0.1:5176/office.html');
 const animation=await p.evaluate(async()=>{const THREE=await import('/node_modules/three/build/three.module.js');const {palette}=await import('/src/office-assets.js');const {RoomWorkspace}=await import('/src/room-workspace.js');const w=new RoomWorkspace(new THREE.Group(),palette(),{kod:'TEST',ad:'Deneme birimi',kadro:[]});w.start('storage');w.update(7,true);const opened=w.door.rotation.y>1;w.update(0,false);const paused=!w.actor.group.visible&&w.door.rotation.y===0;w.start('board');w.update(7,true);const atBoard=w.actor.group.position.z< -3;w.start('meeting');w.update(7,true);const meeting=w.partner.group.visible;w.start('rest');return {opened,paused,atBoard,meeting,stopped:!w.actor.group.visible};});assert(Object.values(animation).every(Boolean));await p.close();
 console.log(JSON.stringify({sizing,labels:labels.length,members:108,managerErrors:'Türkçe',animation,errors}));
}finally{await browser.close();await server.close();}
