import {normalizePack,makeIndex,selectedPassages} from './personal-data.mjs';
let documents=[],index=makeIndex([]);
self.onmessage=({data})=>{
  try {
    if(data.action==='load') {
      documents=normalizePack(data.pack);index=makeIndex(documents);
      self.postMessage({id:data.id,result:{documents:documents.length,
        chunks:documents.reduce((n,d)=>n+d.rows.length,0),active:documents.filter(d=>d.status==='active').length,
        titles:documents.map(d=>({id:d.id,title:d.title,status:d.status,chunks:d.rows.length}))}});
    } else if(data.action==='search')self.postMessage({id:data.id,result:selectedPassages(index,data.query)});
  } catch(e){self.postMessage({id:data.id,error:e.message});}
};
