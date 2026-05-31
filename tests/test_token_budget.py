"""Token 预算管理模块测试。"""

import pytest
from codesage.core.token_budget import (
    AI_PROVIDER_CONTEXT_WINDOWS,
    TokenBudget,
    build_truncated_context,
    calculate_budget,
    estimate_tokens,
    get_context_window,
    truncate_diff_smart,
    truncate_to_budget,
)


class TestEstimateTokens:
    """测试 token 估算功能。"""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_none(self):
        assert estimate_tokens(None) == 0

    def test_short_text(self):
        text = "Hello, world!"
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert tokens < len(text) * 2

    def test_long_text(self):
        text = "hello " * 1000
        tokens = estimate_tokens(text)
        assert tokens > 900
        assert tokens < 1500


class TestGetContextWindow:
    """测试上下文窗口获取。"""

    def test_gpt_4o_mini(self):
        window = get_context_window("openai", "gpt-4o-mini")
        assert window == 128000

    def test_claude_3_5_sonnet(self):
        window = get_context_window("anthropic", "claude-3-5-sonnet-latest")
        assert window == 200000

    def test_unknown_model(self):
        window = get_context_window("openai", "unknown-model")
        assert window > 0


class TestCalculateBudget:
    """测试预算计算。"""

    def test_budget_allocation(self):
        budget = calculate_budget("openai", "gpt-4o-mini")

        assert isinstance(budget, TokenBudget)
        assert budget.context_window == 128000
        assert budget.max_input_tokens < budget.context_window
        assert budget.diff_content_budget > budget.pr_metadata_budget
        assert budget.diff_content_budget > budget.system_prompt_budget
        assert budget.response_budget > 0
        assert budget.safety_buffer > 0

    def test_budget_sum(self):
        budget = calculate_budget("openai", "gpt-4o-mini")

        total = (
            budget.system_prompt_budget
            + budget.pr_metadata_budget
            + budget.diff_content_budget
            + budget.response_budget
            + budget.safety_buffer
        )
        assert total == budget.context_window


class TestTruncateToBudget:
    """测试内容截断。"""

    def test_short_text_unchanged(self):
        text = "Short text"
        budget = 100
        result = truncate_to_budget(text, budget)
        assert result == text

    def test_long_text_truncated(self):
        text = "hello " * 1000
        budget = 100
        result = truncate_to_budget(text, budget)
        assert estimate_tokens(result) <= budget * 2

    def test_prefer_end(self):
        text = "Hello World"
        budget = 5
        result = truncate_to_budget(text, budget, prefer_end=True)
        assert result == " World"


class TestTruncateDiffSmart:
    """测试智能 diff 截断。"""

    def test_small_diff_unchanged(self):
        diff = "line1\nline2\nline3"
        budget = 100
        result, original = truncate_diff_smart(diff, budget)
        assert result == diff

    def test_large_diff_truncated(self):
        diff = "\n".join([f"line {i}" for i in range(1000)])
        budget = 50
        result, original = truncate_diff_smart(diff, budget)
        assert "..." in result or len(result) < len(diff)


class TestBuildTruncatedContext:
    """测试构建截断后的上下文。"""

    def test_empty_diff_list(self):
        budget = calculate_budget("openai", "gpt-4o-mini")
        result = build_truncated_context(
            pr_metadata="Title: Test PR",
            diff_contents=[],
            commits_info="commit1",
            budget=budget,
        )
        assert "Title: Test PR" in result
        assert "commit1" in result

    def test_single_file(self):
        budget = calculate_budget("openai", "gpt-4o-mini")
        result = build_truncated_context(
            pr_metadata="Title: Test",
            diff_contents=[("test.py", "def hello():\n    pass")],
            commits_info="",
            budget=budget,
        )
        assert "test.py" in result

    def test_multiple_files_budget_distribution(self):
        budget = calculate_budget("openai", "gpt-4o-mini")

        large_diff = "\n".join([f"line {i}" for i in range(1000)])
        diff_contents = [
            ("file1.py", large_diff),
            ("file2.py", large_diff),
            ("file3.py", large_diff),
        ]

        result = build_truncated_context(
            pr_metadata="Title: Large PR",
            diff_contents=diff_contents,
            commits_info="",
            budget=budget,
        )

        total_tokens = estimate_tokens(result)
        assert total_tokens < budget.context_window


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
