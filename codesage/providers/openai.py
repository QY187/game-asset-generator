"""OpenAI 兼容 API 封装，用于代码分析。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from codesage.models.analysis import AnalysisResult
from codesage.models.config import Config


_PROVIDER_ENV_PREFIX = {
    "openai": "OPENAI",
    "anthropic": "ANTHROPIC",
    "qwen": "QWEN",
    "hunyuan": "HUNYUAN",
    "doubao": "DOUBAO",
    "deepseek": "DEEPSEEK",
}


class OpenAIProvider:
    """OpenAI 兼容 API 提供者。"""

    def __init__(self, provider: str = "openai", api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = Config.normalize_provider(provider)
        prefix = _PROVIDER_ENV_PREFIX.get(self.provider, "OPENAI")
        self.api_key = api_key or os.getenv(f"{prefix}_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv(f"{prefix}_BASE_URL")
        self.client = None
        
        # 只有在有密钥时才创建客户端
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url if self.base_url else None
                )
            except ImportError:
                pass

    def chat_completion(self, messages: List[Dict[str, str]], model: str = "gpt-4o-mini",
                       temperature: float = 0.3, max_tokens: int = 4096) -> str:
        """调用 OpenAI 聊天完成接口。"""
        if not self.client:
            raise ValueError("OpenAI API key not configured")

        import openai
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content

    def chat_completion_stream(self, messages: List[Dict[str, str]], model: str = "gpt-4o-mini",
                               temperature: float = 0.3, max_tokens: int = 4096):
        """流式调用 API（DeepSeek / OpenAI 兼容）。

        逐块返回 AI 生成的文本，用于实时显示分析结果。
        """
        if not self.client:
            raise ValueError("API key not configured")

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def analyze_pr(self, pr_context: str, model: str = "gpt-4o-mini") -> AnalysisResult:
        """分析 PR 代码变更。"""
        if not self.client:
            # 如果没有配置 API，返回模拟结果
            return self._get_mock_result(pr_context, model=model)
        
        prompt = f"""你是一位资深的代码审查专家，请对以下 PR 变更进行全面分析。

PR 变更内容：
{pr_context}

请按照以下格式输出分析结果：

## 📋 变更摘要

**变更类型**：[Feature/Bugfix/Refactor/Hotfix/Documentation/Other]
**影响范围**：[简要说明影响的模块/功能]
**核心变更**：[3-5个关键点]

## 🔍 风险识别

按严重程度从高到低列出：
- [CRITICAL/MAJOR/MINOR/INFO] [风险类型]: [风险描述]
  - [代码位置]
  - [建议修复方案]

## 💡 Review建议

针对代码质量、性能、安全性等方面提供具体改进建议：
1. [建议1]
2. [建议2]
3. [建议3]

## 📝 总结

[对本次PR的总体评价和建议]
"""

        messages = [
            {"role": "system", "content": "你是一位资深的代码审查专家，擅长发现潜在问题并提供专业的改进建议。"},
            {"role": "user", "content": prompt}
        ]

        result = self.chat_completion(messages, model=model)
        return self._parse_analysis_result(result, model=model)

    def analyze_pr_stream(self, pr_context: str, model: str = "gpt-4o-mini"):
        """流式分析 PR 代码变更，逐块返回 AI 生成内容。

        与 analyze_pr 使用相同的 prompt，但通过 stream=True 实时返回结果。
        适用于 DeepSeek、OpenAI 等兼容 API。
        """
        if not self.client:
            # 未配置 API 时，逐段返回模拟结果
            mock = self._get_mock_result(pr_context, model=model)
            for line in mock.summary.split("\n"):
                yield line + "\n"
            return

        prompt = f"""你是一位资深的代码审查专家，请对以下 PR 变更进行全面分析。

PR 变更内容：
{pr_context}

请按照以下格式输出分析结果：

## 📋 变更摘要

**变更类型**：[Feature/Bugfix/Refactor/Hotfix/Documentation/Other]
**影响范围**：[简要说明影响的模块/功能]
**核心变更**：[3-5个关键点]

## 🔍 风险识别

按严重程度从高到低列出：
- [CRITICAL/MAJOR/MINOR/INFO] [风险类型]: [风险描述]
  - [代码位置]
  - [建议修复方案]

## 💡 Review建议

针对代码质量、性能、安全性等方面提供具体改进建议：
1. [建议1]
2. [建议2]
3. [建议3]

## 📝 总结

[对本次PR的总体评价和建议]
"""

        messages = [
            {"role": "system", "content": "你是一位资深的代码审查专家，擅长发现潜在问题并提供专业的改进建议。"},
            {"role": "user", "content": prompt}
        ]

        for chunk in self.chat_completion_stream(messages, model=model):
            yield chunk

    def _get_mock_result(self, pr_context: str, model: str = "gpt-4o-mini") -> AnalysisResult:
        """返回模拟分析结果（用于测试）。"""
        mock_summary = """## 📋 变更摘要

**变更类型**：Feature
**影响范围**：示例模块
**核心变更**：新增功能测试

## 🔍 风险识别

- [INFO] MAINTAINABILITY: 代码结构良好，建议添加单元测试
  - 文件: test.py
  - 建议: 为新增功能添加测试用例

## 💡 Review建议

1. 建议添加更多注释说明业务逻辑
2. 考虑添加错误处理
3. 代码风格保持一致

## 📝 总结

整体代码质量良好，建议完成测试后合并。"""

        return AnalysisResult(
            pr_url="",
            summary=mock_summary,
            risks=[],
            suggestions=["建议添加更多注释说明业务逻辑", "考虑添加错误处理", "代码风格保持一致"],
            analysis_time=0.5,
            model_used=f"mock:{self.provider}:{model}"
        )

    def _parse_analysis_result(self, response: str, model: str) -> AnalysisResult:
        """解析 AI 响应为 AnalysisResult 对象。"""
        return AnalysisResult(
            pr_url="",
            summary=response,
            risks=[],
            suggestions=[],
            analysis_time=0.0,
            model_used=f"{self.provider}:{model}"
        )
