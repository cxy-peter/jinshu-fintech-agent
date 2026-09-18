"""Small, explicit local recovery ledger and ticket outbox.
The ledger affects this instance only. It is not a distributed rollback service.
"""
from __future__ import annotations
import asyncio, hashlib, json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
import httpx


def timestamp(): return datetime.now(timezone.utc).isoformat()

def load(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

class RecoveryController:
    def __init__(self, directory):
        self.path=Path(directory)/'recovery.json'
        self.state=load(self.path, {'families':{}, 'events':[], 'scope':'single_instance'})
        self.lock=asyncio.Lock()
    def frozen(self, family):return self.state['families'].get(family,{}).get('frozen',False)
    async def rollback(self, family, skill_id, remote, reason):
        async with self.lock:
            # Freeze before contacting the control API. Next request ignores experimental skills.
            record={'frozen':True,'candidate':skill_id,'last_stable':'base_'+family,
                    'reason':reason,'status':'local_frozen_remote_pending','at':timestamp()}
            self.state['families'][family]=record;save(self.path,self.state)
            try:
                await asyncio.wait_for(remote(),timeout=5)
                record['status']='remote_rollback_confirmed'
            except Exception as exc:
                record['status']='local_baseline_remote_unconfirmed'
                record['error']=type(exc).__name__
            self.state['events'].append(dict(family=family,**record));save(self.path,self.state)
            return record|{'note':'本实例已停止候选流量；远端状态未确认时不声称所有实例都已回滚。'}
    def resume(self,family,actor):
        record=self.state['families'].get(family)
        if record and record['status']!='remote_rollback_confirmed':
            raise ValueError('先重试并确认远端回滚，再解除本地冻结；接口恢复不自动恢复候选流量')
        if record:record.update(frozen=False,resumed_by=actor,resumed_at=timestamp())
        save(self.path,self.state);return record or {'frozen':False}

class TicketOutbox:
    def __init__(self,directory,submitter=None):
        self.path=Path(directory)/'ticket_outbox.json';self.rows=load(self.path,[])
        self.submitter=submitter;self.lock=asyncio.Lock()
    def list(self):return list(self.rows)
    def draft(self,session_key,summary):
        key=hashlib.sha256((session_key+'\n'+summary).encode()).hexdigest()
        found=next((r for r in self.rows if r['idempotency_key']==key),None)
        if found:return found
        row={'id':'ticket_'+uuid.uuid4().hex[:16],'idempotency_key':key,'session_key':session_key,
             'summary':summary,'status':'pending_submission','attempts':0,'created_at':timestamp()}
        self.rows.append(row);save(self.path,self.rows);return row
    async def submit(self,row):
        async with self.lock:
            if row['status']=='submitted':return row
            row['attempts']+=1;row['updated_at']=timestamp()
            try:
                if self.submitter is None:raise ConnectionError('No authorized ticket endpoint configured')
                result=await asyncio.wait_for(self.submitter(row),timeout=5)
                if not isinstance(result,dict) or not result.get('ticket_id'):raise ValueError('Missing server receipt')
                row.update(status='submitted',server_ticket_id=result['ticket_id'])
            except Exception as exc:
                row.update(status='pending_submission',error=type(exc).__name__,
                    note='工单尚未确认提交，草稿已在本实例保存；同一幂等键重试，远端仍需支持幂等。')
            save(self.path,self.rows);return row
