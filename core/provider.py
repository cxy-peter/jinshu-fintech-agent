"""One bounded real HTTP call. Provider failures never become canned success."""
from __future__ import annotations
import asyncio
import json
import time
import httpx
from .config import Configuration

class ModelFailure(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

async def complete(config: Configuration, messages: list[dict], *, transport=None, max_tokens=None):
    state = config.public()
    if not state['configured']:
        raise ModelFailure('MODEL_CONFIGURATION_REQUIRED',
            '请在服务端配置有效的 DEEPSEEK_API_KEY。配置错误名称见“服务状态”；不需要 MongoDB 或 Milvus。', 503)
    chat = config.chat
    payload = {'model': chat.model, 'messages': messages,
               'max_tokens': min(max_tokens or config.max_tokens, config.max_tokens),
               'temperature': 0.2, 'stream': False}
    if chat.provider == 'deepseek':
        payload['thinking'] = {'type': 'disabled'}
    start = time.monotonic()
    async def call():
        async with httpx.AsyncClient(transport=transport, follow_redirects=False,
                timeout=httpx.Timeout(config.timeout, connect=min(10, config.timeout)),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=0)) as client:
            async with client.stream('POST', chat.base_url + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + chat.api_key,
                             'Content-Type': 'application/json'}, json=payload) as res:
                failures = {
                    401: ('MODEL_AUTH_FAILED', 'DeepSeek 密钥无效或未获授权；请在 Vercel 服务端检查密钥。'),
                    402: ('MODEL_BALANCE_REQUIRED', '模型账户余额不足，请检查 DeepSeek 账户。'),
                    403: ('MODEL_ACCESS_DENIED', '模型服务拒绝访问；请核对账户及模型权限。'),
                    404: ('MODEL_NOT_FOUND', '模型或接口不存在；请检查 DEEPSEEK_MODEL（默认 deepseek-flash）。'),
                    422: ('MODEL_REQUEST_REJECTED', '模型服务不接受当前请求参数。'),
                    429: ('MODEL_RATE_LIMITED', '模型服务正在限流，请稍后重试。'),
                }
                if res.status_code != 200:
                    code, message = failures.get(res.status_code, ('MODEL_UPSTREAM_ERROR', '模型服务暂时不可用，请稍后重试。'))
                    # Never expose upstream response bodies or request headers.
                    raise ModelFailure(code, message, 429 if res.status_code == 429 else 502)
                parts, size = [], 0
                async for part in res.aiter_bytes():
                    size += len(part)
                    if size > 262144:
                        raise ModelFailure('MODEL_RESPONSE_TOO_LARGE', '模型返回内容超出安全大小限制。')
                    parts.append(part)
                return json.loads(b''.join(parts))
    try:
        data = await asyncio.wait_for(call(), timeout=config.timeout)
        choice = data['choices'][0]
        answer = choice['message'].get('content')
        if choice.get('finish_reason') == 'length':
            raise ModelFailure('MODEL_TRUNCATED', '模型回答达到长度上限，未当作完整答案展示。请缩短问题后重试。')
        if choice.get('finish_reason') not in (None, 'stop'):
            raise ModelFailure('MODEL_INCOMPLETE', '模型未完成正常文本回答，请调整问题后重试。')
        if not isinstance(answer, str) or not answer.strip():
            raise ModelFailure('MODEL_EMPTY_RESPONSE', '模型没有返回可显示的文本，请重试。')
        usage = {k: v for k, v in (data.get('usage') or {}).items()
                 if k in {'prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'}
                 and type(v) is int and v >= 0}
        returned_model = data.get('model')
        if not isinstance(returned_model, str) or len(returned_model) > 160:
            returned_model = chat.model
        return answer.strip(), {
            'provider': chat.provider, 'requested_model': chat.model, 'model': returned_model,
            'usage': usage, 'latency_ms': round((time.monotonic() - start) * 1000),
            'status': 'ok', 'inference_verified': transport is None,
            'verification_scope': 'real_provider_response' if transport is None else 'mock_http_test_only',
        }
    except ModelFailure:
        raise
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise ModelFailure('MODEL_TIMEOUT', '模型响应超时，未生成替代答案；请稍后重试或缩短问题。', 504) from None
    except httpx.RequestError:
        raise ModelFailure('MODEL_NETWORK_ERROR', '暂时无法连接模型服务，请检查服务端网络。') from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ModelFailure('MODEL_INVALID_RESPONSE', '模型返回格式异常，未生成替代答案。') from None
