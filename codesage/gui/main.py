"""CodeSage GUI — AI驱动的PR代码审查工具。"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

import flet as ft

from codesage.core.ai_analyzer import AIAnalyzer
from codesage.core.pr_parser import parse_pr_url
from codesage.core.pr_service import PRService
from codesage.models.analysis import AnalysisResult, RiskSeverity
from codesage.models.config import AI_PROVIDER_BASE_URLS, AI_PROVIDER_MODELS, Config
from codesage.providers.ai_provider import AIProviderFactory
from codesage.utils.config import load_config, save_config

PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI (GPT系列)",
    "anthropic": "Anthropic (Claude系列)",
    "qwen": "阿里云 (通义千问)",
    "hunyuan": "腾讯云 (混元)",
    "doubao": "字节跳动 (豆包)",
}

PROVIDER_ENV_PREFIX = {
    "openai": "OPENAI",
    "anthropic": "ANTHROPIC",
    "qwen": "QWEN",
    "hunyuan": "HUNYUAN",
    "doubao": "DOUBAO",
}

# ── colour palette ──────────────────────────────────────────────────────────

SEVERITY_COLORS = {
    "critical": ft.Colors.RED_600,
    "major": ft.Colors.ORANGE_600,
    "minor": ft.Colors.YELLOW_700,
    "info": ft.Colors.BLUE_400,
}
SEVERITY_BG = {
    "critical": ft.Colors.RED_900,
    "major": ft.Colors.ORANGE_900,
    "minor": ft.Colors.YELLOW_900,
    "info": ft.Colors.BLUE_900,
}
RISK_TYPE_ICONS = {
    "security": "🔒",
    "performance": "⚡",
    "stability": "⚠️",
    "maintainability": "🔧",
    "test_coverage": "🧪",
    "best_practice": "📋",
}


# ── helpers ─────────────────────────────────────────────────────────────────


def _parse_risk_section(summary_text: str) -> list[dict]:
    """从AI分析文本中解析风险项，返回结构化列表。"""
    risks = []
    lines = summary_text.split("\n")
    current_risk = None

    severity_line_pattern = re.compile(
        r"^(?:[•\-*]\s*)?(?:\*\*)?[\[【](CRITICAL|MAJOR|MINOR|INFO)[\]】](?:\*\*)?\s*(.*)$",
        re.IGNORECASE,
    )

    def normalize_risk_type(risk_type: str, title: str) -> str:
        normalized = (risk_type or "").strip().replace("**", "")
        normalized = normalized.replace(" ", "_").replace("-", "_").upper()
        if normalized in {"SECURITY", "PERFORMANCE", "STABILITY", "MAINTAINABILITY", "TEST_COVERAGE", "BEST_PRACTICE"}:
            return normalized
        if any(key in normalized for key in ("安全", "SECURITY")):
            return "SECURITY"
        if any(key in normalized for key in ("性能", "PERFORMANCE")):
            return "PERFORMANCE"
        if any(key in normalized for key in ("稳定", "STABILITY")):
            return "STABILITY"
        if any(key in normalized for key in ("测试", "COVERAGE")):
            return "TEST_COVERAGE"
        if any(key in normalized for key in ("实践", "BEST")):
            return "BEST_PRACTICE"
        if any(key in normalized for key in ("维护", "MAINTAIN")):
            return "MAINTAINABILITY"

        title_text = title.upper()
        if "安全" in title_text or "SECURITY" in title_text:
            return "SECURITY"
        if "性能" in title_text or "PERFORMANCE" in title_text:
            return "PERFORMANCE"
        if "稳定" in title_text or "STABILITY" in title_text:
            return "STABILITY"
        if "测试" in title_text or "COVERAGE" in title_text:
            return "TEST_COVERAGE"
        if "实践" in title_text or "BEST" in title_text:
            return "BEST_PRACTICE"
        return "MAINTAINABILITY"

    def extract_value(text: str) -> str:
        cleaned = text.replace("**", "").strip()
        cleaned = re.sub(r"^[•\-*]\s*", "", cleaned)
        return cleaned.strip()

    for line in lines:
        stripped = extract_value(line)
        if not stripped:
            continue

        m = severity_line_pattern.match(stripped)
        if m:
            if current_risk:
                risks.append(current_risk)
            sev = m.group(1).lower()
            remainder = m.group(2).strip()
            if "：" in remainder:
                rtype_text, title_text = remainder.split("：", 1)
            elif ":" in remainder:
                rtype_text, title_text = remainder.split(":", 1)
            else:
                rtype_text, title_text = "MAINTAINABILITY", remainder

            current_risk = {
                "severity": sev,
                "risk_type": normalize_risk_type(rtype_text, title_text),
                "title": title_text.strip()[:120],
                "description": title_text.strip(),
                "file_path": "",
                "suggestion": "",
            }
            continue

        if current_risk:
            if stripped.startswith(("文件:", "文件：", "代码位置:", "代码位置：", "File:", "File：")):
                current_risk["file_path"] = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped.split("：", 1)[1].strip()
            elif stripped.startswith(("建议:", "建议：", "修复方案:", "修复方案：", "Suggestion:", "Suggestion：")):
                current_risk["suggestion"] = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped.split("：", 1)[1].strip()
            elif stripped.startswith(("- 文件", "• 文件", "- 代码位置", "• 代码位置", "- File", "• File")):
                current_risk["file_path"] = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped.split("：", 1)[1].strip()

    if current_risk:
        risks.append(current_risk)

    return risks


def _parse_suggestions(summary_text: str) -> list[str]:
    """从AI分析文本中解析建议列表。"""
    suggestions = []
    lines = summary_text.split("\n")
    in_section = False

    for line in lines:
        stripped = line.strip()
        if "Review建议" in stripped or "💡" in stripped:
            in_section = True
            continue
        if in_section and re.match(r"^\d+[\.\)、]\s*", stripped):
            suggestion = re.sub(r"^\d+[\.\)、]\s*", "", stripped).strip()
            if suggestion:
                suggestions.append(suggestion)
        elif in_section and stripped.startswith("- "):
            suggestion = stripped[2:].strip()
            if suggestion:
                suggestions.append(suggestion)

    return suggestions


# ── widgets ─────────────────────────────────────────────────────────────────


class StatsCard(ft.Container):
    """统计卡片组件。"""

    def __init__(self, label: str, value: str, color: str, icon: str = ""):
        super().__init__(
            content=ft.Column(
                [
                    ft.Text(
                        f"{icon} {label}" if icon else label,
                        size=12,
                        color=ft.Colors.GREY_400,
                    ),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=color),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
            padding=16,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )


class RiskCard(ft.Container):
    """风险卡片组件。"""

    def __init__(self, risk: dict, index: int):
        sev = risk.get("severity", "info")
        color = SEVERITY_COLORS.get(sev, ft.Colors.GREY_400)
        bg = SEVERITY_BG.get(sev, ft.Colors.GREY_800)
        rtype = risk.get("risk_type", "UNKNOWN")
        icon = RISK_TYPE_ICONS.get(rtype.lower(), "📌")

        header = ft.Row(
            [
                ft.Container(
                    ft.Text(
                        risk.get("severity", "INFO").upper(),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    bgcolor=color,
                    border_radius=6,
                    padding=ft.Padding(8, 2, 8, 2),
                ),
                ft.Container(
                    ft.Text(f"{icon} {rtype}", size=11, color=ft.Colors.GREY_300),
                    bgcolor=ft.Colors.GREY_800,
                    border_radius=6,
                    padding=ft.Padding(8, 2, 8, 2),
                ),
            ],
            spacing=8,
        )

        body = ft.Column(
            [
                ft.Text(
                    risk.get("title", ""),
                    size=14,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.WHITE,
                ),
            ]
            + (
                [
                    ft.Text(
                        risk["file_path"],
                        size=12,
                        color=ft.Colors.BLUE_300,
                        font_family="monospace",
                    )
                ]
                if risk.get("file_path")
                else []
            )
            + (
                [
                    ft.Container(
                        ft.Text(
                            f"💡 {risk['suggestion']}",
                            size=12,
                            color=ft.Colors.GREEN_300,
                        ),
                        bgcolor=ft.Colors.GREEN_900,
                        border_radius=8,
                        padding=10,
                        margin=ft.Margin(top=4),
                    )
                ]
                if risk.get("suggestion")
                else []
            ),
            spacing=4,
        )

        super().__init__(
            content=ft.Column([header, body], spacing=8),
            bgcolor=bg,
            border_radius=12,
            padding=16,
            border=ft.border.Border(left=ft.BorderSide(3, color)),
            margin=ft.Margin(bottom=8),
        )


class SuggestionCard(ft.Container):
    """建议卡片组件。"""

    def __init__(self, suggestion: str, index: int):
        super().__init__(
            content=ft.Row(
                [
                    ft.Container(
                        ft.Text(
                            str(index),
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE,
                        ),
                        bgcolor=ft.Colors.BLUE_700,
                        border_radius=20,
                        width=28,
                        height=28,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        suggestion,
                        size=14,
                        color=ft.Colors.GREY_200,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
            padding=14,
            margin=ft.Margin(bottom=8),
        )


# ── main app ────────────────────────────────────────────────────────────────


class CodeSageApp:
    """CodeSage GUI 应用主类。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self._result: Optional[AnalysisResult] = None
        self._config: Config = load_config()
        self._analyzing = False

        self._setup_page()
        self._build_ui()
        self.page.update()

    # ── page config ──────────────────────────────────────────────────────

    def _setup_page(self):
        self.page.title = "CodeSage - AI代码审查工具"
        self.page.window_width = 1100
        self.page.window_height = 800
        self.page.window_min_width = 800
        self.page.window_min_height = 600
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.fonts = {"monospace": "Consolas"}

    # ── build UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # URL input
        self.url_input = ft.TextField(
            label="PR URL",
            hint_text="https://github.com/owner/repo/pull/123",
            border_color=ft.Colors.BLUE_400,
            focused_border_color=ft.Colors.BLUE_600,
            expand=True,
            text_size=14,
            on_submit=lambda e: self._start_analysis(),
        )

        self.analyze_btn = ft.Button(
            "开始分析",
            icon=ft.Icons.PLAY_ARROW,
            on_click=lambda e: self._start_analysis(),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE,
                padding=ft.Padding(24, 14, 24, 14),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

        self.settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            icon_color=ft.Colors.GREY_400,
            tooltip="设置",
            on_click=lambda e: self._toggle_settings(),
        )

        # Progress
        self.progress_bar = ft.ProgressBar(
            visible=False, width=400, color=ft.Colors.BLUE_400
        )
        self.progress_text = ft.Text(
            "", size=13, color=ft.Colors.GREY_400, visible=False
        )

        # Stats row (hidden until result)
        self.stats_row = ft.Row(
            [
                StatsCard("文件变更", "—", ft.Colors.BLUE_400, "📁"),
                StatsCard("新增行", "—", ft.Colors.GREEN_400, "➕"),
                StatsCard("删除行", "—", ft.Colors.RED_400, "➖"),
                StatsCard("Commits", "—", ft.Colors.PURPLE_400, "📝"),
                StatsCard("Token预算", "—", ft.Colors.ORANGE_400, "🎯"),
                StatsCard("Token使用", "—", ft.Colors.CYAN_400, "📊"),
            ],
            spacing=12,
            visible=False,
        )

        # Tabs for results (Material Design 3 API)
        self._tab_contents = [
            self._build_summary_tab(),
            self._build_risks_tab(),
            self._build_suggestions_tab(),
            self._build_raw_tab(),
        ]

        self._tab_bar = ft.TabBar(
            tabs=[
                ft.Tab(label="📋 变更摘要"),
                ft.Tab(label="⚠️ 风险识别"),
                ft.Tab(label="💡 Review建议"),
                ft.Tab(label="📝 原始分析"),
            ],
        )

        self.result_tabs = ft.Tabs(
            content=ft.Column(
                [self._tab_bar, ft.TabBarView(controls=self._tab_contents, expand=True)],
                expand=True,
            ),
            length=4,
            selected_index=0,
            animation_duration=300,
            visible=False,
            expand=True,
        )

        # Settings panel (hidden by default)
        self.settings_panel = self._build_settings_panel()
        self.settings_panel.visible = False

        # Main content area
        self.content_area = ft.Column(
            [
                self.stats_row,
                ft.Divider(height=1, color=ft.Colors.GREY_800),
                self.result_tabs,
            ],
            spacing=12,
            expand=True,
        )

        # App layout
        self.page.add(
            ft.Column(
                [
                    # Header
                    ft.Container(
                        ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "CodeSage",
                                            size=24,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.BLUE_400,
                                        ),
                                        ft.Container(
                                            ft.Text(
                                                "AI PR Review",
                                                size=11,
                                                color=ft.Colors.GREY_500,
                                            ),
                                            bgcolor=ft.Colors.GREY_900,
                                            border_radius=6,
                                            padding=ft.Padding(8, 2, 8, 2),
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                self.settings_btn,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.Padding(left=24, top=16, right=24, bottom=12),
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_800),
                    # Input area
                    ft.Container(
                        ft.Row(
                            [
                                self.url_input,
                                self.analyze_btn,
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(24, 8, 24, 8),
                    ),
                    # Progress
                    ft.Container(
                        ft.Row(
                            [self.progress_bar, self.progress_text],
                            spacing=16,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(left=24, right=24, bottom=8),
                    ),
                    # Settings
                    self.settings_panel,
                    # Content
                    ft.Container(
                        self.content_area,
                        expand=True,
                        padding=ft.Padding(24, 8, 24, 8),
                    ),
                ],
                expand=True,
                spacing=0,
            )
        )

    # ── tab contents ─────────────────────────────────────────────────────

    def _build_summary_tab(self):
        self.summary_md = ft.Markdown(
            "",
            selectable=True,
        )
        return ft.Container(
            ft.Column(
                [self.summary_md],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
        )

    def _build_risks_tab(self):
        self.risk_filter_critical = True
        self.risk_filter_major = True
        self.risk_filter_minor = True
        self.risk_filter_info = True

        def make_filter_btn(label, sev, color):
            def toggle(e):
                setattr(self, f"risk_filter_{sev}", not getattr(self, f"risk_filter_{sev}"))
                btn = e.control
                btn.bgcolor = color if getattr(self, f"risk_filter_{sev}") else ft.Colors.GREY_800
                btn.update()
                self._filter_risks()

            return ft.Container(
                ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                bgcolor=color,
                border_radius=16,
                padding=ft.Padding(12, 4, 12, 4),
                on_click=toggle,
            )

        self.risks_filter = ft.Row(
            [
                make_filter_btn("严重", "critical", SEVERITY_COLORS["critical"]),
                make_filter_btn("重要", "major", SEVERITY_COLORS["major"]),
                make_filter_btn("次要", "minor", SEVERITY_COLORS["minor"]),
                make_filter_btn("提示", "info", SEVERITY_COLORS["info"]),
            ],
            spacing=8,
            wrap=True,
        )

        self.risks_list = ft.ListView(spacing=0, expand=True)
        self.risks_empty = ft.Text(
            "未发现风险项",
            size=14,
            color=ft.Colors.GREY_500,
            text_align=ft.TextAlign.CENTER,
            visible=False,
        )

        self._all_risks: list[dict] = []

        return ft.Container(
            ft.Column(
                [
                    self.risks_filter,
                    ft.Divider(height=1, color=ft.Colors.GREY_800),
                    self.risks_list,
                    self.risks_empty,
                ],
                spacing=8,
                expand=True,
            ),
            expand=True,
        )

    def _build_suggestions_tab(self):
        self.suggestions_list = ft.ListView(spacing=0, expand=True)
        self.suggestions_empty = ft.Text(
            "暂无明显改进建议",
            size=14,
            color=ft.Colors.GREY_500,
            text_align=ft.TextAlign.CENTER,
        )

        return ft.Container(
            ft.Column(
                [self.suggestions_list, self.suggestions_empty],
                spacing=8,
                expand=True,
            ),
            expand=True,
        )

    def _build_raw_tab(self):
        self.raw_text = ft.Text(
            "",
            size=13,
            color=ft.Colors.GREY_300,
            font_family="monospace",
            selectable=True,
        )
        return ft.Container(
            ft.Column(
                [self.raw_text],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
        )

    def _build_settings_panel(self):
        cfg = self._config
        provider = cfg.ai_provider

        # 厂商选项（显示友好名称）
        self.provider_dropdown = ft.Dropdown(
            label="AI厂商",
            value=provider,
            options=[
                ft.dropdown.Option(key=p, text=PROVIDER_DISPLAY_NAMES.get(p, p))
                for p in cfg.provider_list
            ],
            border_color=ft.Colors.GREY_700,
            text_size=13,
        )
        self.provider_dropdown.on_select = lambda e: self._on_provider_changed()

        # 当前厂商的 API Key
        saved_key = cfg.get_api_key(provider) or ""
        self.api_key_input = ft.TextField(
            label=f"API Key（{PROVIDER_DISPLAY_NAMES.get(provider, provider)}）",
            value=saved_key,
            password=True,
            can_reveal_password=True,
            border_color=ft.Colors.GREY_700,
            text_size=13,
            hint_text=f"或设置环境变量 {PROVIDER_ENV_PREFIX.get(provider, provider.upper())}_API_KEY",
        )

        # 当前厂商的 Base URL
        saved_url = cfg.get_base_url(provider)
        self.base_url_input = ft.TextField(
            label="API Base URL",
            value=saved_url,
            hint_text=AI_PROVIDER_BASE_URLS.get(provider, ""),
            border_color=ft.Colors.GREY_700,
            text_size=13,
        )

        self.github_token_input = ft.TextField(
            label="GitHub Token (可选)",
            value=cfg.github_token or "",
            password=True,
            can_reveal_password=True,
            border_color=ft.Colors.GREY_700,
            text_size=13,
        )

        # 当前厂商的模型列表
        self.model_dropdown = ft.Dropdown(
            label="默认模型",
            value=cfg.default_model,
            options=[ft.dropdown.Option(m) for m in Config.model_options_for(provider)],
            border_color=ft.Colors.GREY_700,
            text_size=13,
        )

        # Token 预算配置
        self.custom_budget_switch = ft.Switch(
            label="启用自定义 Token 预算",
            value=cfg.custom_token_budget,
            active_color=ft.Colors.ORANGE_400,
            thumb_color=ft.Colors.WHITE,
        )

        self.custom_max_tokens_input = ft.TextField(
            label="自定义最大输入 Token 数",
            value=str(cfg.custom_max_input_tokens) if cfg.custom_max_input_tokens > 0 else "",
            border_color=ft.Colors.GREY_700,
            text_size=13,
            hint_text="例如: 60000",
            disabled=not cfg.custom_token_budget,
        )

        self.custom_diff_ratio_input = ft.TextField(
            label="Diff 内容占比 (0.0-1.0)",
            value=str(cfg.custom_diff_ratio),
            border_color=ft.Colors.GREY_700,
            text_size=13,
            hint_text="默认: 0.7",
            disabled=not cfg.custom_token_budget,
        )

        # 绑定开关状态变化
        def on_budget_switch_change(e):
            self.custom_max_tokens_input.disabled = not self.custom_budget_switch.value
            self.custom_diff_ratio_input.disabled = not self.custom_budget_switch.value
            self.page.update()

        self.custom_budget_switch.on_change = on_budget_switch_change

        save_btn = ft.Button(
            "保存配置",
            icon=ft.Icons.SAVE,
            on_click=lambda e: self._save_settings(),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE,
            ),
        )

        return ft.Container(
            ft.ListView(
                [
                    ft.Text(
                        "⚙️ 设置",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_700),
                    self.provider_dropdown,
                    self.api_key_input,
                    self.base_url_input,
                    self.github_token_input,
                    self.model_dropdown,
                    ft.Divider(height=1, color=ft.Colors.GREY_700),
                    ft.Text(
                        "💰 Token 预算",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ORANGE_400,
                    ),
                    self.custom_budget_switch,
                    self.custom_max_tokens_input,
                    self.custom_diff_ratio_input,
                    ft.Row([save_btn], alignment=ft.MainAxisAlignment.END),
                ],
                spacing=14,
                height=450,
            ),
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
            padding=20,
            margin=ft.Margin(24, 8, 24, 8),
        )

    # ── actions ──────────────────────────────────────────────────────────

    def _toggle_settings(self):
        self.settings_panel.visible = not self.settings_panel.visible
        self.page.update()

    def _show_snack_bar(self, message: str, bgcolor: str):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=bgcolor,
            duration=2000,
            open=True,
        )
        self.page.update()

    def _save_settings(self):
        cfg = self._config
        provider = self.provider_dropdown.value or cfg.ai_provider

        # 更新当前厂商
        cfg.ai_provider = provider

        # 保存当前厂商的独立配置（API Key + Base URL + 默认模型）
        api_key = self.api_key_input.value.strip() or None
        base_url = self.base_url_input.value.strip() or None
        default_model = self.model_dropdown.value or Config.default_model_for(provider)
        cfg.set_provider_config(provider, api_key=api_key, base_url=base_url,
                                default_model=default_model)

        # 全局字段
        cfg.github_token = self.github_token_input.value.strip() or None
        cfg.default_model = default_model

        # Token 预算配置
        cfg.custom_token_budget = self.custom_budget_switch.value
        try:
            cfg.custom_max_input_tokens = int(self.custom_max_tokens_input.value.strip()) if self.custom_max_tokens_input.value.strip() else 0
        except ValueError:
            cfg.custom_max_input_tokens = 0
        try:
            cfg.custom_diff_ratio = float(self.custom_diff_ratio_input.value.strip()) if self.custom_diff_ratio_input.value.strip() else 0.7
        except ValueError:
            cfg.custom_diff_ratio = 0.7

        # 向后兼容：如果是 openai 厂商，同步到 openai_api_key
        if provider == "openai" and api_key:
            cfg.openai_api_key = api_key

        save_config(cfg)
        self._config = cfg

        self.settings_panel.visible = False
        self._show_snack_bar(
            f"✅ 配置已保存（{PROVIDER_DISPLAY_NAMES.get(provider, provider)}）",
            ft.Colors.GREEN_700,
        )

    def _on_provider_changed(self):
        provider = self.provider_dropdown.value or self._config.ai_provider
        models = Config.model_options_for(provider)
        default_model = Config.default_model_for(provider)

        # 更新模型下拉
        self.model_dropdown.options = [ft.dropdown.Option(m) for m in models]
        if self.model_dropdown.value not in models:
            self.model_dropdown.value = self._config.get_provider_config(provider).get(
                "default_model", default_model
            )

        # 更新 API Key 字段（切换为当前厂商已保存的值）
        saved_key = self._config.get_api_key(provider) or ""
        self.api_key_input.value = saved_key
        self.api_key_input.label = f"API Key（{PROVIDER_DISPLAY_NAMES.get(provider, provider)}）"
        self.api_key_input.hint_text = (
            f"或设置环境变量 {PROVIDER_ENV_PREFIX.get(provider, provider.upper())}_API_KEY"
        )

        # 更新 Base URL 字段
        saved_url = self._config.get_base_url(provider)
        self.base_url_input.value = saved_url
        self.base_url_input.hint_text = AI_PROVIDER_BASE_URLS.get(provider, "")

        self.page.update()

    def _start_analysis(self):
        if self._analyzing:
            return

        pr_url = self.url_input.value.strip()
        if not pr_url:
            self._show_snack_bar("❌ 请输入PR URL", ft.Colors.RED_700)
            return

        provider = self.provider_dropdown.value or self._config.ai_provider
        model = self.model_dropdown.value or Config.default_model_for(provider)
        api_key = self.api_key_input.value.strip() or None
        base_url = self.base_url_input.value.strip() or None

        # 让当前界面上的选择立即生效，但不强制写入磁盘
        self._config.ai_provider = provider
        self._config.default_model = model
        self._config.set_provider_config(provider, api_key=api_key, base_url=base_url, default_model=model)

        self._analyzing = True
        self._result = None

        # Reset UI
        self.stats_row.visible = False
        self.result_tabs.visible = False
        self.progress_bar.visible = True
        self.progress_text.visible = True
        self.progress_text.value = "正在解析PR URL..."
        self.progress_bar.value = None
        self.analyze_btn.disabled = True
        self.analyze_btn.text = "分析中..."
        self.page.update()

        threading.Thread(
            target=self._perform_analysis,
            args=(pr_url, provider, model),
            daemon=True,
        ).start()

    def _perform_analysis(self, pr_url: str, provider: str, model: str):
        try:
            # Step 1: Parse URL
            self._update_progress("正在解析PR URL...", None)
            pr_ref = parse_pr_url(pr_url)

            # Step 2: Fetch PR
            self._update_progress(
                f"正在获取PR信息 ({pr_ref.owner}/{pr_ref.repo}#{pr_ref.pr_number})...",
                None,
            )
            pr_service = PRService(github_token=self._config.github_token)
            pr = pr_service.get_pr(pr_ref)

            # Step 3: AI Analysis (流式)
            self._update_progress("AI 分析中（实时生成）...", None)

            openai_provider = AIProviderFactory.create(
                provider=provider,
                api_key=self._config.get_api_key(provider),
                base_url=self._config.get_base_url(provider),
            )
            analyzer = AIAnalyzer(openai_provider, provider=provider)

            custom_max_tokens = self._config.custom_max_input_tokens if self._config.custom_token_budget else None
            custom_diff_ratio = self._config.custom_diff_ratio if self._config.custom_token_budget else None

            # 先显示结果区域，让用户看到实时输出
            pr_header = (
                f"## {pr.metadata.title}\n\n"
                f"**作者**: {pr.metadata.author}  |  "
                f"**分支**: {pr.metadata.head_ref} → {pr.metadata.base_ref}  |  "
                f"**状态**: {pr.metadata.state}\n\n"
                f"---\n\n"
            )
            self.summary_md.value = pr_header + "⏳ *正在等待 AI 响应...*"
            self.result_tabs.selected_index = 0
            self.result_tabs.visible = True
            self.page.update()

            # 流式回调：实时更新摘要内容
            accumulated = [pr_header]
            last_update = [time.time()]

            def stream_callback(chunk: str):
                accumulated[0] += chunk
                now = time.time()
                # 每 80ms 刷新一次 UI，避免过于频繁的更新
                if now - last_update[0] > 0.08:
                    self.summary_md.value = accumulated[0]
                    self.page.update()
                    last_update[0] = now

            result = analyzer.analyze_pr_stream(
                pr,
                model=model,
                custom_max_input_tokens=custom_max_tokens,
                custom_diff_ratio=custom_diff_ratio,
                stream_callback=stream_callback,
            )

            # 最后刷新确保完整内容显示
            self.summary_md.value = accumulated[0]

            # Store result
            self._result = result
            self._all_risks = _parse_risk_section(result.summary)

            self._update_progress("分析完成!", 1.0)
            time.sleep(0.2)
            self._show_results(pr)

        except Exception as ex:
            self._show_error(str(ex))

    def _update_progress(self, text: str, value: Optional[float]):
        self.progress_text.value = text
        if value is not None:
            self.progress_bar.value = value
        self.page.update()

    def _show_results(self, pr):
        result = self._result
        if not result:
            return

        # Update stats
        file_count = len(pr.files) if pr else 0
        additions = pr.total_additions if pr else 0
        deletions = pr.total_deletions if pr else 0
        commits = len(pr.commits) if pr else 0

        self.stats_row.controls = [
            StatsCard("文件变更", str(file_count), ft.Colors.BLUE_400, "📁"),
            StatsCard("新增行", f"+{additions}", ft.Colors.GREEN_400, "➕"),
            StatsCard("删除行", f"-{deletions}", ft.Colors.RED_400, "➖"),
            StatsCard("Commits", str(commits), ft.Colors.PURPLE_400, "📝"),
            StatsCard("Token预算", f"{result.diff_budget:,}", ft.Colors.ORANGE_400, "🎯"),
            StatsCard("Token使用", f"{result.input_tokens:,}", ft.Colors.CYAN_400, "📊"),
        ]
        self.stats_row.visible = True

        # Summary tab
        header = (
            f"## {pr.metadata.title if pr else 'PR Analysis'}\n\n"
            f"**作者**: {pr.metadata.author if pr else '—'}  |  "
            f"**分支**: {pr.metadata.head_ref if pr else '—'} → "
            f"{pr.metadata.base_ref if pr else '—'}  |  "
            f"**状态**: {pr.metadata.state if pr else '—'}\n\n"
            f"---\n\n"
        )
        self.summary_md.value = header + result.summary

        # Risks tab
        self.risks_list.controls.clear()
        if self._all_risks:
            self.risks_empty.visible = False
            for i, risk in enumerate(self._all_risks):
                self.risks_list.controls.append(RiskCard(risk, i + 1))
        else:
            self.risks_empty.visible = True

        # Suggestions tab
        self.suggestions_list.controls.clear()
        suggestions = _parse_suggestions(result.summary)
        if not suggestions:
            suggestions = result.suggestions
        if suggestions:
            self.suggestions_empty.visible = False
            for i, s in enumerate(suggestions):
                self.suggestions_list.controls.append(SuggestionCard(s, i + 1))
        else:
            self.suggestions_empty.visible = True

        # Raw tab
        self.raw_text.value = (
            f"# 原始分析结果\n\n"
            f"- **模型**: {result.model_used}\n"
            f"- **耗时**: {result.analysis_time:.2f}s\n\n"
            f"---\n\n"
            f"{result.summary}"
        )

        # Show results
        self.result_tabs.selected_index = 0
        self.result_tabs.visible = True
        self.progress_bar.visible = False
        self.progress_text.visible = False
        self.analyze_btn.disabled = False
        self.analyze_btn.text = "开始分析"
        self._analyzing = False
        self.page.update()

    def _show_error(self, message: str):
        self.progress_bar.visible = False
        self.progress_text.visible = False
        self.analyze_btn.disabled = False
        self.analyze_btn.text = "开始分析"
        self._analyzing = False

        self.stats_row.visible = True
        self.stats_row.controls = [
            StatsCard("错误", "✗", ft.Colors.RED_400, "❌"),
            StatsCard("", "", ft.Colors.GREY_400),
            StatsCard("", "", ft.Colors.GREY_400),
            StatsCard("", "", ft.Colors.GREY_400),
        ]

        self.summary_md.value = f"## ❌ 分析失败\n\n```\n{message}\n```"
        self.result_tabs.selected_index = 0
        self.result_tabs.visible = True
        self.risks_list.controls.clear()
        self.risks_empty.visible = True
        self.suggestions_list.controls.clear()
        self.suggestions_empty.visible = True
        self.raw_text.value = f"错误: {message}"
        self._all_risks = []
        self.page.update()

    def _filter_risks(self):
        if not self._all_risks:
            return

        enabled = set()
        if self.risk_filter_critical:
            enabled.add("critical")
        if self.risk_filter_major:
            enabled.add("major")
        if self.risk_filter_minor:
            enabled.add("minor")
        if self.risk_filter_info:
            enabled.add("info")

        self.risks_list.controls.clear()
        filtered = [r for r in self._all_risks if r.get("severity", "info") in enabled]

        if filtered:
            self.risks_empty.visible = False
            for i, risk in enumerate(filtered):
                self.risks_list.controls.append(RiskCard(risk, i + 1))
        else:
            self.risks_empty.visible = True

        self.page.update()


# ── entry ───────────────────────────────────────────────────────────────────


def _run_app(page: ft.Page):
    """Flet 页面入口。"""
    CodeSageApp(page)


def main():
    """启动 CodeSage GUI 应用。"""
    ft.app(target=_run_app, view=ft.AppView.WEB_BROWSER, port=9877)


if __name__ == "__main__":
    main()
