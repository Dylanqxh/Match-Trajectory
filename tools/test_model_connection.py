"""Safely test an OpenAI-compatible model endpoint without saving its key."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.provider_protocols import normalize_endpoint
from app.providers import ProviderConfig, ProviderError, probe_provider


class DiagnosticError(RuntimeError):
    def __init__(self, message: str, category: str):
        super().__init__(message)
        self.category = category


def run_probe(base_url: str, model: str, api_key: str, *, transport=None) -> dict:
    config = ProviderConfig(provider="custom", base_url=base_url, model=model, api_key=api_key)
    try:
        result = asyncio.run(probe_provider(config, transport=transport))
    except ProviderError as error:
        raise DiagnosticError(str(error), error.category) from None
    return {
        "ok": True,
        "endpoint": normalize_endpoint(config.base_url),
        "model": config.model,
        "message": result["message"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="测试 OpenAI 兼容的 Chat Completions 模型连接")
    parser.add_argument("--base-url", help="中转站 Base URL，例如 https://relay.example.com/v1")
    parser.add_argument("--model", help="中转站提供的模型 ID")
    args = parser.parse_args(argv)
    base_url = (args.base_url or input("Base URL: ")).strip()
    model = (args.model or input("模型 ID: ")).strip()
    api_key = getpass.getpass("API Key（输入不会显示，也不会保存）: ")
    try:
        result = run_probe(base_url, model, api_key)
    except (DiagnosticError, ValueError) as error:
        category = getattr(error, "category", "invalid_configuration")
        print(f"测试失败 [{category}]：{error}")
        return 2
    print(f"测试通过\n请求地址：{result['endpoint']}\n模型：{result['model']}\n{result['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
