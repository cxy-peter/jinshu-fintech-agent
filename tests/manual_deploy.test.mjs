import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {prepareDeployment, included, ROOT_FILES} from '../scripts/prepare_deployment.mjs';
import {targetFromChoice, deployArguments, cleanupTemporary, CLI_VERSION} from '../scripts/manual_deploy.mjs';
const root=fileURLToPath(new URL('..',import.meta.url));
function fixture(t) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jinshu-core-test-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const source=path.join(dir,'source');fs.mkdirSync(source);
 for(const name of [...ROOT_FILES,'core/app.py','core/provider.py','core/web/index.html','core/web/app.js','data/synthetic/documents.json']){
  const p=path.join(source,name);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,'fixture');
 }
 return {dir,source,destination:path.join(dir,'release')};
}
for(const choice of [undefined,'','1','preview'])test('default preview '+String(choice),()=>assert.equal(targetFromChoice(choice),'preview'));
for(const choice of ['2','production'])test('explicit production '+choice,()=>assert.equal(targetFromChoice(choice),'production'));
test('cancel does nothing',()=>assert.equal(targetFromChoice('0'),null));
test('unknown target rejected',()=>assert.throws(()=>targetFromChoice('yes')));
test('preview uses no production flag or unnecessary confirmation',()=>assert.deepEqual(deployArguments('preview'),['deploy','--yes','--logs']));
test('production requires exact confirmation',()=>{assert.throws(()=>deployArguments('production'));assert.throws(()=>deployArguments('production','DEPLOY PREVIEW'));assert.ok(deployArguments('production','DEPLOY PRODUCTION').includes('--prod'));});
test('unknown deployment argument rejected',()=>assert.throws(()=>deployArguments('prod','DEPLOY PRODUCTION')));
for(const name of ['core/.env','core/.env.local','core/credentials.json','core/private.key','core/font.woff2','core/secret.json','core/__pycache__/x.pyc','core/private_corpus/customer.json'])test('exclude '+name,()=>assert.equal(included(name),false));
test('staging keeps actual default app and deterministic tools, not private files',t=>{
 const f=fixture(t);for(const name of ['.env','.env.local','.vercel/project.json','private_corpus/customer.json','core/.env','core/private_corpus/x.json']){const p=path.join(f.source,name);fs.mkdirSync(path.dirname(p),{recursive:true});fs.writeFileSync(p,'secret-sentinel');}
 const hashes=prepareDeployment(f.source,f.destination);assert.ok(hashes['core/app.py']);assert.ok(hashes['jinshu/tools.py']);
 for(const name of Object.keys(hashes))assert.notEqual(fs.readFileSync(path.join(f.destination,name),'utf8'),'secret-sentinel');
 assert.equal(fs.existsSync(path.join(f.destination,'.env')),false);assert.equal(JSON.parse(fs.readFileSync(path.join(f.destination,'release-manifest.json'))).mode,'core');
});
test('existing destination never overwritten',t=>{const f=fixture(t);fs.mkdirSync(f.destination);fs.writeFileSync(path.join(f.destination,'keep'),'data');assert.throws(()=>prepareDeployment(f.source,f.destination));assert.equal(fs.readFileSync(path.join(f.destination,'keep'),'utf8'),'data');});
test('cannot stage inside source',t=>{const f=fixture(t);assert.throws(()=>prepareDeployment(f.source,path.join(f.source,'release')));});
test('missing default app stops staging',t=>{const f=fixture(t);fs.unlinkSync(path.join(f.source,'core/app.py'));assert.throws(()=>prepareDeployment(f.source,f.destination),/Required/);});
test('symlink runtime file rejected',{skip:process.platform==='win32'?'symlink creation requires extra Windows privilege':false},t=>{const f=fixture(t);const p=path.join(f.source,'core/app.py');fs.unlinkSync(p);fs.symlinkSync(path.join(f.source,'index.py'),p);assert.throws(()=>prepareDeployment(f.source,f.destination),/symlink/);});
test('real source staged without enterprise imports or dependency payload',t=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'jinshu-real-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));const hashes=prepareDeployment(root,path.join(dir,'release'));assert.ok(Object.keys(hashes).length>=40);assert.ok(hashes['core/app.py']);assert.ok(hashes['jinshu/tools.py']);assert.ok(!hashes['jinshu/runtime.py']);assert.ok(!Object.keys(hashes).some(x=>x.startsWith('engine/')));});
test('valid minimal Vercel configuration',()=>{const c=JSON.parse(fs.readFileSync(path.join(root,'vercel.json')));assert.equal(c.framework,'fastapi');assert.equal(c.functions['index.py'].excludeFiles,undefined);assert.equal(c.git.deploymentEnabled,false);assert.ok(c.functions['index.py'].maxDuration<=300);});
test('cleanup retries and never throws instead of original deploy error',()=>{let opts,warning;assert.equal(cleanupTemporary('test-dir',(p,o)=>{opts=o;throw Error('EPERM');},x=>warning=x),false);assert.equal(opts.maxRetries,8);assert.match(warning,/test-dir/);});
test('cleanup success is observable',()=>assert.equal(cleanupTemporary('unused',()=>{}),true));
test('launcher help does not call network',()=>{const r=spawnSync(process.execPath,[path.join(root,'scripts/manual_deploy.mjs'),'--help'],{encoding:'utf8'});assert.equal(r.status,0);assert.match(r.stdout,/DEPLOY PRODUCTION/);});
test('both launchers use shared core index:app',()=>{for(const n of ['start_local.sh','start_local.bat']){const s=fs.readFileSync(path.join(root,n),'utf8');assert.ok(s.includes('-m uvicorn index:app'));assert.ok(!s.includes('-m jinshu serve'));}});
for(const fail of [false,true])test('actual child-process deploy flow with stub CLI; failure='+fail,t=>{
 const f=fixture(t);fs.mkdirSync(path.join(f.source,'scripts'),{recursive:true});for(const n of ['manual_deploy.mjs','prepare_deployment.mjs'])fs.copyFileSync(path.join(root,'scripts',n),path.join(f.source,'scripts',n));
 fs.mkdirSync(path.join(f.source,'.vercel'));fs.writeFileSync(path.join(f.source,'.vercel/project.json'),JSON.stringify({orgId:'team_test',projectId:'prj_test',projectName:'test-workbench'}));
 const bin=path.join(f.dir,'bin'),log=path.join(f.dir,'calls.jsonl');fs.mkdirSync(bin);
 const fake=path.join(bin,'fake.cjs');fs.writeFileSync(fake,`const fs=require('node:fs');const a=process.argv.slice(2);fs.appendFileSync(process.env.JINSHU_TEST_LOG,JSON.stringify(a)+'\\n');if(process.env.JINSHU_TEST_FAIL==='1'&&a.includes('deploy')&&!a.includes('--dry'))process.exit(17);console.log('stub-only');`);
 if(process.platform==='win32')fs.writeFileSync(path.join(bin,'npx.cmd'),`@echo off\r\nnode "${fake}" %*\r\nexit /b %errorlevel%\r\n`);
 else fs.writeFileSync(path.join(bin,'npx'),`#!/bin/sh\nexec "${process.execPath}" "${fake}" "$@"\n`,{mode:0o755});
 const r=spawnSync(process.execPath,[path.join(f.source,'scripts/manual_deploy.mjs'),'preview'],{encoding:'utf8',env:{...process.env,PATH:bin+path.delimiter+process.env.PATH,JINSHU_TEST_LOG:log,JINSHU_TEST_FAIL:fail?'1':'0'}});
 assert.equal(r.status,fail?1:0,r.stdout+r.stderr);assert.ok(!r.stderr.includes('DEP0190'));
 const calls=fs.readFileSync(log,'utf8').trim().split('\n').map(JSON.parse);assert.equal(calls.length,3);assert.ok(calls[0].includes('inspect'));assert.ok(calls[1].includes('--dry'));assert.ok(calls[2].includes('--logs'));assert.ok(!calls.some(a=>a.includes('link')||a.includes('--prod')));
 if(fail)assert.match(r.stderr,/Vercel CLI 失败/);
});
test('Windows launcher invokes same script, not shell:true JS',()=>{assert.ok(fs.readFileSync(path.join(root,'deploy_vercel.bat'),'utf8').includes('node scripts\\manual_deploy.mjs'));assert.ok(fs.readFileSync(path.join(root,'scripts/manual_deploy.mjs'),'utf8').includes('shell: false'));});
test('one shared actual default entrypoint',()=>assert.ok(fs.readFileSync(path.join(root,'index.py'),'utf8').includes('from core.app import app')));
