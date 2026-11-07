import {test} from 'node:test';
import assert from 'node:assert/strict';
import {POST} from '../webhooks/hazards.js';
const event={schema_version:1,event_id:'a1234567-1234-1234-1234-123456789012',observed_at:'2026-11-07T10:00:00Z',label:'chair',simulated:true,latitude:null,longitude:null};
test('parameterized insert, stable id and duplicate-safe SQL',async()=>{
  let calls=0;const query=async(sql,params)=>{calls++;assert.match(sql,/ON CONFLICT/);assert.equal(params[0],event.event_id);};
  assert.equal((await POST({query,request:{body:event}})).status,200);
  assert.equal((await POST({query,request:{body:event}})).status,200);assert.equal(calls,2);
});
test('reject bad GPS and shape before SQL',async()=>{
  const query=()=>assert.fail('must not query');
  for(const body of [null,{...event,latitude:100},{...event,simulated:'false'},{...event,event_id:'invalid'}])
    assert.equal((await POST({query,request:{body}})).status,400);
});
