"""配置数据模型。"""

from __future__ import annotations

import os
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field, model_validator


AI_PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4o-mini",
    ],
    "anthropic": [
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
    ],
    "qwen": [
        "qwen-max",
        "qwen-plus",
        "qwen-turbo",
    ],
    "hunyuan": [
        "hunyuan-t1",
        "hunyuan-pro",
        "hunyuan-lite",
    ],
    "doubao": [
        "doubao-pro-32k",
        "doubao-lite-32k",
        "doubao-seed-1.6",
    ],
    "deepseek": [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ],
}

AI_PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "qwen": "qwen-max",
    "hunyuan": "hunyuan-pro",
    "doubao": "doubao-pro-32k",
    "deepseek": "deepseek-v4-pro",
}

AI_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "hunyuan": "https://api.hunyuan.cloud.tencent.com/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "deepseek": "https://api.deepseek.com/v1",
}

DEFAULT_AI_PROVIDER = "openai"


class Config(BaseModel):
    """应用配置，管理所有可配置项"""

    ai_provider: str = Field(description="当前使用的AI厂商", default=DEFAULT_AI_PROVIDER)
    openai_api_key: Optional[str] = Field(description="OpenAI API密钥（向后兼容）", default=None)
    github_token: Optional[str] = Field(description="GitHub访问令牌", default=None)
    default_model: str = Field(description="默认AI模型", default=AI_PROVIDER_DEFAULT_MODEL[DEFAULT_AI_PROVIDER])
    provider_configs: dict[str, dict[str, Any]] = Field(
        description="各厂商独立配置 {provider: {api_key, base_url, default_model}}",
        default_factory=dict,
    )
    confidence_threshold: str = Field(description="置信度阈值", default="medium")
    output_format: str = Field(description="输出格式", default="cli")
    auto_comment: bool = Field(description="是否自动评论", default=False)
    max_tokens: int = Field(description="最大Token数", default=8000)
    temperature: float = Field(description="温度参数", default=0.3)
    
    custom_token_budget: bool = Field(description="是否使用自定义Token预算", default=False)
    custom_max_input_tokens: int = Field(description="自定义最大输入Token数", default=0)
    custom_diff_ratio: float = Field(description="自定义Diff内容占比 (0.0-1.0)", default=0.7)

    _provider_aliases: ClassVar[dict[str, str]] = {
        "openai": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "qwen": "qwen",
        "tongyi": "qwen",
        "hunyuan": "hunyuan",
        "doubao": "doubao",
        "bytedance": "doubao",
        "deepseek": "deepseek",
        "ds": "deepseek",
    }

    @model_validator(mode="after")
    def _sync_provider_and_model(self):
        """确保厂商与模型始终匹配。"""
        provider = self.normalize_provider(self.ai_provider)
        self.ai_provider = provider

        if self.default_model not in self.model_options_for(provider):
            self.default_model = self.default_model_for(provider)

        return self

    # ── provider helper methods ────────────────────────────────────────────

    @classmethod
    def normalize_provider(cls, provider: str) -> str:
        """规范化厂商名称。"""
        return cls._provider_aliases.get((provider or "").strip().lower(), DEFAULT_AI_PROVIDER)

    @classmethod
    def model_options_for(cls, provider: str) -> list[str]:
        """返回指定厂商可用的模型列表。"""
        normalized = cls.normalize_provider(provider)
        return AI_PROVIDER_MODELS.get(normalized, AI_PROVIDER_MODELS[DEFAULT_AI_PROVIDER])

    @classmethod
    def default_model_for(cls, provider: str) -> str:
        """返回指定厂商的默认模型。"""
        normalized = cls.normalize_provider(provider)
        return AI_PROVIDER_DEFAULT_MODEL.get(normalized, AI_PROVIDER_DEFAULT_MODEL[DEFAULT_AI_PROVIDER])

    @classmethod
    def default_base_url_for(cls, provider: str) -> str:
        """返回指定厂商的默认 Base URL。"""
        normalized = cls.normalize_provider(provider)
        return AI_PROVIDER_BASE_URLS.get(normalized, "")

    def get_api_key(self, provider: str | None = None) -> Optional[str]:
        """获取指定厂商的 API Key。

        优先级：厂商独立配置 > openai_api_key 兼容字段 > 环境变量
        """
        p = self.normalize_provider(provider or self.ai_provider)

        # 1. 厂商独立配置
        pcfg = self.provider_configs.get(p, {})
        if pcfg.get("api_key"):
            return pcfg["api_key"]

        # 2. 向后兼容 openai_api_key
        if self.openai_api_key:
            return self.openai_api_key

        # 3. 环境变量
        env_key = f"{p.upper()}_API_KEY"
        if os.getenv(env_key):
            return os.getenv(env_key)

        return os.getenv("OPENAI_API_KEY")

    def get_base_url(self, provider: str | None = None) -> str:
        """获取指定厂商的 Base URL。

        优先级：厂商独立配置 > 环境变量 > 默认值
        """
        p = self.normalize_provider(provider or self.ai_provider)

        # 1. 厂商独立配置
        pcfg = self.provider_configs.get(p, {})
        if pcfg.get("base_url"):
            return pcfg["base_url"]

        # 2. 环境变量
        env_key = f"{p.upper()}_BASE_URL"
        if os.getenv(env_key):
            return os.getenv(env_key)

        # 3. 默认值
        return self.default_base_url_for(p)

    def set_provider_config(self, provider: str, api_key: str | None = None,
                            base_url: str | None = None, default_model: str | None = None):
        """保存指定厂商的配置。"""
        p = self.normalize_provider(provider)
        if p not in self.provider_configs:
            self.provider_configs[p] = {}
        if api_key is not None:
            self.provider_configs[p]["api_key"] = api_key
        if base_url is not None:
            self.provider_configs[p]["base_url"] = base_url
        if default_model is not None:
            self.provider_configs[p]["default_model"] = default_model

    def get_provider_config(self, provider: str | None = None) -> dict:
        """获取指定厂商的完整配置。"""
        p = self.normalize_provider(provider or self.ai_provider)
        return self.provider_configs.get(p, {})

    @property
    def provider_list(self) -> list[str]:
        """返回可配置的 AI 厂商列表。"""
        return list(AI_PROVIDER_MODELS.keys())

    @property
    def model_list(self) -> list:
        """返回当前厂商可用的AI模型列表。"""
        return self.model_options_for(self.ai_provider)
