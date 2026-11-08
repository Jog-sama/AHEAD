import {test} from 'node:test';import assert from 'node:assert/strict';import {POST} from '../webhooks/hazards.js';
const event={schema_version:1,event_id:'a1234567-1234-4234-8234-123456789012',observed_at:'2026-11-07T10:00:00Z',label:'chair',source:'model_candidate',simulated:true,latitude:null,longitude:null,severity:'review',confidence:.8,reason:'blocked',direction:'center'};
const request={body:event,rawBody:JSON.stringify(event),headers:{'x-ahead-signature':'good'}};
const crypto={verifyHmac:async(alg,secret,body,sig)=>alg==='sha256'&&secret==='secret'&&body===request.rawBody&&sig==='good'};
test('authenticated insert uses semantic dedup and stable parameters',async()=>{let calls=0;
  const query=async(sql,params)=>{calls++;assert.match(sql,/ON CONFLICT\(dedup_key\)/);assert.equal(params[0],event.event_id);return[{event_id:event.event_id,duplicate_count:1}];};
  const result=await POST({query,request,crypto,env:{AHEAD_WEBHOOK_SECRET:'secret'}});assert.equal(result.status,200);assert.equal(calls,1);});
test('rejects missing signature, bad GPS and bad shape',async()=>{const query=()=>assert.fail('must not query');
  assert.equal((await POST({query,request:{...request,headers:{}},crypto,env:{AHEAD_WEBHOOK_SECRET:'secret'}})).status,401);
  for(const body of [null,{...event,latitude:100},{...event,simulated:'false'},{...event,event_id:'invalid'}])
    assert.equal((await POST({query,request:{...request,body},crypto,env:{AHEAD_WEBHOOK_SECRET:'secret'}})).status,400);});
