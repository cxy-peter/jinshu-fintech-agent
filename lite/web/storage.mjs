/** Per-origin IndexedDB. This is visitor-local persistence, not server authorization. */
let db;
export async function openStore(){
 if(!db)db=await new Promise((resolve,reject)=>{const q=indexedDB.open('jinshu-lite-v5',1);q.onupgradeneeded=()=>q.result.createObjectStore('state');q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error)});
 return {
  load: key=>new Promise((resolve,reject)=>{const q=db.transaction('state').objectStore('state').get(key);q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error)}),
  save: (key,value)=>new Promise((resolve,reject)=>{const t=db.transaction('state','readwrite');t.objectStore('state').put(value,key);t.oncomplete=resolve;t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error)}),
  clear: ()=>new Promise((resolve,reject)=>{const t=db.transaction('state','readwrite');t.objectStore('state').clear();t.oncomplete=resolve;t.onerror=()=>reject(t.error)})
 };
}
export async function hash(data){const a=typeof data==='string'?new TextEncoder().encode(data):data;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',a))].map(v=>v.toString(16).padStart(2,'0')).join('')}
export function downloadBlob(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
