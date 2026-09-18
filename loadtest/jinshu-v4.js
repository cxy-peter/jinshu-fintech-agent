// Run only against an authorized test deployment, starting at low load.
import http from 'k6/http';
import {check,sleep} from 'k6';
import {Rate,Counter,Trend} from 'k6/metrics';
const taskOK=new Rate('task_verified');
const generated=new Rate('live_generation_returned');
const failed=new Counter('task_errors');
const latency=new Trend('task_latency_ms',true);
const base=__ENV.BASE_URL||'http://127.0.0.1:8766';
const vus=Number(__ENV.VUS||1);
export const options={vus,duration:__ENV.DURATION||'60s',thresholds:{http_req_failed:['rate<0.05']}};
export function setup(){
  if(!__ENV.TOKEN)throw new Error('Set TOKEN from an authorized test account; never commit it.');
  return {};
}
export default function(){
  const started=Date.now();
  const response=http.post(base+'/api/ask',JSON.stringify({workflow:'service',query:'工单接口不可用时应当怎么处理？',allow_external:__ENV.ALLOW_EXTERNAL==='1'}),{
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+__ENV.TOKEN},timeout:__ENV.TIMEOUT||'180s'});
  latency.add(Date.now()-started);
  let data={};try{data=response.json();}catch(_){ }
  const verified=response.status===200 && !!data.verification?.passed;
  taskOK.add(verified);
  const mode=data.execution?.answer_mode;
  generated.add(verified && (mode==='llm'||mode==='pi_runtime'));
  if(!verified)failed.add(1);
  check(response,{'HTTP 200':r=>r.status===200,'task verified':()=>verified});
  sleep(Number(__ENV.PAUSE||1));
}
export function handleSummary(data){return {'k6-summary.json':JSON.stringify({scope:'authenticated business path, synthetic test load',configured_vus:vus,data},null,2)};}
