'use strict';
async function run(){
  const {Client}=require('pg');
  const client=new Client({host:process.env.PGHOST,port:Number(process.env.PGPORT||5432),database:process.env.PGDATABASE,user:process.env.PGUSER,password:process.env.PGPASSWORD,ssl:false,application_name:'lcarlie-ai-health-f6'});
  await client.connect();
  try{
    await client.query('BEGIN READ ONLY');
    await client.query('SET LOCAL ROLE ai_reader');
    const health=(await client.query('SELECT core.ai_orchestrator_health() AS health')).rows[0].health;
    await client.query('COMMIT');
    process.stdout.write(JSON.stringify({component:'lcarlie-ai-orchestrator',...health})+'\n');
  }catch(error){try{await client.query('ROLLBACK')}catch(_){};process.stderr.write('orchestrator health check failed\n');process.exitCode=1;}finally{await client.end();}
}
run();
