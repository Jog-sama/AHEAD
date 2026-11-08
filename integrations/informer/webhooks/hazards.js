export async function POST({query,request,crypto,env}) {
  const signature=request.headers['x-ahead-signature']||'';
  if(!env.AHEAD_WEBHOOK_SECRET||!signature||
     !await crypto.verifyHmac('sha256',env.AHEAD_WEBHOOK_SECRET,request.rawBody,signature))
    return {status:401,body:{ok:false,error:'Unauthorized'}};
  const e=request.body;
  const validCoord=(v,min,max)=>v===null||(typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max);
  if (!e || e.schema_version!==1 || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(e.event_id||'') ||
      typeof e.label!=='string' || !e.label || e.label.length>120 ||
      typeof e.simulated!=='boolean' || !Number.isFinite(Date.parse(e.observed_at)) ||
      !validCoord(e.latitude,-90,90) || !validCoord(e.longitude,-180,180) ||
      typeof e.confidence!=='number' || e.confidence<0 || e.confidence>1) {
    return {status:400,body:{ok:false,error:'Invalid hazard event'}};
  }
  const bucket=Math.floor(Date.parse(e.observed_at)/300000);
  const coord=v=>v===null?'none':Number(v).toFixed(4);
  const dedup=[e.label.trim().toLowerCase(),e.direction,coord(e.latitude),coord(e.longitude),bucket].join('|');
  const rows=await query(`INSERT INTO hazards
    (event_id,observed_at,label,source,simulated,latitude,longitude,severity,confidence,reason,direction,dedup_key,payload,last_seen)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$2)
    ON CONFLICT(dedup_key) DO UPDATE SET last_seen=EXCLUDED.observed_at,
      duplicate_count=hazards.duplicate_count+1,
      confidence=GREATEST(hazards.confidence,EXCLUDED.confidence),payload=EXCLUDED.payload
    RETURNING event_id,duplicate_count`,
    [e.event_id,e.observed_at,e.label,e.source,e.simulated,e.latitude,e.longitude,e.severity,
      e.confidence,e.reason,e.direction,dedup,JSON.stringify(e)]);
  return {status:200,body:{ok:true,event_id:rows[0].event_id,duplicate_count:rows[0].duplicate_count}};
}
