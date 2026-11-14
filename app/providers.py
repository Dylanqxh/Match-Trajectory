import asyncio
import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, model_validator

from app.models import StrictModel
from app.provider_protocols import (
    adapt_request,
    decode_response,
    request_endpoint,
    request_headers,
)

PRESETS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-6.1-sol", "help_url": "https://platform.openai.com/api-keys"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-5", "help_url": "https://console.anthropic.com/settings/keys"},
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "help_url": "https://api-docs.deepseek.com/"},
    "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "help_url": "https://help.aliyun.com/zh/model-studio/get-api-key/"},
}
PROBE_TOTAL_TIMEOUT_SECONDS = 20
PROBE_MAX_RESPONSE_BYTES = 131072


class ProviderError(Exception):
    def __init__(self, message: str = "", category: str = "model_unavailable"):
        super().__init__(message)
        self.category = category


_BALANCE_HINTS = ("insufficient_quota", "insufficient quota", "insufficient_balance", "insufficient balance",
                  "exceeded your current quota", "quota", "balance", "payment required", "余额", "欠费", "额度不足")
_RATE_HINTS = ("rate limit", "rate_limit", "too many", "throttl")
_PROBE_MESSAGES = {
    "invalid_key": "Key 无效或账户没有调用权限。请到供应商控制台重新复制 Key，并确认已经开通该模型。",
    "insufficient_balance": "账户余额或额度不足。请到供应商控制台充值或查看套餐，然后再测试连接。",
    "rate_limited": "请求过于频繁，服务暂时限流。请稍等一两分钟再试，不必更换 Key。",
    "network": "连不上模型服务。请检查网络、代理和接口地址。",
    "timeout": "连接超时，请检查网络或稍后重试。",
    "model_unavailable": "模型不可用或名称不正确。请核对预设模型，或在高级选项里修改模型 ID。",
}
_GENERATION_MESSAGES = {
    "invalid_key": "Key 无效，请重新连接模型。",
    "insufficient_balance": "模型额度不足，请到供应商控制台检查后再继续。",
    "rate_limited": "模型服务限流，请稍后继续。",
    "network": "模型网络连接失败，任务已保留。",
    "timeout": "模型调用超时；本次可能已经计费，可稍后明确继续。",
    "model_unavailable": "模型服务调用失败，任务已保留，请检查地址或稍后继续。",
}


def classify_provider_failure(status: int, snippet: str = "", *, redirect: bool = False, during: str = "probe") -> tuple[str, str]:
    """Map a provider HTTP failure to a fixed category. The snippet is never copied into the message."""
    blob = (snippet or "").lower()
    messages = _GENERATION_MESSAGES if during == "generation" else _PROBE_MESSAGES
    balance = any(token in blob for token in _BALANCE_HINTS)
    rate = any(token in blob for token in _RATE_HINTS)
    if redirect:
        return "network", "服务返回重定向，已停止发送凭据。请检查接口地址是否正确。"
    if status in (401, 403):
        category = "invalid_key"
    elif status == 402 or (status == 429 and balance) or (balance and not rate):
        category = "insufficient_balance"
    elif status == 429 or rate:
        category = "rate_limited"
    elif status in (404, 408, 503) or "model_not_found" in blob or "model not found" in blob:
        category = "model_unavailable"
    else:
        category = "model_unavailable" if status >= 500 or status == 400 else "network" if status == 0 else "model_unavailable"
    return category, messages[category]


class ProviderConfig(StrictModel):
    provider: Literal["openai", "anthropic", "deepseek", "dashscope", "custom"]
    base_url: str = Field(default="", max_length=1000)
    model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_address(self):
        if self.provider in PRESETS:
            preset = PRESETS[self.provider]["base_url"]
            if self.base_url and self.base_url.rstrip("/") != preset:
                raise ValueError("预设地址不能覆盖，请选择自定义接口")
            self.base_url = preset
        self.base_url = self.base_url.rstrip("/")
        parts = urlsplit(self.base_url)
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("模型地址不能包含账户、查询参数或片段")
        try:
            local = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            local = parts.hostname == "localhost"
        if parts.scheme != "https" and not (parts.scheme == "http" and local):
            raise ValueError("远程模型必须使用 HTTPS；HTTP 仅用于本机接口")
        return self


def _without_secret(message: str, config: ProviderConfig) -> str:
    secret = config.api_key.get_secret_value()
    if secret and secret in message:
        return message.replace(secret, "••••")
    return message


async def _read_error_snippet(response) -> str:
    raw = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            if len(raw) >= 800:
                break
            raw.extend(chunk[:800 - len(raw)])
    except (httpx.HTTPError, TimeoutError):
        return ""
    return bytes(raw).decode("utf-8", "ignore")


async def probe_provider(config: ProviderConfig, *, transport=None) -> dict:
    payload = {"model": config.model, "messages": [{"role": "user", "content": 'Return only this JSON object: {"ok":true}'}],
               "max_tokens": 64, "stream": False}
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    try:
        async with asyncio.timeout(PROBE_TOTAL_TIMEOUT_SECONDS), httpx.AsyncClient(
            timeout=15, follow_redirects=False, transport=transport, trust_env=False,
        ) as client, client.stream(
            "POST", request_endpoint(config), headers=request_headers(config), json=adapt_request(config, payload),
        ) as response:
            if response.status_code != 200:
                snippet = await _read_error_snippet(response)
                category, message = classify_provider_failure(
                    response.status_code, snippet, redirect=bool(response.is_redirect), during="probe")
                raise ProviderError(_without_secret(message, config), category)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > PROBE_MAX_RESPONSE_BYTES:
                    raise ProviderError("模型响应过大，已停止连接测试", "model_unavailable")
                body.extend(chunk)
    except (httpx.TimeoutException, TimeoutError):
        raise ProviderError(_PROBE_MESSAGES["timeout"], "timeout") from None
    except httpx.HTTPError:
        raise ProviderError(_PROBE_MESSAGES["network"], "network") from None
    try:
        text = decode_response(config, body)["choices"][0]["message"]["content"]
        if json.loads(text) != {"ok": True}:
            raise ValueError("unexpected JSON")
    except (ValueError, KeyError, TypeError, IndexError):
        raise ProviderError("模型未按要求返回 JSON；此组合尚不能用于后续结构化流程", "model_unavailable") from None
    key = config.api_key.get_secret_value()
    return {"provider": config.provider, "base_url": config.base_url, "model": config.model,
            "configured": True, "key_mask": "••••" + (key[-4:] if len(key) > 8 else ""),
            "json_probe_passed": True, "resume_generation_verified": False,
            "message": "短文本连接测试通过；尚未验证完整简历生成"}
