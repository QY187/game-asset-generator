# CodeSage - AI驱动的代码审查工具

<div align="center">

**智能代码评审助手 - 通过AI自动化分析提升代码评审效率与质量**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Development Status](https://img.shields.io/badge/status-Alpha-orange)](https://pypi.org/)

</div>

---

## 📖 项目简介

CodeSage 是一款以 AI 为核心驱动力的 Pull Request 评审工具，通过自动化分析帮助开发团队提升代码评审效率与质量，减少人工评审负担，同时保持评审深度与一致性。

### 核心价值

- ⚡ **效率提升**：自动化处理 PR 变更分析，将人工评审时间缩短 60% 以上
- 🛡️ **质量保障**：通过 AI 模型的专业知识库，识别潜在风险与改进点
- 📏 **一致性**：确保每次评审遵循相同的标准与深度
- 🎯 **上下文理解**：深入理解代码变更的业务上下文，提供有意义的建议

---

## ✨ 功能特性

### 核心功能

| 功能模块 | 描述 |
|---------|------|
| **PR变更总结** | 自动生成 PR 变更摘要，包括文件数量、代码行数变更、涉及模块 |
| **业务意图解读** | AI 推断开发者意图，生成简洁的变更说明 |
| **风险识别** | 识别安全漏洞、性能问题、稳定性风险等 |
| **Review建议** | 针对风险点提供具体的修复建议和代码示例 |
| **多平台支持** | 支持 GitHub、Gitee 等主流代码托管平台 |
| **多AI厂商** | 支持 OpenAI、Claude 等多种 AI 模型 |

### 风险检测能力

| 风险类别 | 检测内容 | 严重程度 |
|---------|---------|---------|
| 🔴 安全问题 | SQL注入、XSS、敏感信息泄露等 | Critical/Major |
| 🟠 性能问题 | N+1查询、大循环内数据库操作等 | Major/Minor |
| 🟡 稳定性问题 | 空指针风险、缺少异常处理等 | Major/Minor |
| 🔵 可维护性 | 过长函数、重复代码、过深嵌套等 | Minor |

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/codesage.git
cd codesage

# 安装依赖
pip install -e .
```

### 配置

创建 `.env` 文件或设置环境变量：

```bash
# GitHub Token（用于访问 GitHub API）
GITHUB_TOKEN=your_github_token

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key

# 可选：OpenAI API Base URL（用于自定义端点）
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 基本使用

#### CLI 命令行工具

```bash
# 分析 GitHub PR
codesage analyze https://github.com/owner/repo/pull/123

# 分析 Gitee PR
codesage analyze https://gitee.com/owner/repo/pull/456

# 指定 AI 模型
codesage analyze https://github.com/owner/repo/pull/123 --model gpt-4

# 将分析结果发布到 PR 评论
codesage analyze https://github.com/owner/repo/pull/123 --comment

# 输出分析结果到文件
codesage analyze https://github.com/owner/repo/pull/123 --output result.md
```

#### GUI 图形界面

```bash
# 启动图形界面
codesage-gui
```

---

## 📋 使用示例

### 示例输出

```markdown
📋 **PR变更摘要**

**基本信息**
- PR: #1234 - 用户登录功能重构
- 作者: @developer  
- 变更范围: 8个文件，+486行，-312行
- 变更类型: 功能重构 + 性能优化

**核心变更**
1. 重构了 `UserService` 的认证流程，支持多因素认证
2. 引入Redis缓存层，优化登录验证性能（预计提升40%）
3. 新增 `LoginHistory` 模块用于安全审计

**影响评估**
- 涉及认证模块，建议重点关注安全相关变更
- 依赖 `common-utils` 的版本已更新

🚨 **风险代码标识** (发现 2 个问题)

| 严重程度 | 问题类型 | 文件位置 | 描述 |
|----------|----------|----------|------|
| 🔴 Critical | 安全风险 | `auth/login.py:45` | 检测到SQL拼接，可能导致SQL注入 |
| 🟠 Major | 性能风险 | `db/query.py:78` | 发现N+1查询问题，循环内执行数据库操作 |

💡 **Review建议**

### 🔴 Must Fix - 必须修复

**1. SQL注入风险** (`auth/login.py:45`)
```python
# 问题：直接拼接用户输入到SQL查询
user_input = request.GET['username']
query = f"SELECT * FROM users WHERE name = '{user_input}'"  # ❌ 危险

# 建议：使用参数化查询
query = "SELECT * FROM users WHERE name = %s"  # ✅ 安全
cursor.execute(query, (user_input,))
```

**影响范围：** 攻击者可通过构造特殊用户名执行任意SQL命令
```

---

## ⚙️ 配置说明

### 支持的 AI 厂商

| 厂商 | Provider | 默认模型 | 支持的模型 |
|-----|----------|---------|-----------|
| OpenAI | `openai` | `gpt-4o` | `gpt-4`, `gpt-4o`, `gpt-4o-mini` |

### 环境变量

| 变量名 | 描述 | 必需 |
|--------|------|------|
| `GITHUB_TOKEN` | GitHub 个人访问令牌 | 是（用于 GitHub PR） |
| `OPENAI_API_KEY` | OpenAI API 密钥 | 是 |
| `OPENAI_BASE_URL` | OpenAI API 基础 URL | 否 |

---

## 🛠️ 开发指南

### 项目结构

```
codesage/
├── cli/              # 命令行接口
│   └── main.py       # CLI 入口
├── core/             # 核心业务逻辑
│   ├── ai_analyzer.py    # AI 分析器
│   ├── pr_parser.py      # PR URL 解析
│   ├── pr_service.py     # PR 服务
│   └── token_budget.py   # Token 预算管理
├── gui/              # 图形界面
│   └── main.py       # GUI 入口
├── models/           # 数据模型
│   ├── analysis.py   # 分析结果模型
│   ├── config.py     # 配置模型
│   └── pr.py         # PR 数据模型
├── providers/        # 平台适配器
│   ├── ai_provider.py    # AI 提供者接口
│   ├── gitee.py          # Gitee 平台适配
│   ├── github.py         # GitHub 平台适配
│   └── openai.py         # OpenAI 适配
└── utils/            # 工具函数
    └── config.py     # 配置加载
```

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_pr_parser.py -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=codesage --cov-report=html
```

### 代码风格

项目遵循 PEP 8 代码规范，使用以下工具进行代码质量检查：

```bash
# 代码格式化
black codesage/

# 代码检查
ruff check codesage/

# 类型检查
mypy codesage/
```

---

## 📚 技术架构

### 系统架构

```
┌─────────────────┐
│  Web UI / CLI  │  用户入口
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PR解析服务     │  解析 PR URL、获取变更
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI分析服务     │  变更摘要、风险识别、建议生成
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  通知服务       │  GitHub 评论、Webhook 推送
└─────────────────┘
```

### 核心模块

- **PR解析服务**：统一处理不同代码托管平台的 PR 获取
- **AI分析服务**：调用 AI 模型进行代码分析
- **上下文管理**：为 AI 分析提供丰富的上下文信息
- **模型路由**：根据任务复杂度智能选择合适的 AI 模型

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- 感谢 OpenAI 提供强大的 AI 能力
- 感谢所有贡献者的支持

---

## 📞 联系方式

- 项目主页：https://github.com/your-username/codesage
- 问题反馈：https://github.com/your-username/codesage/issues
- 邮箱：team@codesage.ai

---

<div align="center">

**Made with ❤️ by CodeSage Team**

</div>