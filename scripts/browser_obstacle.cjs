const {chromium}=require('playwright');
const waitText=async(p,s,t)=>{for(let i=0;i<100;i++){if((await p.locator(s).textContent()).includes(t))return;await new Promise(r=>setTimeout(r,50));}throw Error('Timed out: '+s);};
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const page=await browser.newPage({viewport:{width:390,height:844},permissions:['camera','microphone']});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765');
 await page.fill('#key','test-only-backend-key-000000000000');await page.click('#connect');
 await waitText(page,'#connection','MOCK');
 await page.selectOption('#mode','obstacle');
 // Wait for the mode-change Stop; camera-start auto-arm then supplies fresh frames.
 await page.waitForTimeout(100);
 await page.click('#camera');
 await waitText(page,'#cameraLabel','round trip');
 await waitText(page,'#scene','reason');
 const state=await page.evaluate(async()=> (await fetch('/api/status',{headers:{'X-API-Key':'test-only-backend-key-000000000000'}})).json());
 if(!state.armed||state.mode!=='obstacle'||state.commanded_angle!==90)throw Error('Obstacle fallback/auto-arm failed');
 await page.fill('#question','where is the chair');await page.click('#ask');
 await page.click('#hazards');
 await page.click('#stop');
 await waitText(page,'#modeLabel','DISARMED');
 if(errors.length)throw Error(errors.join('\n'));
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow');
 console.log('Chromium: obstacle mode auto-arm, fresh frame diagnostics, missing-model neutral, voice, hazards, Stop PASS. Fake camera; mock servo.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
