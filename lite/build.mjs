import {createHash} from 'node:crypto';
import {cp,mkdir,rm,writeFile,readFile,access} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for(const [from,to] of [['node_modules/jszip/dist/jszip.min.js','jszip.min.js'],['node_modules/pdfjs-dist/build/pdf.mjs','pdf.mjs'],['node_modules/pdfjs-dist/build/pdf.worker.mjs','pdf.worker.mjs'],['node_modules/pdfjs-dist/cmaps','cmaps'],['node_modules/jszip/LICENSE.markdown','JSZIP_LICENSE.md'],['node_modules/pdfjs-dist/LICENSE','PDFJS_LICENSE.txt']]){try{await access(from);await cp(from,'web/vendor/'+to,{recursive:true});}catch(e){if(e.code!=='ENOENT')throw e;await access('web/vendor/'+to);}}
await rm('dist',{recursive:true,force:true});await cp('web','dist',{recursive:true});
await writeFile('dist/build-info.json',JSON.stringify({version:'7.0.0',evaluatorHash:createHash('sha256').update((await Promise.all(['core.mjs','assurance.mjs','constraints.mjs','policy.mjs','readability.mjs','benchmarking.mjs','tools.mjs'].map(async p=>p+'\n'+await readFile('web/'+p,'utf8')))).join('\n')).digest('hex'),commit:process.env.VERCEL_GIT_COMMIT_SHA||process.env.GITHUB_SHA||'local',built_at:new Date().toISOString(),mode:'browser_lexical',no_model_weights:true},null,2));
console.log('Built static Lite; vendor scripts included, no fonts/model weights/private corpus.');
