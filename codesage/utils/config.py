"""配置管理工具。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from codesage.models.config import AI_PROVIDER_MODELS, Config

CONFIG_DIR = Path.home() / ".codesage"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config(config_path: Path | str = CONFIG_FILE) -> Config:
    """加载配置文件，并使用环境变量覆盖敏感配置。"""

    path = Path(config_path)
    data: dict = {}

    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            loaded = json.load(file)
            if isinstance(loaded, dict):
                data = loaded

    config = Config(**data)
    return _apply_environment_overrides(config)


def save_config(config: Config, config_path: Path | str = CONFIG_FILE) -> None:
    """保存配置文件。"""

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(config.model_dump(), file, ensure_ascii=False, indent=2)


def _apply_environment_overrides(config: Config) -> Config:
    """使用环境变量覆盖配置，包括各厂商独立环境变量。"""

    updates: dict = {}

    ai_provider = os.getenv("AI_PROVIDER")
    if ai_provider:
        updates["ai_provider"] = Config.normalize_provider(ai_provider)

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        updates["openai_api_key"] = openai_key

    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        updates["github_token"] = github_token

    ai_model = os.getenv("AI_MODEL")
    if ai_model:
        updates["default_model"] = ai_model

    # 各厂商独立环境变量: {PROVIDER}_API_KEY, {PROVIDER}_BASE_URL
    provider = Config.normalize_provider(ai_provider) if ai_provider else config.ai_provider
    for p in AI_PROVIDER_MODELS:
        pcfg = config.provider_configs.get(p, {})
        modified = False

        env_key = os.getenv(f"{p.upper()}_API_KEY")
        if env_key and pcfg.get("api_key") != env_key:
            pcfg = dict(pcfg)
            pcfg["api_key"] = env_key
            modified = True

        env_url = os.getenv(f"{p.upper()}_BASE_URL")
        if env_url and pcfg.get("base_url") != env_url:
            pcfg = dict(pcfg)
            pcfg["base_url"] = env_url
            modified = True

        if modified:
            if "provider_configs" not in updates:
                updates["provider_configs"] = dict(config.provider_configs)
            updates["provider_configs"][p] = pcfg

    if not updates:
        return config

    return config.model_copy(update=updates)