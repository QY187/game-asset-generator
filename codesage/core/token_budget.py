"""Token 预算管理模块，控制 AI 上下文的 token 使用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from codesage.models.config import AI_PROVIDER_MODELS


AI_PROVIDER_CONTEXT_WINDOWS: dict[str, int] = {
    "openai": {
        "gpt-4.1": 128000,
        "gpt-4.1-mini": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
    },
    "anthropic": {
        "claude-3-5-sonnet-latest": 200000,
        "claude-3-5-haiku-latest": 200000,
        "claude-3-opus-latest": 200000,
    },
    "qwen": {
        "qwen-max": 32000,
        "qwen-plus": 131072,
        "qwen-turbo": 131072,
    },
    "hunyuan": {
        "hunyuan-t1": 128000,
        "hunyuan-pro": 128000,
        "hunyuan-lite": 128000,
    },
    "doubao": {
        "doubao-pro-32k": 32000,
        "doubao-lite-32k": 32000,
        "doubao-seed-1.6": 32000,
    },
    "deepseek": {
        "deepseek-v4-flash": 128000,
        "deepseek-v4-pro": 128000,
    },
}

TOKEN_ALLOC_RATIO = {
    "system_prompt": 0.02,
    "pr_metadata": 0.03,
    "diff_content": 0.70,
    "response": 0.20,
    "safety_buffer": 0.05,
}

CHARS_PER_TOKEN_RATIO = 4.0


@dataclass
class TokenBudget:
    """Token 预算分配结果。"""

    context_window: int
    max_input_tokens: int
    system_prompt_budget: int
    pr_metadata_budget: int
    diff_content_budget: int
    response_budget: int
    safety_buffer: int


def get_context_window(provider: str, model: str) -> int:
    """获取指定模型的上下文窗口大小。

    Args:
        provider: AI 厂商名称
        model: 模型名称

    Returns:
        上下文窗口大小（tokens）
    """
    provider_models = AI_PROVIDER_CONTEXT_WINDOWS.get(provider, {})
    if model in provider_models:
        return provider_models[model]

    provider_all_models = AI_PROVIDER_MODELS.get(provider, [])
    for m in provider_all_models:
        if m in provider_models:
            return provider_models[m]

    return 32000


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量。

    使用经验比例：约 4 个字符 = 1 个 token

    Args:
        text: 待估算的文本

    Returns:
        估算的 token 数量
    """
    if not text:
        return 0
    return int(len(text) / CHARS_PER_TOKEN_RATIO) + len(text.split())


def calculate_budget(
    provider: str,
    model: str,
    custom_max_input_tokens: Optional[int] = None,
    custom_diff_ratio: Optional[float] = None,
) -> TokenBudget:
    """计算各部分的 token 预算。

    Args:
        provider: AI 厂商名称
        model: 模型名称
        custom_max_input_tokens: 自定义最大输入 token 数（可选）
        custom_diff_ratio: 自定义 diff 内容占比（可选，0.0-1.0）

    Returns:
        TokenBudget 对象，包含各部分预算
    """
    context_window = get_context_window(provider, model)
    
    # 使用自定义预算或自动计算
    if custom_max_input_tokens and custom_max_input_tokens > 0:
        max_input_tokens = custom_max_input_tokens
        diff_ratio = custom_diff_ratio if (custom_diff_ratio and 0 < custom_diff_ratio <= 1.0) else TOKEN_ALLOC_RATIO["diff_content"]
        remaining_ratio = 1.0 - diff_ratio
        system_ratio = TOKEN_ALLOC_RATIO["system_prompt"] / (TOKEN_ALLOC_RATIO["system_prompt"] + TOKEN_ALLOC_RATIO["pr_metadata"]) * remaining_ratio
        metadata_ratio = TOKEN_ALLOC_RATIO["pr_metadata"] / (TOKEN_ALLOC_RATIO["system_prompt"] + TOKEN_ALLOC_RATIO["pr_metadata"]) * remaining_ratio
        
        system_prompt_budget = int(max_input_tokens * system_ratio)
        pr_metadata_budget = int(max_input_tokens * metadata_ratio)
        diff_content_budget = int(max_input_tokens * diff_ratio)
        response_budget = int(context_window * TOKEN_ALLOC_RATIO["response"])
        safety_buffer = int(context_window * TOKEN_ALLOC_RATIO["safety_buffer"])
    else:
        max_input_tokens = int(context_window * (1 - TOKEN_ALLOC_RATIO["response"] - TOKEN_ALLOC_RATIO["safety_buffer"]))

        system_prompt_budget = int(max_input_tokens * TOKEN_ALLOC_RATIO["system_prompt"])
        pr_metadata_budget = int(max_input_tokens * TOKEN_ALLOC_RATIO["pr_metadata"])
        diff_content_budget = int(max_input_tokens * TOKEN_ALLOC_RATIO["diff_content"])
        response_budget = int(context_window * TOKEN_ALLOC_RATIO["response"])
        safety_buffer = int(context_window * TOKEN_ALLOC_RATIO["safety_buffer"])

    return TokenBudget(
        context_window=context_window,
        max_input_tokens=max_input_tokens,
        system_prompt_budget=system_prompt_budget,
        pr_metadata_budget=pr_metadata_budget,
        diff_content_budget=diff_content_budget,
        response_budget=response_budget,
        safety_buffer=safety_buffer,
    )


