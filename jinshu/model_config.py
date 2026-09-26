"""One server-side model configuration for local services and Vercel.

Never combine a DeepSeek credential with another provider's endpoint. Empty
CHAT_* variables are not overrides. This module performs no network requests.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit
import os
import re

DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"
CHAT_KEYS = ("CHAT_BASE_URL", "CHAT_API_KEY", "CHAT_MODEL")

@dataclass(frozen=True)
class ChatConfiguration:
    provider: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    missing: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()

    def public(self):
        return {"provider": self.provider, "model": self.model,
                "configured": not self.missing and not self.invalid,
                "inference_verified": False,
                "verification_scope": "configuration_only; inspect actual per-request model_calls"}

def resolve_chat(env: Mapping[str, str] | None = None, fallback=None) -> ChatConfiguration:
    env = os.environ if env is None else env
    def get(key, default=""):
        return str(env.get(key, "")).strip() or default
    selection = get("CHAT_PROVIDER", "auto").lower()
    generic_present = any(get(k) for k in CHAT_KEYS)
    deepseek_present = any(get(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"))
    invalid = []
    if selection not in {"auto", "deepseek", "openai_compatible"}:
        invalid.append("CHAT_PROVIDER")
    if selection == "deepseek" and generic_present:
        invalid.append("CHAT_PROVIDER_MIXED_CONFIGURATION")
    if selection == "openai_compatible" or (selection == "auto" and generic_present):
        base, key, model = (get(k) for k in CHAT_KEYS)
        missing = [k for k in CHAT_KEYS if not get(k)]
        provider, base_key, model_key = "openai_compatible", "CHAT_BASE_URL", "CHAT_MODEL"
    elif selection == "auto" and not deepseek_present and fallback and fallback[1]:
        base, key, model = fallback
        missing = [k for k, value in zip(CHAT_KEYS, fallback) if not value]
        provider, base_key, model_key = "openai_compatible", "CHAT_BASE_URL", "CHAT_MODEL"
    else:
        base, key, model = get("DEEPSEEK_BASE_URL", DEEPSEEK_BASE), get("DEEPSEEK_API_KEY"), get("DEEPSEEK_MODEL", DEEPSEEK_MODEL)
        missing = [] if key else ["DEEPSEEK_API_KEY"]
        provider, base_key, model_key = "deepseek", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"
    base = base.rstrip("/")
    try:
        url = urlsplit(base)
        official = (url.scheme == "https" and url.hostname == "api.deepseek.com"
                    and url.port in {None, 443} and url.path in {"", "/v1"}
                    and not any((url.username, url.password, url.query, url.fragment)))
        if base and (url.scheme not in {"http", "https"} or not url.hostname
                     or any((url.username, url.password, url.query, url.fragment))):
            invalid.append(base_key)
        if provider == "deepseek" and not official:
            invalid.append(base_key)
        if official:
            provider = "deepseek"
        if env.get("VERCEL") and base and (url.scheme != "https" or url.hostname in {"localhost", "127.0.0.1", "::1"}):
            invalid.append(base_key)
    except ValueError:
        invalid.append(base_key)
    if model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,119}", model):
        invalid.append(model_key)
        model = "invalid_model_name"
    return ChatConfiguration(provider, base, key, model, tuple(missing), tuple(sorted(set(invalid))))
