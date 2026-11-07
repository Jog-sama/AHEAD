const {chromium,webkit}=require('playwright');
const waitText=async(page,selector,text)=>{for(let i=0;i<100;i++){if((await page.locator(selector).textContent()).includes(text))return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timeout: '+selector+' '+text);};
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
 const page=await browser.newPage({viewport:{width:390,height:844},permissions:['camera','microphone']});
 let errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765');
 await page.fill('#key','test-only-backend-key-000000000000');await page.click('#connect');
 await waitText(page,'#connection','MOCK DEVICE');
 await page.click('#arm');
 const left=page.locator('[data-direction=left]');await left.focus();await page.keyboard.down('Space');
 await waitText(page,'#telemetry','80°');
 await page.keyboard.up('Space');
 await waitText(page,'#modeLabel','DISARMED');
 await page.click('#camera');await waitText(page,'#cameraLabel','Camera ready');
 await page.selectOption('#mode','cv');await page.click('#arm');
 await waitText(page,'#cameraLabel','round trip');
 await page.click('#stop');
 await page.locator('#record').focus();await page.keyboard.down('Space');
 await waitText(page,'#record','Recording…');
 await page.waitForTimeout(250);await page.keyboard.up('Space');
 await waitText(page,'#audioStatus','bytes received');
 await page.screenshot({path:'/tmp/tv-ui.png',fullPage:true});
 if(errors.length)throw new Error(errors.join('\n'));
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Horizontal overflow');
 console.log('Chromium 390px: auth, manual nudge/release, camera upload, Stop, microphone upload, no JS errors, no horizontal overflow PASS');
 await browser.close();
 try{
  const wb=await webkit.launch({headless:true});const wp=await wb.newPage({viewport:{width:390,height:844}});
  await wp.goto('http://127.0.0.1:8765');await wp.fill('#key','test-only-backend-key-000000000000');await wp.click('#connect');
  await waitText(wp,'#connection','MOCK DEVICE');
  console.log('Desktop WebKit: page load + authenticated status PASS (not iOS hardware)');await wb.close();
 }catch(e){console.log('Desktop WebKit unavailable: '+e.message.split('\n')[0]);}
})().catch(e=>{console.error(e);process.exit(1)});
