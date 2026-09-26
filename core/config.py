"""No database settings are prerequisites for the default web application."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping
import os
from jinshu.model_config import resolve_chat, ChatConfiguration, CHAT_KEYS

@dataclass(frozen=True)
class Configuration:
    chat: ChatConfiguration
    access_code: str = field(repr=False)
    timeout: int = 55
    max_tokens: int = 1600
    hourly_limit: int = 30
    configuration_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def public(self):
        problems = list(self.chat.invalid) + list(self.configuration_errors)
        return {
            **self.chat.public(),
            'configured': not self.chat.missing and not problems,
            'missing': list(self.chat.missing), 'invalid': problems,
            'access_required': bool(self.access_code), 'warnings': list(self.warnings),
            'max_tokens': self.max_tokens, 'timeout_seconds': self.timeout,
            'hourly_limit_per_instance': self.hourly_limit,
        }

def load(env: Mapping[str, str] | None = None) -> Configuration:
    e = dict(os.environ if env is None else env)
    warnings, errors = [], []
    provider = (e.get('CHAT_PROVIDER') or 'auto').strip().lower()
    # Existing Vercel projects can contain stale CHAT_* values from V7/V8.
    # A deliberately supplied DeepSeek key wins in auto mode; never borrow it
    # for a third-party endpoint. Explicit generic selection is still respected.
    if provider in {'auto', 'deepseek'} and (e.get('DEEPSEEK_API_KEY') or '').strip():
        if any((e.get(k) or '').strip() for k in CHAT_KEYS):
            warnings.append('已选择 DEEPSEEK_API_KEY；未使用旧 CHAT_* 配置。')
        for k in CHAT_KEYS:
            e.pop(k, None)
        e['CHAT_PROVIDER'] = 'deepseek'
    chat = resolve_chat(e)
    def integer(key, default, low, high):
        raw = e.get(key, '').strip()
        if not raw:
            return default
        try:
            result = int(raw)
            if not low <= result <= high:
                raise ValueError
            return result
        except ValueError:
            errors.append(key)
            return default
    timeout = integer('MODEL_TIMEOUT', 55, 5, 90)
    tokens = integer('CHAT_MAX_TOKENS', 1600, 64, 4096)
    hourly = integer('MAX_MODEL_CALLS_PER_HOUR', 30, 1, 120)
    code = (e.get('JINSHU_ACCESS_CODE') or '').strip()
    if code and not 12 <= len(code) <= 200:
        errors.append('JINSHU_ACCESS_CODE')
    return Configuration(chat, code, timeout, tokens, hourly, tuple(errors), tuple(warnings))
