import {readdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
async function walk(dir){let out=[];for(const e of await readdir(dir,{withFileTypes:true})){const p=dir+'/'+e.name;if(e.isDirectory())out.push(...await walk(p));else out.push(p);}return out;}
const paths=(await walk('dist')).filter(p=>!p.includes('/data/')&&!p.endsWith('/sw.js'));
const fonts=paths.filter(p=>/latin-wght-normal.*\.woff2$/.test(p));
let html=await readFile('dist/index.html','utf8');
html=html.replace('</head>',fonts.map(p=>'<link rel="preload" as="font" type="font/woff2" crossorigin href="./'+p.slice(5)+'">').join('')+'</head>');
await writeFile('dist/index.html',html);
const resources=paths.map(p=>'./'+p.slice(5));
const version=createHash('sha256').update((await Promise.all(paths.map(p=>readFile(p)))).map(b=>b.toString('base64')).join()).digest('hex').slice(0,16);
const sw=`const CACHE='psx-shell-${version}';const FILES=${JSON.stringify(resources)};
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('psx-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(url.origin!==self.location.origin||event.request.method!=='GET')return;
 // Forecasts are network-first and are persisted by the client only after hash/schema validation.
 if(url.pathname.includes('/data/'))return;
 if(event.request.mode==='navigate'){event.respondWith(fetch(event.request).catch(()=>caches.match(new URL('./index.html',self.registration.scope),{ignoreVary:true})));return;}
 event.respondWith(caches.match(event.request,{ignoreVary:true}).then(cached=>cached||fetch(event.request)));
});
`;
await writeFile('dist/sw.js',sw);
console.log('Service worker generated:',version,resources.length,'app-shell files');
