import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {chromium} from 'playwright';
import {createServer} from 'vite';
const snapshot=JSON.parse(await fs.readFile('../../../office-preview-data.json','utf8'));
const agents=JSON.parse(await fs.readFile('../../../office-preview-agents.json','utf8'));
const output='../../../../outputs/v3/';
const server=await createServer({configFile:'vite.config.js',server:{host:'127.0.0.1',port:5176,strictPort:true}});await server.listen();await server.watcher.close();
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--disk-cache-size=1','--media-cache-size=1','--disable-gpu-shader-disk-cache']});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async r=>{const p=new URL(r.request().url()).pathname;if(p==='/api/office/events')return r.fulfill({contentType:'text/event-stream',body:'event: snapshot\ndata: {"active":{}}\n\n'});let data={};if(p==='/api/session')data={authenticated:true};if(p==='/api/panel/ekip')data=snapshot;if(p==='/api/panel/ajanlar')data=agents;return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});});
 await page.goto('http://127.0.0.1:5176/office.html');await page.locator('#departmentCount').filter({hasText:'50'}).waitFor();await page.locator('#officeLife').uncheck();
 assert.equal(await page.locator('#floorSelect').inputValue(),'all');assert.equal(await page.locator('.scene-label').count(),50);assert.match(await page.locator('#floorContext').innerText(),/50 birim/);console.log('Açılış: 50 birim');
 await page.locator('#showTechdynasty').click();assert.equal(await page.locator('#floorSelect').inputValue(),'brand:tecdynasty');assert.equal(await page.locator('.scene-label').count(),4);assert.deepEqual((await page.locator('.scene-label strong').allTextContents()).sort(),['Teknoloji ve araçlar','Web ve dönüşüm','Otomasyon ve yapay zekâ','Güvenlik'].sort());
 await page.locator('#refresh').click();await page.locator('#connection').filter({hasText:'Canlı bağlantı'}).waitFor({timeout:10000});assert.equal(await page.locator('#floorSelect').inputValue(),'brand:tecdynasty');assert.equal(await page.locator('.scene-label').count(),4);console.log('TECDYNASTY: dört doğru birim; yenilemede korundu');
 await page.screenshot({clip:await page.locator('#sceneFrame').boundingBox(),path:output+'12-tecdynasty-tum-birimler.png',timeout:60000});
 await page.locator('#showGoril').click();assert.equal(await page.locator('.scene-label').count(),7);
 await page.locator('#floorSelect').selectOption('center');assert.equal(await page.locator('.scene-label').count(),4);
 await page.locator('#showAllOffices').click();assert.equal(await page.locator('.scene-label').count(),50);await page.locator('#refresh').click();await page.locator('#connection').filter({hasText:'Canlı bağlantı'}).waitFor({timeout:10000});assert.equal(await page.locator('#floorSelect').inputValue(),'all');assert.equal(await page.locator('.scene-label').count(),50);
 await page.screenshot({clip:await page.locator('#sceneFrame').boundingBox(),path:output+'13-butun-50-birim.png',timeout:60000});
 await page.locator('#loungeView').selectOption('1');await page.screenshot({clip:await page.locator('#sceneFrame').boundingBox(),path:output+'14-yesil-kafe.png',timeout:60000});
 await page.locator('#loungeView').selectOption('2');await page.screenshot({clip:await page.locator('#sceneFrame').boundingBox(),path:output+'15-agacli-teras.png',timeout:60000});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({initialRooms:50,allAfterRefresh:50,tecdynasty:4,goril:7,errors}));
}finally{await browser.close();await server.close();}
