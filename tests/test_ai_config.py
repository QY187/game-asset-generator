"""测试 AI 配置模型，包括多厂商支持。"""
import os

from codesage.models.config import Config


def test_provider_model_sync_openai():
    cfg = Config(ai_provider="openai", default_model="claude-3-5-sonnet-latest")
    assert cfg.ai_provider == "openai"
    assert cfg.default_model == "gpt-4o-mini"
    assert cfg.model_list == ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"]


def test_provider_model_sync_anthropic():
    cfg = Config(ai_provider="anthropic", default_model="gpt-4o-mini")
    assert cfg.ai_provider == "anthropic"
    assert cfg.default_model == "claude-3-5-sonnet-latest"
    assert "claude-3-5-sonnet-latest" in cfg.model_list


def test_per_provider_config_api_key():
    """厂商独立 API Key 可正常存取。"""
    cfg = Config(ai_provider="openai")
    cfg.set_provider_config("openai", api_key="sk-openai-test")
    cfg.set_provider_config("anthropic", api_key="sk-anthropic-test")
    assert cfg.get_api_key("openai") == "sk-openai-test"
    assert cfg.get_api_key("anthropic") == "sk-anthropic-test"


def test_per_provider_config_base_url():
    """厂商独立 Base URL 可正常存取，未配置时返回默认值。"""
    cfg = Config(ai_provider="openai")
    cfg.set_provider_config("openai", base_url="https://custom.openai.com")
    assert cfg.get_base_url("openai") == "https://custom.openai.com"
    # anthropic 未配置时返回默认值（可能被环境变量覆盖）
    assert cfg.get_base_url("anthropic") != ""


def test_backward_compat_openai_api_key():
    """openai_api_key 字段对未独立配置的厂商仍然生效。"""
    cfg = Config(ai_provider="qwen", openai_api_key="sk-legacy")
    assert cfg.get_api_key("qwen") == "sk-legacy"


def test_provider_config_persistence():
    """provider_configs 能正确序列化/反序列化。"""
    cfg = Config(ai_provider="openai")
    cfg.set_provider_config("openai", api_key="sk-123", base_url="https://example.com",
                            default_model="gpt-4o")
    cfg.set_provider_config("anthropic", api_key="sk-456")
    data = cfg.model_dump()
    cfg2 = Config(**data)
    assert cfg2.get_api_key("openai") == "sk-123"
    assert cfg2.get_base_url("openai") == "https://example.com"
    assert cfg2.get_provider_config("openai").get("default_model") == "gpt-4o"
    assert cfg2.get_api_key("anthropic") == "sk-456"


def test_normalize_provider_aliases():
    """厂商别名能正确规范化。"""
    assert Config.normalize_provider("claude") == "anthropic"
    assert Config.normalize_provider("tongyi") == "qwen"
    assert Config.normalize_provider("bytedance") == "doubao"
    assert Config.normalize_provider("unknown") == "openai"


def test_default_base_urls():
    """各厂商有对应的默认 Base URL。"""
    assert Config.default_base_url_for("openai") == "https://api.openai.com/v1"
    assert Config.default_base_url_for("qwen") == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert Config.default_base_url_for("doubao") == "https://ark.cn-beijing.volces.com/api/v3"


def test_model_options_per_provider():
    """不同厂商返回不同的模型列表。"""
    assert "gpt-4o" in Config.model_options_for("openai")
    assert "claude-3-opus-latest" in Config.model_options_for("anthropic")
    assert "qwen-max" in Config.model_options_for("qwen")
    assert "hunyuan-pro" in Config.model_options_for("hunyuan")
    assert "doubao-pro-32k" in Config.model_options_for("doubao")
