"""AI 提供者工厂。"""

from __future__ import annotations

from typing import Optional

from codesage.models.config import Config
from codesage.providers.openai import OpenAIProvider


class AIProviderFactory:
    """按厂商创建 AI 提供者。"""

    @staticmethod
    def create(provider: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        normalized = Config.normalize_provider(provider)
        return OpenAIProvider(provider=normalized, api_key=api_key, base_url=base_url)
