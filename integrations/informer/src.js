import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';
const $=id=>document.getElementById(id);let events=[],map=null,markers=null;
function visible(){const f=$('filter').value;return events.filter(e=>f==='all'||(f==='simulated')===e.simulated);}
function drawMap(){if(!map)return;markers.clearLayers();const points=[];for(const e of visible()){
  if(e.latitude==null||e.longitude==null)continue;const p=[Number(e.latitude),Number(e.longitude)];points.push(p);
  const label=document.createElement('span');label.textContent=`${e.label} · ${e.simulated?'SIMULATED':'REVIEW'} · ${e.duplicate_count}×`;
  L.circleMarker(p,{radius:7,color:e.simulated?'#72807a':'#e6693e'}).bindPopup(label).addTo(markers);
}if(points.length)map.fitBounds(points,{maxZoom:18,padding:[20,20]});}
function drawTable(){$('events').replaceChildren();for(const e of visible()){const row=document.createElement('tr');
  for(const text of [new Date(e.observed_at).toLocaleString(),e.label,e.simulated?'SIMULATED':'MODEL CANDIDATE',`${Math.round(e.confidence*100)}%`,`${e.duplicate_count}×`,e.latitude==null?'Not supplied':`${Number(e.latitude).toFixed(5)}, ${Number(e.longitude).toFixed(5)}`,e.reason||'']){
    const cell=document.createElement('td');cell.textContent=text;row.append(cell);}$('events').append(row);}drawMap();}
async function refresh(){try{const [a,b]=await Promise.all([fetch('api/_server/hazards'),fetch('api/_server/summary')]);
  if(!a.ok||!b.ok)throw Error('Informer query failed');events=await a.json();const s=await b.json();const t=s.totals;
  for(const [id,key] of [['observations','observations'],['clusters','clusters'],['candidates','review_candidates'],['mapped','mapped']])$(id).textContent=t[key];
  $('summary').replaceChildren();for(const x of s.recent){const li=document.createElement('li');li.textContent=`${x.label}: ${x.observations} observation${x.observations===1?'':'s'} (${x.simulated?'simulated':'review'})`;$('summary').append(li);}
  $('narrative').textContent=s.top.length?`${t.observations} observations collapsed into ${t.clusters} review clusters. Most frequent: ${s.top[0].label} (${s.top[0].observations}).`:'No observations in the last seven days.';
  $('status').textContent=`Updated ${new Date().toLocaleTimeString()}`;drawTable();window.informerReady=true;
}catch(e){$('status').textContent=e.message;}}
$('refresh').onclick=refresh;$('filter').onchange=drawTable;$('mapButton').onclick=()=>{if(!map){$('map').style.height='360px';map=L.map('map').setView([36.0014,-78.9382],15);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map);markers=L.layerGroup().addTo(map);}drawMap();};
refresh();setInterval(refresh,15000);
