import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';
const $=id=>document.getElementById(id);
let events=[],map=null,markers=null;
function drawMap(){
  if(!map)return;
  markers.clearLayers();
  const points=[];
  for(const e of events){
    if(e.latitude==null||e.longitude==null)continue;
    const p=[Number(e.latitude),Number(e.longitude)];points.push(p);
    const label=document.createElement('span');label.textContent=`${e.label} · ${e.simulated?'SIMULATED':'NEEDS REVIEW'}`;
    L.circleMarker(p,{radius:7,color:e.simulated?'#777':'#b64e24'}).bindPopup(label).addTo(markers);
  }
  if(points.length)map.fitBounds(points,{maxZoom:18,padding:[20,20]});
}
async function refresh(){
  try{
    const response=await fetch('api/_server/hazards');if(!response.ok)throw Error('Hazard query failed');
    events=await response.json();$('events').replaceChildren();
    for(const e of events){const row=document.createElement('tr');
      for(const text of [e.observed_at,e.label,e.simulated?'SIMULATED':'MODEL CANDIDATE',e.latitude==null?'Not supplied':`${e.latitude}, ${e.longitude}`,e.payload?.reason||'']){
        const cell=document.createElement('td');cell.textContent=text;row.append(cell);
      }$('events').append(row);
    }
    const response2=await fetch('api/_server/summary');if(!response2.ok)throw Error('Summary query failed');
    const summary=await response2.json();$('summary').replaceChildren();
    for(const s of summary){const li=document.createElement('li');li.textContent=`${s.label}: ${s.observations} observations (${s.simulated?'simulated':'review'})`;$('summary').append(li);}
    $('status').textContent=`${events.length} recent observations. Map tiles load only when requested.`;
    drawMap();window.informerReady=true;
  }catch(e){$('status').textContent=e.message;}
}
$('refresh').onclick=refresh;
$('mapButton').onclick=()=>{
  if(!map){$('map').style.height='360px';map=L.map('map').setView([36.0014,-78.9382],15);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
    markers=L.layerGroup().addTo(map);
  }drawMap();
};
refresh();setInterval(refresh,15000);
