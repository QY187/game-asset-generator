"""AI 分析服务：核心代码审查引擎。"""

from __future__ import annotations

import time
from typing import Callable, List, Optional, Tuple
import re

from codesage.core.confidence import ConfidenceCalculator
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
        self.confidence_calculator = ConfidenceCalculator()

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
        # 提取风险项并尝试定位到具体文件/行号
        risks = self._extract_risks(result.summary, pr)

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

    def _extract_risks(self, content: str, pr: PR) -> List[Risk]:
        """从响应中提取风险项，并计算置信度。尝试解析出文件路径与行号。"""
        risks: List[Risk] = []
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # 风险块以 '- [' 开头，例如: - [CRITICAL] TYPE: 描述
            if line.startswith("-") and ("[CRITICAL]" in line or "[MAJOR]" in line or "[MINOR]" in line or "[INFO]" in line):
                # 收集块内容
                block_lines = [line]
                j = i + 1
                while j < len(lines) and (lines[j].startswith("  -") or lines[j].startswith("    ") or lines[j].strip() == ""):
                    block_lines.append(lines[j].strip())
                    j += 1

                # 解析 severity 与主体描述
                first = block_lines[0]
                parts = first.split("]")
                severity_str = parts[0].replace("[", "").replace("-", "").strip()
                rest = "]".join(parts[1:]).strip()

                # 识别风险类型
                risk_type = "MAINTAINABILITY"
                if "安全" in rest or "Security" in rest:
                    risk_type = "SECURITY"
                elif "性能" in rest or "Performance" in rest:
                    risk_type = "PERFORMANCE"
                elif "稳定" in rest or "Stability" in rest:
                    risk_type = "STABILITY"
                elif "维护" in rest or "Maintainability" in rest:
                    risk_type = "MAINTAINABILITY"

                # 从块中找文件路径、建议、示例代码片段
                file_path = ""
                suggestion = None
                code_snippet = None
                fix_example = None

                for bl in block_lines[1:]:
                    if bl.lower().startswith("- 文件:") or bl.lower().startswith("- file:"):
                        file_path = bl.split(":", 1)[1].strip()
                    elif bl.lower().startswith("- 建议:") or bl.lower().startswith("- suggestion:"):
                        suggestion = bl.split(":", 1)[1].strip()
                    elif bl.startswith("- `") or bl.startswith("`") or "```" in bl:
                        # 简单收集可能的代码片段
                        code_snippet = bl

                # 尝试在 diff 中定位行号
                line_start, line_end = 0, 0
                if file_path:
                    # 找到对应 file change
                    matching = [f for f in pr.files if f.filename.endswith(file_path) or f.filename == file_path]
                    if matching:
                        fc = matching[0]
                        # 如果存在明确代码片段，从 patch 中定位
                        if code_snippet:
                            ls, le, snippet = self._locate_mention_in_patch(fc.patch or "", code_snippet)
                            if ls:
                                line_start, line_end = ls, le
                                code_snippet = snippet
                        # 如果没有 snippet，但可根据 additions 大致定位到开头
                        if line_start == 0 and fc.additions > 0:
                            line_start = 1
                            line_end = max(1, fc.additions)

                risk = Risk(
                    id=f"risk-{len(risks) + 1}",
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_end,
                    severity=getattr(RiskSeverity, severity_str, RiskSeverity.MINOR),
                    risk_type=getattr(RiskType, risk_type, RiskType.MAINTAINABILITY),
                    title=rest[:100] if len(rest) > 100 else rest,
                    description="\n".join(block_lines),
                    confidence=ConfidenceLevel.MEDIUM,
                    code_snippet=code_snippet,
                    suggestion=suggestion,
                    fix_example=fix_example,
                )

                risk.confidence = self.confidence_calculator.calculate_confidence(risk)
                risks.append(risk)

                i = j
                continue

            i += 1

        return risks

    def _locate_mention_in_patch(self, patch: str, mention: str) -> Tuple[int, int, Optional[str]]:
        """在 unified diff patch 中定位 mention，返回(开始行, 结束行, snippet)。

        简要实现：解析 hunk header 中的新文件行号（+start,count），并在新增/上下文行中搜索 mention。
        """
        if not patch:
            return 0, 0, None

        new_line = None
        lines = patch.split("\n")
        current_new = 0
        for idx, l in enumerate(lines):
            # 匹配 hunk header: @@ -a,b +c,d @@
            m = re.match(r"@@ .*\+(\d+)(?:,(\d+))? @@", l)
            if m:
                try:
                    start = int(m.group(1))
                except Exception:
                    start = 1
                current_new = start - 1
                continue

            if l.startswith("+"):
                current_new += 1
                content = l[1:]
                if mention.strip().strip('`') in content:
                    # 找到匹配，返回该新增行
                    snippet = content
                    return current_new, current_new, snippet
            elif l.startswith(" "):
                current_new += 1
                content = l[1:]
                if mention.strip().strip('`') in content:
                    snippet = content
                    return current_new, current_new, snippet

        return 0, 0, None

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
