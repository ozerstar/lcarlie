const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const implementation = source.slice(source.indexOf('async function sendMessage(message'), source.indexOf('function log_scroll()'));
function harness(chunks, fetchOverride) {
  const elements = {};
  const rows = [];
  const calls = [];
  let released = false;
  const reader = {async read() { return chunks.length ? {value: new TextEncoder().encode(chunks.shift()), done: false} : {done: true}; }, async cancel() {}, releaseLock() {released = true;}};
  const context = vm.createContext({TextDecoder, AbortController, crypto: {randomUUID: () => 'stable-turn'},
    state: {csrfToken:'token'}, chatId: () => 'conversation',
    qs: id => elements[id] ||= {},
    addChatMessage(role, html) {const row = {role, innerHTML:html, setAttribute(){}, classList:{remove(){}}, querySelector(){return null;}};rows.push(row);return row;},
    addChatCopyButton(row) {row.copy = true;}, escapeHtml: x => x, renderMarkdownLite: x => x,
    renderAnswerBody: x => x.text, JarvisDil: {error:x=>x,text:x=>x},
    refreshActivity(){}, log_scroll(){},
    fetch: async (...args) => {calls.push(args);return fetchOverride ? fetchOverride(...args) : {ok:true,body:{getReader:()=>reader}};}});
  vm.runInContext('let activeStreamController=null, lastUserMessage=null, lastChatTurn=null;'+implementation, context);
  return {context, rows, elements, calls, released:()=>released, send:(text, previous)=>context.sendMessage(text, previous)};
}
test('desktop handles final NDJSON without newline and restores copy control', async()=>{
  const h=harness(['{"type":"token","delta":"Mer"}\n','{"type":"done","result":{"text":"Merhaba"}}']);
  assert.equal(await h.send('selam'), 'Merhaba');
  assert.equal(h.rows[1].innerHTML,'Merhaba'); assert.equal(h.rows[1].copy,true);
  assert.equal(h.elements.retryBtn.hidden,true); assert.equal(h.released(),true);
});
test('truncated response is not presented as completed and preserves partial answer', async()=>{
  const h=harness(['{"type":"token","delta":"Kısmi yanıt"}\n']);
  await h.send('soru');
  assert.match(h.rows[1].innerHTML,/Kısmi yanıt/); assert.match(h.rows[1].innerHTML,/tamamlanmadı/);
  assert.equal(h.elements.retryBtn.hidden,false); assert.equal(h.elements.sendBtn.disabled,false);
});
test('concurrent shortcuts cannot launch a second turn', async()=>{
  let release; const response=new Promise(resolve=>release=resolve);
  const h=harness([],()=>response); const first=h.send('ilk');
  assert.equal(await h.send('ikinci'),''); assert.equal(h.calls.length,1);
  release({ok:false}); await first; assert.equal(h.elements.sendBtn.disabled,false);
});
test('manual reconnect reuses turn and original conversation instead of executing a new request', async()=>{
  const h=harness(['{"type":"done","result":{"text":"Tamam"}}\n']);
  await h.send('soru',{id:'existing-turn',chatId:'original-chat'});
  const body=JSON.parse(h.calls[0][1].body);
  assert.equal(body.turn_id,'existing-turn'); assert.equal(body.chat_id,'original-chat');
  assert.equal(h.rows.filter(row=>row.role==='user').length,0);
});
test('stage update does not erase streamed text', async()=>{
  const h=harness(['{"type":"token","delta":"Metin"}\n{"type":"stage","label":"Bekliyor"}\n']);
  await h.send('soru'); assert.match(h.rows[1].innerHTML,/Metin/);
});
test('stopping display does not claim server-side work was cancelled', async()=>{
  const error = new Error('aborted'); error.name='AbortError';
  const h=harness([],async()=>{throw error;});
  assert.equal(await h.send('soru'),'');
  assert.match(h.rows[1].innerHTML,/Sunucudaki işlem devam ediyor olabilir/);
  assert.equal(h.elements.retryBtn.hidden,false);
});
test('malformed stream becomes incomplete instead of an unhandled failure', async()=>{
  const h=harness(['not json\n']);
  await h.send('soru');
  assert.match(h.rows[1].innerHTML,/tamamlanmadı/);
  assert.equal(h.released(),true);
  assert.equal(h.elements.sendBtn.disabled,false);
});
