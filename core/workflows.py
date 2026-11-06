"""V11 server-owned, checkpointed financial workflows.

The existing fact-plane Store supplies atomic SQLite / Mongo / private Blob CAS.
Only read-only deterministic tools are replayable here: no payments, emails,
LLM calls or third-party writes. A new HTTP request resumes an expired lease;
there is deliberately no untracked background task inside a Vercel function.
"""
from __future__ import annotations

import asyncio
import copy
import csv
import hashlib
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable
from pathlib import Path
from unified import tools as adapters

from jinshu import tools
from unified.tools import REQUIRED_PARAMS, execute

RECIPE_VERSION = 'wealth-workflow-1'
CODE_HASH = hashlib.sha256(Path(__file__).read_bytes()+Path(tools.__file__).read_bytes()+Path(adapters.__file__).read_bytes()).hexdigest()
LEASE_SECONDS = 45
MAX_ATTEMPTS = 3
MAX_RUNS_PER_OWNER = 20
MAX_TOTAL_RUNS = 100
MAX_INPUT_BYTES = 180_000
LABELS = {'KEEP': '规则检查通过，仍须独立复核', 'REVIEW': '存在待核对项', 'REWRITE': '硬校验失败，禁止批准导出'}


class Conflict(ValueError):
    """A stale version, conflicting key, or invalid state transition."""


@dataclass(frozen=True)
class Principal:
    owner: str
    username: str
    role: str


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def nodes_for(workflow: str) -> dict:
    if workflow == 'wealth_review':
        return {'validate': [], 'weekly_report': ['validate'], 'wealth_benchmark': ['validate'],
                'verify': ['weekly_report', 'wealth_benchmark'], 'report': ['verify']}
    if workflow not in REQUIRED_PARAMS:
        raise ValueError('未登记的业务流程')
    return {'validate': [], workflow: ['validate'], 'verify': [workflow], 'report': ['verify']}


def required_sources(workflow):
    names = ['weekly_report', 'wealth_benchmark'] if workflow == 'wealth_review' else [workflow]
    return list(dict.fromkeys(f for name in names for f in tools.FILES[name]))


def snapshot(workflow, values, sources, examples):
    nodes_for(workflow)
    if not isinstance(values, dict) or type(examples) is not bool:
        raise ValueError('参数须为对象，示例开关须为布尔值')
    allowed = REQUIRED_PARAMS['wealth_benchmark'] if workflow == 'wealth_review' else REQUIRED_PARAMS[workflow]
    if set(values) - set(allowed):
        raise ValueError('参数含未登记字段')
    missing = [k for k in allowed if values.get(k) in (None, '')]
    if missing:
        raise ValueError('缺少参数：' + '、'.join(missing))
    # Examples are frozen at submission, never silently substituted during replay.
    if examples:
        if sources not in (None, {}):
            raise ValueError('示例模式不接受自填数据；修改示例请切换为用户输入')
        sources = {name: tools.source(name) for name in required_sources(workflow)}
    if not isinstance(sources, dict) or set(sources) != set(required_sources(workflow)):
        raise ValueError('请提供完整数据文件：' + '、'.join(required_sources(workflow)))
    declared_synthetic = examples or any(isinstance(v, dict) and v.get('synthetic') is True for v in sources.values())
    payload = {'workflow': workflow, 'values': values, 'sources': sources, 'synthetic': declared_synthetic,
               'source_mode': 'bundled_example' if examples else 'user_supplied'}
    if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > MAX_INPUT_BYTES:
        raise ValueError('可恢复任务输入最多180KB；请先筛选同口径数据')
    return copy.deepcopy(payload)


def node_key(name, payload):
    if name in REQUIRED_PARAMS:
        return fingerprint({'recipe': RECIPE_VERSION, 'code': CODE_HASH, 'tool': name,
                            'values': {k: payload['values'][k] for k in REQUIRED_PARAMS[name]},
                            'sources': {f: payload['sources'][f] for f in tools.FILES[name]},
                            'synthetic': payload['synthetic']})
    return fingerprint({'recipe': RECIPE_VERSION, 'code': CODE_HASH, 'node': name, 'input': payload})


