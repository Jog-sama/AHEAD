export async function POST({query,request}) {
  const e=request.body;
  const validCoord=(v,min,max)=>v===null||(typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max);
  if (!e || e.schema_version!==1 || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(e.event_id||'') ||
      typeof e.label!=='string' || !e.label || e.label.length>120 ||
      typeof e.simulated!=='boolean' || !Number.isFinite(Date.parse(e.observed_at)) ||
      !validCoord(e.latitude,-90,90) || !validCoord(e.longitude,-180,180)) {
    return {status:400,body:{ok:false,error:'Invalid hazard event'}};
  }
  await query(`INSERT INTO hazards(event_id,observed_at,label,simulated,latitude,longitude,payload)
    VALUES($1,$2,$3,$4,$5,$6,$7::jsonb) ON CONFLICT(event_id) DO NOTHING`,
    [e.event_id,e.observed_at,e.label,e.simulated,e.latitude,e.longitude,JSON.stringify(e)]);
  return {status:200,body:{ok:true,event_id:e.event_id}};
}
