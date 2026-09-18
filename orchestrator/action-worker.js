'use strict';
function validateInternalReview(payload) {
  if(!payload||typeof payload!=='object'||Array.isArray(payload)) throw new Error('invalid payload');
  const keys=Object.keys(payload).sort();
  if(JSON.stringify(keys)!==JSON.stringify(['reason','subject_ref'])) throw new Error('invalid payload schema');
  if(typeof payload.subject_ref!=='string'||!payload.subject_ref||payload.subject_ref.length>200) throw new Error('invalid subject ref');
  if(typeof payload.reason!=='string'||!payload.reason||payload.reason.length>2000) throw new Error('invalid reason');
}
async function run() {
  const {Client}=require('pg');
  const client=new Client({host:process.env.PGHOST,port:Number(process.env.PGPORT||5432),database:process.env.PGDATABASE,user:process.env.PGUSER,password:process.env.PGPASSWORD,ssl:false,application_name:'lcarlie-action-worker-f5'});
  await client.connect();
  try {
    await client.query('BEGIN');
    await client.query('SET LOCAL ROLE action_executor');
    const action=(await client.query('SELECT * FROM core.ai_claim_approved_action($1,$2)',[process.env.ACTION_WORKER_ID||'f5-action-worker',180])).rows[0];
    if(!action){await client.query('COMMIT');return {status:'IDLE'};}
    let resultClass='EXECUTED',summary='internal human review request recorded by FakeExecutor';
    try {
      if(action.action_type!=='REQUEST_HUMAN_REVIEW') throw new Error('handler not enabled');
      validateInternalReview(action.payload);
    } catch(_) { resultClass='FAILED_FINAL'; summary='action rejected by fixed handler policy'; }
    await client.query('SELECT core.ai_complete_action_execution($1,$2,$3,$4)',[action.execution_id,action.lease_token,resultClass,summary]);
    await client.query('COMMIT');
    return {status:resultClass,execution_id:Number(action.execution_id),action_id:Number(action.action_id),action_type:action.action_type,attempt:Number(action.attempt_count)};
  } catch(error) { try{await client.query('ROLLBACK');}catch(_){} throw error; } finally {await client.end();}
}
if(require.main===module) run().then(result=>process.stdout.write(JSON.stringify(result)+'\n')).catch(()=>{process.stderr.write('action worker failed safely\n');process.exitCode=1;});
module.exports={validateInternalReview};