def new_nodes(payload, previous=None):
    result = {}
    for name, depends in nodes_for(payload['workflow']).items():
        key = node_key(name, payload)
        old = (previous or {}).get(name, {})
        if old.get('status') == 'succeeded' and old.get('fingerprint') == key:
            result[name] = copy.deepcopy(old) | {'reused': True}
        else:
            result[name] = {'id': name, 'depends': depends, 'fingerprint': key,
                            'status': 'pending', 'attempts': 0, 'reused': False,
                            'result': None, 'error': None, 'duration_ms': None}
    return result


def verify_results(results):
    """Rules label data quality, not confidence and not institutional approval."""
    warnings, failures = [], []
    for name, record in results.items():
        body = record.get('result', {})
        warnings.extend({'tool': name, 'detail': issue} for issue in body.get('issues', []))
        if body.get('passed') is False:
            failures.append({'tool': name, 'detail': '算术恒等式或必填字段校验未通过',
                             'fields': body.get('missing_fields', []), 'checks': body.get('checks')})
        if name == 'kep':
            warnings.extend({'tool': name, 'detail': '案件记录需人工核实', 'case_id': r.get('case_id')}
                            for r in body.get('rows', []) if r.get('status') != 'found_sent_record')
        if name in ('issuance', 'material_fill', 'onboarding', 'strategy'):
            warnings.append({'tool': name, 'detail': '日历/业务口径或候选规则需要人工确认；不执行外部业务'})
    label = 'REWRITE' if failures else 'REVIEW' if warnings else 'KEEP'
    return {'label': label, 'description': LABELS[label], 'warnings': warnings,
            'failures': failures, 'can_review': not failures, 'confidence_score': None,
            'scope': '确定性工具结果检查；不是模型质量、合规结论或真实业务收益'}


def run_node(name, payload, completed):
    if name == 'validate':
        for filename, rows in payload['sources'].items():
            if filename.endswith('.csv'):
                if not isinstance(rows, list) or not rows or len(rows) > 1500 or not all(isinstance(x, dict) for x in rows):
                    raise ValueError('CSV数据须为1至1500行的对象数组')
        return {'input_hash': fingerprint(payload), 'source_hashes': {k: fingerprint(v) for k, v in payload['sources'].items()}}
    if name in REQUIRED_PARAMS:
        record = execute(name, {k: payload['values'][k] for k in REQUIRED_PARAMS[name]},
                         sources={f: payload['sources'][f] for f in tools.FILES[name]}, examples=False)
        record['synthetic'] = payload['synthetic']
        record['input_mode'] = 'synthetic_example' if payload['synthetic'] else 'user_supplied'
        return record
    calculations = {k: v for k, v in completed.items() if k in REQUIRED_PARAMS}
    if name == 'verify':
        return verify_results(calculations)
    quality = completed['verify']
    return {'title': '周报质检与同业对标复核包' if payload['workflow'] == 'wealth_review' else '业务任务复核包',
            'quality': quality, 'calculations': calculations,
            'input_hash': fingerprint(payload), 'recipe_version': RECIPE_VERSION,
            'synthetic': payload['synthetic'], 'business_action_executed': False,
            'summary': [{'tool': k, 'rows': len(v.get('result', {}).get('rows', [])),
                         'summary': v.get('result', {}).get('summary', {})} for k, v in calculations.items()],
            'next_action': '请核对数据口径、异常和来源，提交另一账号复核；所有输出仍为业务草稿'}


def event(row, kind, **detail):
    row['events'].append({'at': time.time(), 'kind': kind, **detail})
    row['events'] = row['events'][-80:]


