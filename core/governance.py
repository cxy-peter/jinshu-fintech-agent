"""Review, five memory boundaries and human-gated policy loop for the V10 UI.
The original enterprise implementation remains under jinshu/ and engine/.
"""
from __future__ import annotations
import copy
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from .rag import active_documents, candidates, digest, rank

DEPARTMENTS={'dept_wealth':'理财产品','dept_release':'发行与报表','dept_risk':'准入与风控','dept_service':'客服知识','shared':'公共流程'}
CATEGORIES={'retrieval':'召回遗漏','intent':'理解或流程错误','generation':'回答与资料不符','knowledge_gap':'知识缺口'}
ACCOUNTS=[{'username':'editor','password':'demo-editor','role':'editor','name':'资料编辑'},
          {'username':'reviewer','password':'demo-reviewer','role':'reviewer','name':'独立审核'},
          {'username':'operations','password':'demo-operations','role':'operator','name':'运营观察'}]
TEMPLATES={'direct':'先直接回答，再列出依据与待确认事项。','checklist':'按核对清单列出步骤、来源和人工复核项。','compare':'按口径、差异、依据组织对比。'}

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def audit(state,action,actor,**details):
    state['audit'].append(dict(id=uid(),at=now(),action=action,actor=actor,**details))
    state['audit']=state['audit'][-300:]

def owner(request):
    token=request.cookies.get('jinshu_owner','')
    return digest(token) if len(token)==64 else None

def actor(state,request):
    token=request.cookies.get('jinshu_session','')
    session=state['sessions'].get(digest(token)) if token else None
    if not session or session['expires']<time.time(): return None
    return session

def login(state,username,password,env):
    users=ACCOUNTS if env.get('JINSHU_DEMO_ACCOUNTS')=='1' else []
    # Custom accounts require server-managed scrypt hashes, not public passwords.
    configured=json.loads(env.get('JINSHU_USERS_JSON','[]'))
    match=next((u for u in users if u['username']==username),None)
    valid=match and hmac.compare_digest(digest(password),digest(match['password']))
    if not valid:
        match=next((u for u in configured if u['username']==username),None)
        if match:
            expected=hashlib.scrypt(password.encode(),salt=bytes.fromhex(match['salt']),n=16384,r=8,p=1).hex()
            valid=hmac.compare_digest(expected,match['password_hash'])
    if not valid: raise PermissionError('账号或密码错误。这里不是 DeepSeek API Key。')
    if match['role'] not in ('editor','reviewer','operator'): raise PermissionError('无效账号角色')
    state['sessions']={k:v for k,v in state['sessions'].items() if v['expires']>time.time()}
    if len(state['sessions'])>=100: raise ValueError('演示登录会话已满，请稍后重试。')
    token=secrets.token_hex(32)
    who={k:match[k] for k in ('username','role','name')}
    state['sessions'][digest(token)]=who|{'expires':time.time()+4*3600}
    return token,who

def require(who,*roles):
    if not who or who['role'] not in roles: raise PermissionError('请使用有权限的账号登录。')

def publish(state,did,who,decision,reason,external_allowed):
    require(who,'reviewer')
    d=state['documents'].get(did)
    if not d or d['status']!='pending': raise ValueError('资料不在待审状态')
    if d['author']==who['username']: raise PermissionError('不能审核自己提交的资料')
    if not reason.strip(): raise ValueError('请填写审核意见')
    if decision=='reject': d.update(status='rejected',reviewer=who['username'],review_note=reason)
    else:
        old=[x for x in state['documents'].values() if x['status']=='active' and x['topic']==d['topic'] and x['department']==d['department']]
        if any(x['version']>=d['version'] for x in old): raise ValueError('版本必须高于当前已发布版本')
        from datetime import date
        today=date.today().isoformat()
        if (d.get('effective') and d['effective']>today) or (d.get('expires') and d['expires']<today): raise ValueError('资料不在生效期内')
        for previous in old: previous['status']='archived'; d['replaces']=previous['id']
        d.update(status='active',reviewer=who['username'],review_note=reason,external_allowed=external_allowed,published_at=now())
    audit(state,'document_'+decision,who['username'],doc_id=did,version=d['version'])
    return d

def binding(state,skill):
    data={'skill':{k:skill[k] for k in ('id','terms','top_k','template','department')},
          'documents':[(d['id'],d['version'],[c['hash'] for c in d['chunks']]) for d in [d for d in active_documents(state,skill['department']) if d['external_allowed']]],
          'cases':[state['feedback'].get(x) for x in skill['feedback_ids']], 'evaluator':'paired-retrieval-v1'}
    return digest(json.dumps(data,ensure_ascii=False,sort_keys=True))

def propose(state,who,feedback_ids,top_k,terms,template):
    require(who,'editor','operator','reviewer')
    cases=[state['feedback'][i] for i in feedback_ids if i in state['feedback']]
    if not cases: raise ValueError('请先选取反馈记录')
    department=cases[0]['department']
    if any(c['department']!=department for c in cases): raise ValueError('不同部门的问题请分开建候选')
    if all(c['category']=='knowledge_gap' for c in cases):
        raise ValueError('知识缺口先补资料并独立审核，不能让 Skill 编造事实。')
    source_text='\n'.join(c['text'] for d in active_documents(state,department) if d['external_allowed'] for c in d['chunks'])
    if any(t not in source_text for t in terms): raise ValueError('扩展词必须能在当前有效资料中找到；请先补齐知识缺口。')
    skill=dict(id=uid(),author=who['username'],department=department,terms=terms,top_k=top_k,template=template,
        status='draft',rollout=0,feedback_ids=[c['id'] for c in cases],created_at=now(),replay=None)
    state['skills'][skill['id']]=skill
    audit(state,'skill_proposed',who['username'],skill_id=skill['id'])
    return skill

