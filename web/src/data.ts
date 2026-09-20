import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import schema from './bundle.schema.json';
import type { Bundle, Forecast } from './contracts.generated';

const ajv=new Ajv({strict:false}); addFormats(ajv);
const validate=ajv.compile<Bundle>(schema);
const KEY='psx:last-verified-v1';
const hash=async(text:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(v=>v.toString(16).padStart(2,'0')).join('');
export type Loaded={bundle:Bundle; offline:boolean; error:string|null};
const idPattern=/^[a-f0-9]{64}$/;
export function validBundle(value:unknown):value is Bundle{
 if(!validate(value)) return false;
 const bundle=value as Bundle;
 if(bundle.mode!=='production') return false;
 return [...bundle.forecasts,...bundle.history].every(f=>
 !f.fixture && !f.instrument.startsWith('TEST:') &&
 f.target_definition===({official_total_return:'direction:official-total-return:v1',official_price_return:'direction:official-price-return:v1',adjusted_price:'direction:action-adjusted-ex-dividend:v1'}[f.return_basis]) &&
 f.target_session>f.reference_session && new Date(f.next_open_at)<=new Date(f.expires_at) &&
 (f.p_up===null ? f.p_not_up===null && f.signal==='unavailable' :
 f.p_not_up!==null && Math.abs(f.p_up+f.p_not_up-1)<1e-10 && !!f.model_version && bundle.model_versions.includes(f.model_version)) &&
 new Date(f.cutoff)<=new Date(f.issued_at) && new Date(f.issued_at)<new Date(f.next_open_at) &&
 (!['up','not_up'].includes(f.signal) || f.validation_status==='validated' && !!f.scorecard && !f.suppression_reason));
}
async function fetchText(path:string){
 const response=await fetch(path,{cache:'no-store',signal:AbortSignal.timeout(12000)});
 if(!response.ok) throw new Error('Published file unavailable');
 const value=await response.text(); if(value.length>2_000_000) throw new Error('Bundle exceeds size limit'); return value;
}
export async function loadBundle():Promise<Loaded>{
 try{
  const pointer=JSON.parse(await fetchText('./data/latest.json'));
  if(!idPattern.test(pointer.bundle_id)||!idPattern.test(pointer.manifest_hash)) throw new Error('Invalid publication pointer');
  const base='./data/bundles/'+pointer.bundle_id+'/';
  const manifestText=await fetchText(base+'manifest.json');
  if(await hash(manifestText)!==pointer.manifest_hash) throw new Error('Manifest integrity check failed');
  const manifest=JSON.parse(manifestText);
  if(manifest.bundle_id!==pointer.bundle_id||Object.keys(manifest.files).join()!=='results.json') throw new Error('Manifest version mismatch');
  const raw=await fetchText(base+'results.json');
  if(await hash(raw)!==manifest.files['results.json']||await hash(raw)!==pointer.bundle_id) throw new Error('Results integrity check failed');
  const bundle:unknown=JSON.parse(raw);
  if(!validBundle(bundle)||JSON.stringify(bundle.model_versions)!==JSON.stringify(manifest.model_versions)) throw new Error('Results contract check failed');
  try{localStorage.setItem(KEY,JSON.stringify({raw,sha:pointer.bundle_id}));}catch{/* Quota failure must not hide a verified current result. */}
  return {bundle,offline:!navigator.onLine,error:null};
 }catch(error){
  const reason=error instanceof Error?error.message:'Unable to load publication';
  try{
   const cached=JSON.parse(localStorage.getItem(KEY)||'null');
   if(cached&&await hash(cached.raw)===cached.sha){
    const bundle:unknown=JSON.parse(cached.raw);
    if(validBundle(bundle))return {bundle,offline:!navigator.onLine,error:reason};
   }
  }catch{/* Reject damaged local cache. */}
  throw new Error(reason);
 }
}
export type Freshness={state:'current'|'historical'|'delayed'|'unknown'|'unavailable';label:string;reason:string};
export function freshness(bundle:Bundle,forecast:Forecast|undefined,now:number):Freshness{
 if(!forecast || forecast.p_up===null) return {state:'unavailable',label:'No trained forecast',reason:forecast?.suppression_reason||bundle.reason||'No forecast available.'};
 if(now>=Date.parse(forecast.expires_at)) return {state:'historical',label:'Historical forecast - expired',reason:'Its target session has ended. This cached forecast is history.'};
 if(!bundle.calendar_coverage_until || now>=Date.parse(bundle.calendar_coverage_until))return {state:'unknown',label:'Calendar coverage unknown',reason:'Freshness cannot be established beyond the verified exchange calendar.'};
 if(now<Date.parse(bundle.generated_at)-300000)return {state:'unknown',label:'Check device clock',reason:'Device time precedes this publication.'};
 if(bundle.status!=='ready'||!bundle.update_due_at||now>Date.parse(bundle.update_due_at)||now>Date.parse(forecast.update_due_at))
 return {state:'delayed',label:'Data delayed',reason:'The expected update deadline passed. A scheduler failure cannot keep this signal current.'};
 return {state:'current',label:'Current research estimate',reason:'Issued before the next session opened; target and update deadlines are still valid.'};
}
export const pkTime=(value:string|null|undefined)=>value?new Intl.DateTimeFormat('en-PK',{timeZone:'Asia/Karachi',dateStyle:'medium',timeStyle:'short'}).format(new Date(value)):'Not available';
export const probability=(value:number|null|undefined)=>value==null?'\u2014':(value*100).toFixed(1)+'%';
export function safeURL(value:unknown):string|undefined{
 if(typeof value!=='string')return undefined;
 try{const url=new URL(value); return url.protocol==='https:'&&!url.username&&!url.password?url.href:undefined;}catch{return undefined;}
}
