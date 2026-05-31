"""AI 分析服务：核心代码审查引擎。"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from codesage.core.token_budget import (
    TokenBudget,
    build_truncated_context,
    calculate_budget,
    estimate_tokens,
)
from codesage.models.analysis import (
    AnalysisResult,
    ConfidenceLevel,
    Risk,
    RiskSeverity,
    RiskType,
)
from codesage.models.pr import PR


class AIAnalyzer:
    """AI 代码审查分析器，支持 Token 预算管理。"""

    def __init__(self, openai_provider, provider: str = "openai"):
        self.openai = openai_provider
        self.provider = provider

    def analyze_pr(
        self,
        pr: PR,
        model: str = "gpt-4o-mini",
        custom_max_input_tokens: Optional[int] = None,
        custom_diff_ratio: Optional[float] = None,
    ) -> AnalysisResult:
        """分析 PR 代码变更，使用 Token 预算管理优化上下文。

        Args:
            pr: PR 对象
            model: 使用的 AI 模型
            custom_max_input_tokens: 自定义最大输入 token 数（可选）
            custom_diff_ratio: 自定义 diff 内容占比（可选，0.0-1.0）

        Returns:
            AnalysisResult 分析结果
        """
        start_time = time.time()

        budget = calculate_budget(
            provider=self.provider,
            model=model,
            custom_max_input_tokens=custom_max_input_tokens,
            custom_diff_ratio=custom_diff_ratio,
        )

        context = self._build_context(pr, budget)

        total_input_tokens = estimate_tokens(context)

        result = self.openai.analyze_pr(context, model=model)

        analysis_time = time.time() - start_time

        parsed_result = self._parse_and_enhance(result, pr)
        parsed_result.analysis_time = analysis_time
        parsed_result.model_used = f"{self.provider}:{model}"
        parsed_result.input_tokens = total_input_tokens
        parsed_result.context_window = budget.context_window
        parsed_result.diff_budget = budget.diff_content_budget

        return parsed_result

    def analyze_pr_stream(
        self,
        pr: PR,
        model: str = "gpt-4o-mini",
        custom_max_input_tokens: Optional[int] = None,
        custom_diff_ratio: Optional[float] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> AnalysisResult:
        """流式分析 PR 代码变更，通过回调实时返回生成内容。

        Args:
            pr: PR 对象
            model: 使用的 AI 模型
            custom_max_input_tokens: 自定义最大输入 token 数
            custom_diff_ratio: 自定义 diff 内容占比
            stream_callback: 每次收到文本片段时调用

        Returns:
            AnalysisResult 分析结果
        """
        start_time = time.time()

        budget = calculate_budget(
            provider=self.provider,
            model=model,
            custom_max_input_tokens=custom_max_input_tokens,
            custom_diff_ratio=custom_diff_ratio,
        )

        context = self._build_context(pr, budget)
        total_input_tokens = estimate_tokens(context)

        full_response: list[str] = []
        for chunk in self.openai.analyze_pr_stream(context, model=model):
            full_response.append(chunk)
            if stream_callback:
                stream_callback(chunk)

        analysis_time = time.time() - start_time
        result_text = "".join(full_response)

        result = AnalysisResult(
            pr_url="",
            summary=result_text,
            risks=[],
            suggestions=[],
            analysis_time=analysis_time,
            model_used=f"{self.provider}:{model}",
        )

        parsed_result = self._parse_and_enhance(result, pr)
        parsed_result.analysis_time = analysis_time
        parsed_result.model_used = f"{self.provider}:{model}"
        parsed_result.input_tokens = total_input_tokens
        parsed_result.context_window = budget.context_window
        parsed_result.diff_budget = budget.diff_content_budget

        return parsed_result

    def _build_context(self, pr: PR, budget: TokenBudget) -> str:
        """构建 PR 分析上下文，使用 Token 预算管理。

        Args:
            pr: PR 对象
            budget: Token 预算分配

        Returns:
            构建好的上下文字符串
        """
        metadata_parts = []
        metadata_parts.append(f"- 标题: {pr.metadata.title}")
        metadata_parts.append(f"- 作者: {pr.metadata.author}")
        metadata_parts.append(f"- 状态: {pr.metadata.state}")
        metadata_parts.append(f"- 目标分支: {pr.metadata.base_ref}")
        metadata_parts.append(f"- 源分支: {pr.metadata.head_ref}")

        if pr.metadata.body:
            metadata_parts.append(f"- 描述: {pr.metadata.body[:500]}")

        pr_metadata = "\n".join(metadata_parts)

        diff_contents = []
        for file in pr.files:
            if file.patch:
                diff_info = f"- 状态: {file.status}, 新增: {file.additions} 行, 删除: {file.deletions} 行"
                diff_full = f"{diff_info}\n\n```diff\n{file.patch}\n```"
                diff_contents.append((file.filename, diff_full))

        commits_parts = []
        for commit in pr.commits:
            commits_parts.append(f"- {commit.sha[:7]}: {commit.message}")
        commits_info = "\n".join(commits_parts)

        context = build_truncated_context(
            pr_metadata=pr_metadata,
            diff_contents=diff_contents,
            commits_info=commits_info,
            budget=budget,
        )

        return context

    def _parse_and_enhance(self, result: AnalysisResult, pr: PR) -> AnalysisResult:
        """解析 AI 响应并增强结果。"""
        # 提取风险项（简化实现，后续可增强）
        risks = self._extract_risks(result.summary)
        
        # 提取建议
        suggestions = self._extract_suggestions(result.summary)
        
        return AnalysisResult(
            pr_url=pr.reference.url,
            summary=result.summary,
            risks=risks,
            suggestions=suggestions,
            analysis_time=result.analysis_time,
            model_used=result.model_used
        )

    def _extract_risks(self, content: str) -> List[Risk]:
        """从响应中提取风险项。"""
        risks = []
        
        # 简单的规则匹配提取
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if any(severity in line for severity in ["CRITICAL", "MAJOR", "MINOR", "INFO"]):
                # 解析风险行
                parts = line.split("]")
                if len(parts) >= 2:
                    severity_str = parts[0].replace("[", "").strip()
                    rest = "]".join(parts[1:]).strip()
                    
                    risk_type = "未知"
                    if "安全" in rest or "Security" in rest:
                        risk_type = "SECURITY"
                    elif "性能" in rest or "Performance" in rest:
                        risk_type = "PERFORMANCE"
                    elif "稳定" in rest or "Stability" in rest:
                        risk_type = "STABILITY"
                    elif "维护" in rest or "Maintainability" in rest:
                        risk_type = "MAINTAINABILITY"
                    
                    risks.append(Risk(
                        id=f"risk-{len(risks) + 1}",
                        file_path="",
                        line_start=0,
                        line_end=0,
                        severity=getattr(RiskSeverity, severity_str, RiskSeverity.MINOR),
                        risk_type=getattr(RiskType, risk_type, RiskType.MAINTAINABILITY),
                        title=rest[:100] if len(rest) > 100 else rest,
                        description=rest,
                        confidence=ConfidenceLevel.MEDIUM,
                        suggestion="查看详细建议"
                    ))
        
        return risks

    def _extract_suggestions(self, content: str) -> List[str]:
        """从响应中提取建议。"""
        suggestions = []
        
        lines = content.split("\n")
        in_review_section = False
        
        for line in lines:
            if "Review建议" in line:
                in_review_section = True
                continue
            
            if in_review_section and line.startswith(("1.", "2.", "3.", "4.", "5.")):
                suggestions.append(line[3:].strip())
        
        return suggestions
