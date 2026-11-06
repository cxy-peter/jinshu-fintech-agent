"""Authenticated workflow API; exported data always comes from server checkpoints."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from typing import Literal

from . import governance as g
from .workflows import WorkflowService, Principal, snapshot, nodes_for, required_sources, Conflict
from jinshu import tools
from jinshu.fixtures import WORKFLOWS
from unified.tools import REQUIRED_PARAMS


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Payload(Input):
    workflow: str = Field(max_length=50)
    values: dict = Field(default_factory=dict)
    sources: dict | None = None
    use_examples: StrictBool = False


class Create(Payload):
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')


class Edit(Payload):
    revision: int = Field(ge=1, strict=True)


class Revision(Input):
    revision: int = Field(ge=1, strict=True)


class Review(Revision):
    decision: Literal['approve', 'reject']
    reason: str = Field(min_length=1, max_length=500)


def install(app, store, authorize, defaults):
    service = WorkflowService(store)
    app.state.workflow_service = service

    async def principal(request: Request, c=Depends(authorize)):
        who = g.actor(await store.read(), request)
        g.require(who, 'editor', 'reviewer', 'operator')
        owner = g.owner(request)
        if not owner:
            raise HTTPException(409, '请先初始化工作空间')
        return Principal(owner, who['username'], who['role'])

    @app.get('/api/workflows/catalog')
    async def catalog(c=Depends(authorize)):
        names = ['wealth_review', *REQUIRED_PARAMS]
        return [{'id': name, 'name': '周报质检＋同业对标' if name == 'wealth_review' else WORKFLOWS[name]['name'],
                 'nodes': nodes_for(name), 'required_sources': required_sources(name),
                 'required_values': REQUIRED_PARAMS['wealth_benchmark' if name == 'wealth_review' else name],
                 'example': {'values': defaults['wealth_benchmark' if name == 'wealth_review' else name],
                             'sources': {f: tools.source(f) for f in required_sources(name)}},
                 'scope': '同一后端的确定性业务流程；不执行真实金融操作'} for name in names]

    @app.get('/api/workflow-metrics')
    async def metrics(p=Depends(principal)):
        return await service.metrics(p)

    @app.get('/api/workflows')
    async def listing(queue: bool = False, p=Depends(principal)):
        return await service.list(p, queue)

    @app.post('/api/workflows')
    async def create(d: Create, p=Depends(principal)):
        return await service.create(p, d.request_id, snapshot(d.workflow, d.values, d.sources, d.use_examples))

    @app.get('/api/workflows/{run_id}')
    async def read(run_id: str, p=Depends(principal)):
        return await service.read(run_id, p)

    @app.put('/api/workflows/{run_id}')
    async def edit(run_id: str, d: Edit, p=Depends(principal)):
        return await service.edit(run_id, p, d.revision, snapshot(d.workflow, d.values, d.sources, d.use_examples))

    @app.post('/api/workflows/{run_id}/advance')
    async def advance(run_id: str, d: Revision, p=Depends(principal)):
        return await service.advance(run_id, p, d.revision)

    @app.post('/api/workflows/{run_id}/review')
    async def review(run_id: str, d: Review, p=Depends(principal)):
        return await service.review(run_id, p, d.revision, d.decision, d.reason)

    @app.get('/api/workflows/{run_id}/export')
    async def export(run_id: str, revision: int, format: Literal['json', 'csv'] = 'json', p=Depends(principal)):
        content, kind = await service.export(run_id, p, revision, format)
        return Response(content, media_type=kind,
                        headers={'Content-Disposition': f'attachment; filename="jinshu-{run_id}-v{revision}.{format}"',
                                 'X-Jinshu-Export-Scope': 'server-held-reviewed-draft'})

    @app.delete('/api/workflows/{run_id}')
    async def delete(run_id: str, revision: int, p=Depends(principal)):
        return await service.delete(run_id, p, revision)