class WorkflowService:
    def __init__(self, store, runner: Callable = run_node, clock: Callable = time.time):
        self.store, self.runner, self.clock = store, runner, clock

    @staticmethod
    def _row(state, run_id, person, *, write=False):
        row = state.get('workflow_runs', {}).get(run_id)
        owns = row and row['owner'] == person.owner and row['author'] == person.username
        review_access = row and person.role == 'reviewer' and row['status'] in ('needs_review', 'approved', 'rejected')
        if not owns and (write or not review_access):
            raise PermissionError('任务不存在或无权访问')
        return row

    async def read(self, run_id, person):
        return copy.deepcopy(self._row(await self.store.read(), run_id, person))

    async def list(self, person, queue=False):
        if queue and person.role != 'reviewer':
            raise PermissionError('复核队列需要审核角色')
        state = await self.store.read()
        records = state.get('workflow_runs', {}).values()
        if queue:
            rows = [r for r in records if r['status'] == 'needs_review' and r['author'] != person.username]
        else:
            rows = [r for r in records if r['owner'] == person.owner and r['author'] == person.username]
        return sorted(({k: r[k] for k in ('id', 'workflow', 'author', 'revision', 'status', 'created_at', 'updated_at', 'quality')}
                       for r in rows), key=lambda r: r['created_at'], reverse=True)

    async def create(self, person, request_id, payload):
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
            raise ValueError('请求标识须为8至80位字母、数字、下划线或短横线')
        key = fingerprint([person.owner, person.username, request_id])[:32]
        submitted = fingerprint(payload)
        def save(state):
            runs = state.setdefault('workflow_runs', {})
            if key in runs:
                old = runs[key]
                if old['submitted_hash'] != submitted:
                    raise Conflict('同一请求标识已用于不同输入，请使用新标识')
                return old
            if len(runs) >= MAX_TOTAL_RUNS or sum(r['owner'] == person.owner for r in runs.values()) >= MAX_RUNS_PER_OWNER:
                raise ValueError('任务演示存储已达上限，请先导出并删除已完成任务')
            row = {'id': key, 'owner': person.owner, 'author': person.username, 'request_id': request_id,
                   'workflow': payload['workflow'], 'recipe_version': RECIPE_VERSION, 'code_hash': CODE_HASH,
                   'payload': payload, 'submitted_hash': submitted, 'input_hash': submitted,
                   'revision': 1, 'status': 'pending', 'nodes': new_nodes(payload),
                   'lease': None, 'quality': None, 'approval': None, 'events': [],
                   'created_at': self.clock(), 'updated_at': self.clock()}
            event(row, 'created'); runs[key] = row
            return row
        return await self.store.mutate(save)

    async def edit(self, run_id, person, revision, payload):
        def change(state):
            row = self._row(state, run_id, person, write=True)
            if revision != row['revision']:
                raise Conflict('任务版本已改变，请刷新')
            if row['workflow'] != payload['workflow']:
                raise ValueError('已有任务不可改变流程类型')
            row.update(payload=payload, input_hash=fingerprint(payload), revision=revision+1,
                       nodes=new_nodes(payload, row['nodes']), recipe_version=RECIPE_VERSION, code_hash=CODE_HASH, status='pending', approval=None,
                       quality=None, lease=None, updated_at=self.clock())
            event(row, 'input_changed', reused=[k for k, n in row['nodes'].items() if n['reused']])
            return row
        return await self.store.mutate(change)

    async def advance(self, run_id, person, revision):
        lease_id = uuid.uuid4().hex
        def claim(state):
            row = self._row(state, run_id, person, write=True)
            if row['revision'] != revision or row['recipe_version'] != RECIPE_VERSION or row.get('code_hash') != CODE_HASH:
                raise Conflict('输入或流程版本已改变，请重新保存后执行')
            if row['status'] in ('needs_review', 'approved', 'rejected', 'blocked'):
                return row, []
            if row['lease'] and row['lease']['until'] > self.clock():
                raise Conflict('已有执行批次处理中；刷新查看状态，不重复提交')
            if row['lease']:
                for node in row['nodes'].values():
                    if node['status'] == 'running':
                        node['status'] = 'pending'
                event(row, 'lease_recovered')
            # A crash can happen after a checkpoint but before batch settlement.
            # Finalize from persisted results before selecting any new work.
            verified = row['nodes']['verify']
            if verified['status'] == 'succeeded':
                row['quality'] = verified['result']
                if not verified['result']['can_review']:
                    row.update(status='blocked', lease=None, updated_at=self.clock())
                    return row, []
            if all(n['status'] == 'succeeded' for n in row['nodes'].values()):
                row.update(status='needs_review', lease=None, updated_at=self.clock())
                event(row, 'checkpoint_settled')
                return row, []
            candidates = [n for n in row['nodes'].values() if n['status'] in ('pending', 'failed')
                          and n['attempts'] < MAX_ATTEMPTS
                          and all(row['nodes'][d]['status'] == 'succeeded' for d in n['depends'])]
            chosen = candidates[:2]
            if not chosen:
                row['status'] = 'attention'
                return row, []
            for node in chosen:
                node.update(status='running', attempts=node['attempts']+1, error=None)
            row.update(lease={'id': lease_id, 'until': self.clock()+LEASE_SECONDS}, status='running', updated_at=self.clock())
            event(row, 'batch_claimed', nodes=[n['id'] for n in chosen])
            return row, [n['id'] for n in chosen]
        row, selected = await self.store.mutate(claim)
        if not selected:
            return row
        payload = row['payload']
        completed = {k: n['result'] for k, n in row['nodes'].items() if n['status'] == 'succeeded'}

        async def one(name):
            start = time.perf_counter()
            try:
                result = await asyncio.wait_for(asyncio.to_thread(self.runner, name, payload, completed), timeout=20)
                # Validate serialized results before entering a retried CAS mutation.
                json.dumps(result, ensure_ascii=False, allow_nan=False)
                error = None
            except (ValueError, KeyError, TypeError, OverflowError, asyncio.TimeoutError) as exc:
                result = None
                error = str(exc)[:240] if isinstance(exc, ValueError) else '数据字段、类型或执行时间不符合要求'
            except Exception:
                result, error = None, '执行失败，未确认成功；请复核数据或重试'
            duration = round((time.perf_counter()-start)*1000, 2)
            def finish(state):
                current = self._row(state, run_id, person, write=True)
                if current['revision'] != revision or not current['lease'] or current['lease']['id'] != lease_id:
                    raise Conflict('迟到结果已丢弃，当前任务输入或执行所有权已改变')
                current['nodes'][name].update(status='failed' if error else 'succeeded', result=result,
                                              error=error, duration_ms=duration)
                event(current, 'node_failed' if error else 'node_completed', node=name, duration_ms=duration)
            await self.store.mutate(finish)
        outcomes = await asyncio.gather(*(one(name) for name in selected), return_exceptions=True)
        exceptions = [x for x in outcomes if isinstance(x, BaseException)]
        if exceptions:
            raise exceptions[0]
        def settle(state):
            current = self._row(state, run_id, person, write=True)
            if current['revision'] != revision or not current['lease'] or current['lease']['id'] != lease_id:
                raise Conflict('批次结果版本已失效')
            current['lease'] = None
            current['updated_at'] = self.clock()
            verify = current['nodes']['verify']
            if verify['status'] == 'succeeded':
                current['quality'] = verify['result']
                if not verify['result']['can_review']:
                    current['status'] = 'blocked'
                    event(current, 'hard_validation_blocked')
                    return current
            if all(n['status'] == 'succeeded' for n in current['nodes'].values()):
                current['status'] = 'needs_review'
            elif any(n['status'] == 'failed' for n in current['nodes'].values()):
                current['status'] = 'attention'
            else:
                current['status'] = 'pending'
            return current
        return await self.store.mutate(settle)

    async def review(self, run_id, person, revision, decision, reason):
        if person.role != 'reviewer':
            raise PermissionError('需要独立审核角色')
        if decision not in ('approve', 'reject') or not reason.strip() or len(reason) > 500:
            raise ValueError('需要有效复核决定及1至500字意见')
        def change(state):
            row = self._row(state, run_id, person)
            if row['revision'] != revision or row['status'] != 'needs_review' or row.get('code_hash') != CODE_HASH:
                raise Conflict('只能复核当前待审版本')
            if row['author'] == person.username:
                raise PermissionError('提交者不能审核自己的任务')
            if not row['quality']['can_review']:
                raise Conflict('硬校验失败，不能批准')
            row['approval'] = {'reviewer': person.username, 'reason': reason, 'decision': decision,
                               'revision': revision, 'input_hash': row['input_hash'],
                               'result_hash': fingerprint(row['nodes']['report']['result']), 'at': self.clock()}
            row['status'] = 'approved' if decision == 'approve' else 'rejected'
            event(row, 'review_'+decision, reviewer=person.username)
            return row
        return await self.store.mutate(change)

    async def export(self, run_id, person, revision, fmt='json'):
        row = await self.read(run_id, person)
        approval = row.get('approval') or {}
        result = row['nodes']['report']['result']
        if row['revision'] != revision or row.get('code_hash') != CODE_HASH or row['status'] != 'approved' or approval.get('input_hash') != row['input_hash'] or approval.get('result_hash') != fingerprint(result):
            raise Conflict('仅可导出已独立复核且未改变的任务版本')
        artifact = {'run_id': run_id, 'revision': revision, 'approval': approval, 'report': result,
                    'business_action_executed': False, 'code_hash': CODE_HASH, 'export_scope': 'server_held_reviewed_draft'}
        if fmt == 'json':
            return json.dumps(artifact, ensure_ascii=False, indent=2).encode(), 'application/json'
        if fmt != 'csv':
            raise ValueError('仅支持JSON或CSV')
        rows = []
        for name, calc in result['calculations'].items():
            rows.extend({'流程': name, '任务版本': revision, **r} for r in calc['result'].get('rows', []))
        fields = list(dict.fromkeys(k for r in rows for k in r))
        def safe(v):
            text = '' if v is None else str(v)
            return "'"+text if text.lstrip().startswith(('=', '+', '-', '@')) else text
        out = io.StringIO(newline=''); writer = csv.writer(out)
        writer.writerow([safe(k) for k in fields])
        writer.writerows([[safe(r.get(k)) for k in fields] for r in rows])
        return ('\ufeff'+out.getvalue()).encode(), 'text/csv; charset=utf-8'

    async def delete(self, run_id, person, revision):
        def remove(state):
            row = self._row(state, run_id, person, write=True)
            if row['revision'] != revision:
                raise Conflict('任务已更新')
            if row['status'] == 'running' and row['lease'] and row['lease']['until'] > self.clock():
                raise Conflict('执行批次处理中，请稍后删除')
            del state['workflow_runs'][run_id]
            return {'deleted': True, 'request_id_reuse_after_deletion_is_not_deduplicated': True}
        return await self.store.mutate(remove)

    async def metrics(self, person):
        state = await self.store.read()
        rows = [r for r in state.get('workflow_runs', {}).values()
                if r['owner'] == person.owner and r['author'] == person.username]
        nodes = [n for r in rows for n in r['nodes'].values()]
        return {'submitted': len(rows), 'awaiting_review': sum(r['status']=='needs_review' for r in rows),
                'approved': sum(r['status']=='approved' for r in rows),
                'blocked': sum(r['status']=='blocked' for r in rows),
                'failed_steps': sum(n['status']=='failed' for n in nodes),
                'step_attempts': sum(n['attempts'] for n in nodes),
                'reused_steps_current_revision': sum(n['reused'] for n in nodes),
                'lease_recoveries_retained_events': sum(e['kind']=='lease_recovered' for r in rows for e in r['events']),
                'scope': '本人保留任务的操作统计；不是正确率、真实用户收益或压测结果'}