def truncate_to_budget(text: str, budget: int, prefer_end: bool = False) -> str:
    """将文本截断到指定 token 预算内。

    Args:
        text: 待截断的文本
        budget: token 预算
        prefer_end: 是否保留文本末尾（用于 diff，保留最新的变更）

    Returns:
        截断后的文本
    """
    if not text:
        return text

    estimated = estimate_tokens(text)
    if estimated <= budget:
        return text

    max_chars = int(budget * CHARS_PER_TOKEN_RATIO)

    if prefer_end:
        return text[-max_chars:] if len(text) > max_chars else text
    else:
        return text[:max_chars] if len(text) > max_chars else text


def truncate_diff_smart(file_patch: str, budget: int) -> Tuple[str, int]:
    """智能截断 diff 内容，优先保留有意义的变更。

    策略：
    1. 如果 diff 较小，直接返回
    2. 否则从开头截断，保留最近的变更（通常是最重要的）
    3. 添加截断标记

    Args:
        file_patch: 文件的 diff 内容
        budget: 分配的 token 预算

    Returns:
        (截断后的 diff, 原始 diff 估计 token 数)
    """
    if not file_patch:
        return file_patch, 0

    original_tokens = estimate_tokens(file_patch)
    if original_tokens <= budget:
        return file_patch, original_tokens

    max_chars = int(budget * CHARS_PER_TOKEN_RATIO)

    if len(file_patch) <= max_chars:
        return file_patch, original_tokens

    truncated = file_patch[-max_chars:]

    truncated = "\n... (diff truncated, showing recent changes) ...\n" + truncated

    return truncated, original_tokens


def build_truncated_context(
    pr_metadata: str,
    diff_contents: List[Tuple[str, str]],
    commits_info: str,
    budget: TokenBudget,
) -> str:
    """构建截断后的完整分析上下文。

    智能分配各部分的 token 预算，确保最重要的内容（diff）获得最多空间。

    Args:
        pr_metadata: PR 元数据文本
        diff_contents: List of (filename, diff_content) tuples
        commits_info: Commit 信息文本
        budget: TokenBudget 对象

    Returns:
        构建好的上下文字符串
    """
    parts = []
    current_tokens = 0

    parts.append("## PR 信息\n" + pr_metadata)
    current_tokens += estimate_tokens(parts[-1])

    if commits_info:
        parts.append("\n## Commit 记录\n" + commits_info)
        current_tokens += estimate_tokens(parts[-1])

    parts.append("\n## 文件变更")
    parts.append(f"({len(diff_contents)} 个文件)")
    current_tokens += estimate_tokens(parts[-1])

    available_for_diff = budget.diff_content_budget - current_tokens

    if available_for_diff <= 0:
        return "\n".join(parts)

    per_file_budget = available_for_diff // max(len(diff_contents), 1)

    total_original_tokens = 0
    for filename, diff in diff_contents:
        total_original_tokens += estimate_tokens(diff)

    alloc_budget = min(per_file_budget, available_for_diff // max(len(diff_contents), 1))

    if total_original_tokens > available_for_diff:
        scale_factor = available_for_diff / total_original_tokens
        alloc_budget = int(alloc_budget * scale_factor)

    for filename, diff in diff_contents:
        file_tokens = estimate_tokens(diff)
        if file_tokens <= alloc_budget:
            parts.append(f"\n### {filename}")
            parts.append(f"\n```diff\n{diff}\n```")
        else:
            truncated_diff, _ = truncate_diff_smart(diff, alloc_budget)
            parts.append(f"\n### {filename}")
            parts.append(f"\n```diff\n{truncated_diff}\n```")

    return "\n".join(parts)
