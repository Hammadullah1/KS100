import {readFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const sha=s=>createHash('sha256').update(s).digest('hex');
const pointer=JSON.parse(await readFile('dist/data/latest.json','utf8'));
if(!/^[a-f0-9]{64}$/.test(pointer.bundle_id))throw Error('Invalid bundle pointer');
const base='dist/data/bundles/'+pointer.bundle_id+'/';
const raw=await readFile(base+'results.json','utf8');const manifestRaw=await readFile(base+'manifest.json','utf8');
if(sha(raw)!==pointer.bundle_id||sha(manifestRaw)!==pointer.manifest_hash)throw Error('Bundle integrity failed');
const b=JSON.parse(raw);const manifest=JSON.parse(manifestRaw);
if(b.mode!=='production'||manifest.files['results.json']!==sha(raw))throw Error('Unsafe publication mode');
if(b.forecasts.some(f=>f.fixture||f.instrument.startsWith('TEST:')))throw Error('Fixture forecast leaked');
async function scan(dir){for(const e of await readdir(dir,{withFileTypes:true})){const p=dir+'/'+e.name;if(e.isDirectory())await scan(p);else{
 if(p.endsWith('.map')||/\.env/.test(e.name)||/\.parquet$/.test(e.name))throw Error('Forbidden public artifact '+p);
 if(e.name==='results.json'){const result=JSON.parse(await readFile(p,'utf8'));if(result.mode!=='production'||[...(result.forecasts||[]),...(result.history||[])].some(f=>f.fixture||f.instrument.startsWith('TEST:')))throw Error('Unsafe historical public bundle '+p);}
 if(/\.(js|json|html)$/.test(p)){const text=await readFile(p,'utf8');if(/(?:github_pat_|ghp_|sk-proj-)[A-Za-z0-9_]{20,}/.test(text)||/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY/.test(text))throw Error('Credential pattern in public artifact');}
}}}
await scan('dist');
console.log('Production bundle checked: no fixture forecasts, source maps, raw Parquet or credential patterns.');
