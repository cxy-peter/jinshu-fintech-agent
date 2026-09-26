"""Only the outbound HTTP transport is mocked; the deployed app class/route/UI are unchanged."""
import asyncio
import json
import httpx
from core.app import create_app
async def respond(request):
    payload=json.loads(request.content)
    content=payload['messages'][-1]['content']
    if '模拟401' in content:
        return httpx.Response(401,text='never-surface-upstream-secret')
    if '慢请求' in content:
        await asyncio.sleep(1.5)
    answer='【HTTP协议模拟测试，不是真实 DeepSeek】\n先统一可比口径，再复核观察区间和数据来源。'
    if '[S1]' in content:
        answer+='本次资料要求人工复核。[S1]'
    return httpx.Response(200,json={'model':'mock-deepseek-test','choices':[{'message':{'content':answer},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':25,'completion_tokens':20,'total_tokens':45}})
app=create_app(env={'DEEPSEEK_API_KEY':'test-only-not-a-real-key'},transport=httpx.MockTransport(respond))
