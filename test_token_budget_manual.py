"""Token 预算管理测试脚本。"""

from codesage.core.token_budget import (
    calculate_budget,
    estimate_tokens,
    get_context_window,
    build_truncated_context,
)

# 测试上下文窗口获取
print("=== 上下文窗口测试 ===")
print(f"GPT-4o-mini: {get_context_window('openai', 'gpt-4o-mini')}")
print(f"Claude-3.5-Sonnet: {get_context_window('anthropic', 'claude-3-5-sonnet-latest')}")

# 测试预算计算
print("\n=== 预算计算测试 ===")
budget = calculate_budget("openai", "gpt-4o-mini")
print(f"总上下文窗口: {budget.context_window}")
print(f"最大输入: {budget.max_input_tokens}")
print(f"System Prompt: {budget.system_prompt_budget}")
print(f"PR元数据: {budget.pr_metadata_budget}")
print(f"Diff内容: {budget.diff_content_budget}")
print(f"回复: {budget.response_budget}")
print(f"安全缓冲: {budget.safety_buffer}")

# 测试 token 估算
print("\n=== Token 估算测试 ===")
text = "def hello():\n    print('hello world')\n" * 100
print(f"示例代码 tokens: {estimate_tokens(text)}")

# 测试上下文构建
print("\n=== 上下文构建测试 ===")
pr_meta = "Title: Test PR\nAuthor: test_user"
diff_content = [("test.py", "def foo():\n    pass" * 100)]
commits = "abc123: initial commit"
ctx = build_truncated_context(pr_meta, diff_content, commits, budget)
print(f"构建的上下文长度: {len(ctx)} chars, ~{estimate_tokens(ctx)} tokens")
print(f"上下文在预算内: {estimate_tokens(ctx) <= budget.max_input_tokens}")

# 测试大型 PR 场景
print("\n=== 大型 PR 场景测试 ===")
large_diffs = []
for i in range(10):
    diff = "\n".join([f"+ line {j}" for j in range(500)])
    large_diffs.append((f"file{i}.py", diff))

budget_large = calculate_budget("openai", "gpt-4o-mini")
ctx_large = build_truncated_context(pr_meta, large_diffs, commits, budget_large)
print(f"大型PR上下文: ~{estimate_tokens(ctx_large)} tokens")
print(f"是否在预算内: {estimate_tokens(ctx_large) <= budget_large.max_input_tokens}")
