import asyncio
import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, model_validator

from app.models import StrictModel

PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "help_url": "https://api-docs.deepseek.com/"},
    "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "help_url": "https://help.aliyun.com/zh/model-studio/get-api-key/"},
}
PROBE_TOTAL_TIMEOUT_SECONDS = 20
PROBE_MAX_RESPONSE_BYTES = 131072


class ProviderError(Exception):
    pass


class ProviderConfig(StrictModel):
    provider: Literal["deepseek", "dashscope", "custom"]
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


async def probe_provider(config: ProviderConfig, *, transport=None) -> dict:
    endpoint = config.base_url if config.base_url.endswith("/chat/completions") else config.base_url + "/chat/completions"
    payload = {"model": config.model, "messages": [{"role": "user", "content": 'Return only this JSON object: {"ok":true}'}],
               "max_tokens": 64, "stream": False}
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    try:
        async with asyncio.timeout(PROBE_TOTAL_TIMEOUT_SECONDS), httpx.AsyncClient(
            timeout=15, follow_redirects=False, transport=transport, trust_env=False,
        ) as client, client.stream(
            "POST", endpoint, headers={"Authorization": "Bearer " + config.api_key.get_secret_value()}, json=payload,
        ) as response:
            if response.status_code != 200:
                messages = {401: "Key 无效，请重新复制", 403: "账户没有调用权限，请检查服务开通状态",
                            429: "额度不足或服务限流，请在供应商控制台检查"}
                message = "服务返回重定向，已停止发送凭据" if response.is_redirect else messages.get(response.status_code, "模型调用失败，请检查模型名称或服务状态")
                raise ProviderError(message)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > PROBE_MAX_RESPONSE_BYTES:
                    raise ProviderError("模型响应过大，已停止连接测试")
                body.extend(chunk)
    except (httpx.TimeoutException, TimeoutError):
        raise ProviderError("连接超时，请检查网络或稍后重试") from None
    except httpx.HTTPError:
        raise ProviderError("无法连接模型服务，请检查地址和网络") from None
    try:
        text = json.loads(body)["choices"][0]["message"]["content"]
        if json.loads(text) != {"ok": True}:
            raise ValueError("unexpected JSON")
    except (ValueError, KeyError, TypeError, IndexError):
        raise ProviderError("模型未按要求返回 JSON；此组合尚不能用于后续结构化流程") from None
    key = config.api_key.get_secret_value()
    return {"provider": config.provider, "base_url": config.base_url, "model": config.model,
            "configured": True, "key_mask": "••••" + (key[-4:] if len(key) > 8 else ""),
            "json_probe_passed": True, "resume_generation_verified": False,
            "message": "短文本连接测试通过；尚未验证完整简历生成"}
