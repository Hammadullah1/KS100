import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test.beforeEach(async({page})=>{await page.route('https://raw.githubusercontent.com/**',route=>route.abort());});
test('daily research probabilities display with evidence warnings',async({page})=>{
 const issued=new Date().toISOString();const due=new Date(Date.now()+86400000).toISOString();
 const estimate={horizon:1,reference_session:issued.slice(0,10),issued_at:issued,update_due_at:due,p_up:.57,p_not_up:.43,baseline_up:.5,model_version:'research-browser-test',reference_hash:'test',outcome:null};
 const feed={schema_version:'research-live-v1',mode:'experimental',instrument:'KSE100',generated_at:issued,reference_session:estimate.reference_session,source_url:'https://dps.psx.com.pk/',model_name:'research',validation:'No demonstrated forecasting advantage',calendar_status:'unverified',forecast_basis:'recorded sessions',forecasts:[estimate,{...estimate,horizon:5}],history:[estimate,{...estimate,horizon:5}]};
 await page.route('https://raw.githubusercontent.com/**',route=>route.fulfill({body:JSON.stringify(feed),contentType:'application/json'}));
 await page.setViewportSize({width:393,height:850});await page.goto('/');
 await expect(page.getByText('57.0%',{exact:true})).toBeVisible();
 await expect(page.getByText('Daily research estimate — not a validated signal',{exact:true})).toBeVisible();
 await expect(page.getByText('This forecast covers the index, not its 100 individual stocks.')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 const result=await new AxeBuilder({page}).analyze();expect(result.violations).toEqual([]);
 await page.screenshot({path:'test-results/live-research-393.png',fullPage:true});
});
for(const width of [320,360,393]){
 test('mobile empty dashboard '+width,async({page})=>{
  await page.setViewportSize({width,height:850});await page.goto('/');
  await expect(page.getByRole('heading',{name:'KSE-100 market outlook'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Awaiting verified sources');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(page.getByText('No estimate available')).toHaveCount(2);
  await page.getByRole('button',{name:'5 sessions'}).click();
  await expect(page.getByRole('heading',{name:'The next 5 sessions'})).toBeVisible();
  for(const name of ['Watchlist','Evidence','Drivers','Health']){await page.getByRole('button',{name,exact:true}).click();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  await page.getByRole('button',{name:'Overview'}).click();
  const result=await new AxeBuilder({page}).analyze();expect(result.violations).toEqual([]);
  await page.screenshot({path:`test-results/dashboard-${width}.png`,fullPage:true});
 });
}
test('verified app shell works offline',async({page,context})=>{
 await page.goto('/');await expect(page.getByRole('status')).toContainText('Awaiting verified sources');
 await page.evaluate(()=>navigator.serviceWorker.ready);
 await page.reload();await expect(page.getByRole('heading',{name:'KSE-100 market outlook'})).toBeVisible();
 await context.setOffline(true);await page.reload();
 await expect(page.getByRole('status')).toContainText('Offline');
 await expect(page.getByText('No estimate available')).toHaveCount(2);
 await page.screenshot({path:'test-results/offline.png',fullPage:true});
});

// Synthetic contract payload exists only in tests; never copied to public assets.
test('expired verified cache remains historical when publication is corrupt',async({page,context})=>{
 const {readFileSync}=await import('node:fs');
 const {createHash}=await import('node:crypto');
 const raw=readFileSync(new URL('../fixtures/expired.json',import.meta.url),'utf8');
 const sha=createHash('sha256').update(raw).digest('hex');
 await page.addInitScript(({raw,sha})=>localStorage.setItem('psx:last-verified-v1',JSON.stringify({raw,sha})),{raw,sha});
 await page.route('**/data/latest.json',route=>route.fulfill({body:'corrupt publication',contentType:'application/json'}));
 await page.goto('/');
 await expect(page.getByText('Historical forecast - expired',{exact:true})).toBeVisible();
 await expect(page.getByText('Its target session has ended. This cached forecast is history.')).toBeVisible();
 await page.evaluate(()=>navigator.serviceWorker.ready);
 await page.reload();
 await context.setOffline(true);
 await page.reload();
 await expect(page.getByRole('status')).toContainText('Offline');
 await expect(page.getByText('Historical forecast - expired',{exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/expired-cache.png',fullPage:true});
});