def replay(state,sid,who):
    require(who,'editor','reviewer','operator')
    skill=state['skills'].get(sid)
    if not skill or skill['status'] not in ('draft','evaluated'): raise ValueError('只回放未发布候选')
    rows=candidates([d for d in active_documents(state,skill['department']) if d['external_allowed']]); details=[]; seen=set()
    for fid in skill['feedback_ids']:
        case=state['feedback'].get(fid)
        if not case or case['query'] in seen: continue
        seen.add(case['query']); expected=set(case.get('expected_docs',[]))
        # Labels are human-selected document ids, never inferred from candidate output.
        baseline=rank(case['query'],rows,top_k=4)
        treatment=rank(case['query']+' '+' '.join(skill['terms']),rows,top_k=skill['top_k'])
        b=bool(expected & {s['doc_id'] for s in baseline}); t=bool(expected & {s['doc_id'] for s in treatment})
        valid=bool(expected) and expected<={d['doc_id'] for d in rows}
        details.append(dict(feedback_id=fid,query=case['query'],label_valid=valid,baseline_hit=b,candidate_hit=t,
                            baseline_ids=[s['doc_id'] for s in baseline],candidate_ids=[s['doc_id'] for s in treatment]))
    passed=len(details)>=3 and all(c['label_valid'] and c['candidate_hit'] and c['candidate_hit']>=c['baseline_hit'] for c in details)
    skill['replay']=dict(at=now(),sample_count=len(details),passed=passed,details=details,binding=binding(state,skill),
        scope='确定性关键词召回回放；不代表生成准确率、神经重排收益或统计显著性',
        strict_improvements=sum(c['candidate_hit'] and not c['baseline_hit'] for c in details))
    skill['status']='evaluated'
    audit(state,'skill_replay',who['username'],skill_id=sid,passed=passed)
    return skill

def release(state,sid,who,action):
    require(who,'reviewer')
    skill=state['skills'].get(sid)
    if not skill: raise ValueError('候选不存在')
    if skill['author']==who['username']: raise PermissionError('候选发布需要另一位审核人')
    if action=='rollback':
        if skill['status']!='active': raise ValueError('候选没有在运行')
        skill.update(status='rolled_back',rollout=0)
    elif action=='canary':
        if skill['status']!='evaluated' or not skill['replay']['passed']: raise ValueError('至少三个不同且有人工目标标注的问题回放通过后才能灰度')
        if skill['replay']['binding']!=binding(state,skill): raise ValueError('资料、样本或候选发生变化，请重新回放')
        if any(s['status']=='active' and s['department']==skill['department'] for s in state['skills'].values()): raise ValueError('同部门已有灰度策略，请先回滚旧策略')
        skill.update(status='active',rollout=5,reviewer=who['username'])
    elif action=='promote':
        if skill['status']!='active' or skill['replay']['binding']!=binding(state,skill): raise ValueError('策略或资料已变，请重新回放')
        metrics=skill_metrics(state,sid)
        if min(metrics[g]['n'] for g in ('control','treatment'))<5: raise ValueError('每组至少五个不同浏览器标识明确反馈后才允许扩量；不是实名用户或统计显著性证明')
        if metrics['treatment']['rate']<metrics['control']['rate']: raise ValueError('处理组低于基线，请先检查或回滚')
        steps=[5,20,50,100];skill['rollout']=steps[min(steps.index(skill['rollout'])+1,3)]
    audit(state,'skill_'+action,who['username'],skill_id=sid,rollout=skill['rollout'])
    return skill

def skill_metrics(state,sid):
    out={}
    for group in ('control','treatment'):
        users={f['owner']:f for f in state['feedback'].values() if f.get('skill_id')==sid and f.get('group')==group}
        out[group]={'n':len(users),'rate':sum(f['resolved'] for f in users.values())/len(users) if users else None}
    return out

def policy(state,owner_id,department):
    for skill in state['skills'].values():
        if skill['status']=='active' and skill['department'] in (department,'all'):
            # Superseded evidence invalidates a previously reviewed treatment immediately.
            if skill['replay']['binding']!=binding(state,skill): continue
            bucket=int(digest(owner_id+'|'+skill['id'])[:8],16)%100
            group='treatment' if bucket<skill['rollout'] else 'control'
            return skill,group
    return None,'baseline'

def dashboard(state):
    feedback=list(state['feedback'].values()); total=len(feedback)
    resolved=sum(f['resolved'] for f in feedback)
    conversations=list(state['conversations'].values())
    turns=[m for c in conversations for m in c['turns'] if m['role']=='assistant']
    rates=dict(resolution=resolved/total if total else None,feedback_coverage=total/len(turns) if turns else None)
    return dict(documents=[{k:v for k,v in d.items() if k not in ('chunks','text')} for d in state['documents'].values()],
        feedback=feedback,skills=[s|{'metrics':skill_metrics(state,s['id'])} for s in state['skills'].values()],audit=state['audit'][-50:],
        metrics={'answered_turns':len(turns),'feedback_count':total,'resolved_count':resolved,**rates,
                 'categories':{k:sum(f['category']==k for f in feedback if not f['resolved']) for k in CATEGORIES},
                 'scope':'本空间实际保存记录；没有反馈不算解决；与历史离线评测及真实机构业务收益分开'},
        alerts=[{'level':'red','message':'已反馈问题的解决率低于 60%，请查看具体上下文。'}] if total>=5 and rates['resolution']<.6 else [])
