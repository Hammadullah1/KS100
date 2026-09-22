export const LIVE_URL='https://raw.githubusercontent.com/Hammadullah1/KS100/forecast-data/latest.json';
const CACHE='psx:experimental-feed-v1';
export type LiveEstimate={horizon:1|5;reference_session:string;issued_at:string;update_due_at:string;p_up:number;p_not_up:number;baseline_up:number;model_version:string;reference_hash:string;outcome:{target_session:string;up:boolean;correct:boolean}|null};
export type LiveFeed={schema_version:'research-live-v1';mode:'experimental';instrument:'KSE100';generated_at:string;reference_session:string;source_url:string;model_name:string;validation:string;calendar_status:string;forecast_basis:string;forecasts:LiveEstimate[];history:LiveEstimate[]};
export type LiveLoaded={feed:LiveFeed;cached:boolean;error:string|null};
const probability=(p:unknown):p is number=>typeof p==='number'&&Number.isFinite(p)&&p>=0&&p<=1;
const timestamp=(value:unknown):value is string=>typeof value==='string'&&Number.isFinite(Date.parse(value));
export function validLive(value:unknown):value is LiveFeed{
 if(!value||typeof value!=='object')return false;
 const f=value as LiveFeed;
 if(f.schema_version!=='research-live-v1'||f.mode!=='experimental'||f.instrument!=='KSE100'||!timestamp(f.generated_at)||!/^\d{4}-\d{2}-\d{2}$/.test(f.reference_session)||!Array.isArray(f.forecasts)||f.forecasts.length!==2||!Array.isArray(f.history)||f.history.length>1000)return false;
 if(f.forecasts.map(v=>v.horizon).sort().join()!=='1,5')return false;
 return [...f.forecasts,...f.history].every(e=>[1,5].includes(e.horizon)&&timestamp(e.issued_at)&&timestamp(e.update_due_at)&&Date.parse(e.issued_at)<Date.parse(e.update_due_at)&&Date.parse(e.issued_at)<=Date.parse(f.generated_at)&&probability(e.p_up)&&probability(e.p_not_up)&&probability(e.baseline_up)&&Math.abs(e.p_up+e.p_not_up-1)<1e-10&&typeof e.model_version==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(e.reference_session)&&(e.outcome===null||e.outcome&&typeof e.outcome.up==='boolean'&&typeof e.outcome.correct==='boolean'&&e.outcome.target_session>e.reference_session))&&f.forecasts.every(e=>e.reference_session===f.reference_session);
}
export async function loadLive():Promise<LiveLoaded>{
 try{
  const response=await fetch(LIVE_URL,{cache:'no-store',signal:AbortSignal.timeout(12000)});
  if(!response.ok)throw Error('Daily research update is unavailable');
  const text=await response.text();if(text.length>1_000_000)throw Error('Research response is too large');
  const feed:unknown=JSON.parse(text);if(!validLive(feed))throw Error('Research update failed validation');
  try{localStorage.setItem(CACHE,JSON.stringify(feed));}catch{/* Storage is optional. */}
  return {feed,cached:false,error:null};
 }catch(error){
  const reason=error instanceof Error?error.message:'Research update unavailable';
  try{const feed:unknown=JSON.parse(localStorage.getItem(CACHE)||'null');if(validLive(feed))return {feed,cached:true,error:reason};}catch{/* Invalid cache stays unavailable. */}
  throw Error(reason);
 }
}
export function liveState(loaded:LiveLoaded,now:number):string{
 if(now<Date.parse(loaded.feed.generated_at)-300000)return 'Check device clock';
 if(loaded.feed.forecasts.some(f=>now>=Date.parse(f.update_due_at)))return 'Update overdue — previous estimate';
 if(loaded.cached)return 'Offline or update unavailable — saved estimate';
 return 'Daily research estimate — not a validated signal';
}
