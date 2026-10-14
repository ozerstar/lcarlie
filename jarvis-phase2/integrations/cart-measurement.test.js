const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(__dirname+'/cart-measurement.js','utf8');
function fixture(path='/cart',analytics=false,existing=[]){
 let tick, calls=[];
 const context={location:{pathname:path},localStorage:{getItem:()=>JSON.stringify({analytics})},document:{readyState:'complete',addEventListener:()=>{}},setInterval:(fn)=>{tick=fn;},window:{dataLayer:existing,addEventListener:()=>{},gtag:(...args)=>{calls.push(args);context.window.dataLayer.push(args);}}};
 const originalPush=context.window.dataLayer.push.bind(context.window.dataLayer);
 context.window.dataLayer.push=(event)=>{calls.push(event);return originalPush(event);};
 vm.runInNewContext(code,context);
 return {context,calls,tick:()=>tick(),allow:()=>{analytics=true;}};
}
let f=fixture();assert.equal(f.calls.length,0);f.allow();f.tick();assert.equal(f.calls.length,1);f.tick();assert.equal(f.calls.length,1);
f.context.location.pathname='/product';f.tick();f.context.location.pathname='/cart';f.tick();assert.equal(f.calls.length,2);
f=fixture('/product',true);assert.equal(f.calls.length,0);
f=fixture('/cart',true,[['event','view_cart',{}]]);assert.equal(f.calls.length,0);assert.equal(f.context.window.__lcCartMeasurement.deduplicated,1);
f=fixture('/cart',true);assert.equal(f.calls[0].page_path,'/cart');assert.equal(f.calls[0].event,'view_cart');assert(!('user_id' in f.calls[0]));
console.log('PASS consent, duplicates, SPA, target measurement ID and no customer identifiers');
