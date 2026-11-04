import test from 'node:test';
import assert from 'node:assert/strict';
import {syncDepartments} from './src/roster-data.js';
test('missing primary members are restored and fresh detailed status wins',()=>{
  const result=syncDepartments({departmanlar:[{kod:'RED_TEAM',sorumlu:{key:'a'},kadro:[{key:'a',status:'VERİ YOK'}]}]},
    {departmanlar:[{kod:'RED_TEAM',uyeler:[{key:'a',ad:'A',durum:'KONUŞTU'},{key:'b',ad:'B',durum:'KONUŞTU'}]}]});
  assert.equal(result[0].kadro.length,2);assert.equal(result[0].kadro[0].status,'KONUŞTU');assert.equal(result[0].kadro[0].sorumlu_mu,true);
});
test('empty departments stay empty and large rosters are never truncated in data',()=>{
  const deps=Array.from({length:200},(_,i)=>({kod:'D'+i,uyeler:i===0?[]:Array.from({length:30},(_,j)=>({key:i+'_'+j,ad:'Üye'}))}));
  const result=syncDepartments(null,{departmanlar:deps});
  assert.equal(result.length,200);assert.equal(result.find(d=>d.kod==='D0').kadro.length,0);
  assert.equal(result.reduce((n,d)=>n+d.kadro.length,0),199*30);
});
test('one failed source still preserves valid roster',()=>{
  assert.equal(syncDepartments({departmanlar:[{kod:'TEKNOLOJI',kadro:[{key:'x'}]}]},null)[0].kadro.length,1);
});
