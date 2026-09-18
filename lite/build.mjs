import {cp,mkdir,rm,writeFile} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for(const [from,to] of [['node_modules/jszip/dist/jszip.min.js','jszip.min.js'],['node_modules/pdfjs-dist/build/pdf.mjs','pdf.mjs'],['node_modules/pdfjs-dist/build/pdf.worker.mjs','pdf.worker.mjs'],['node_modules/pdfjs-dist/cmaps','cmaps'],['node_modules/jszip/LICENSE.markdown','JSZIP_LICENSE.md'],['node_modules/pdfjs-dist/LICENSE','PDFJS_LICENSE.txt']])await cp(from,'web/vendor/'+to,{recursive:true});
await rm('dist',{recursive:true,force:true});await cp('web','dist',{recursive:true});
await writeFile('dist/build-info.json',JSON.stringify({version:'5.0.0',built_at:new Date().toISOString(),mode:'browser_lexical',no_model_weights:true},null,2));
console.log('Built static Lite; vendor scripts included, no fonts/model weights/private corpus.');
