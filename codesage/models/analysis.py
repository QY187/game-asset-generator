"""分析结果数据模型"""
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """置信度等级，用于评估风险识别的可信度"""
    
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskSeverity(str, Enum):
    """风险严重程度，用于对风险进行分级"""
    
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class RiskType(str, Enum):
    """风险类型，用于分类不同类型的代码问题"""
    
    SECURITY = "security"
    PERFORMANCE = "performance"
    STABILITY = "stability"
    MAINTAINABILITY = "maintainability"
    TEST_COVERAGE = "test_coverage"
    BEST_PRACTICE = "best_practice"


class Risk(BaseModel):
    """风险项，描述识别到的代码问题"""
    
    id: str = Field(description="风险唯一标识")
    file_path: str = Field(description="文件路径")
    line_start: int = Field(description="起始行号")
    line_end: int = Field(description="结束行号")
    severity: RiskSeverity = Field(description="严重程度")
    risk_type: RiskType = Field(description="风险类型")
    title: str = Field(description="风险标题")
    description: str = Field(description="风险描述")
    confidence: ConfidenceLevel = Field(description="置信度")
    code_snippet: Optional[str] = Field(description="问题代码片段", default=None)
    suggestion: Optional[str] = Field(description="修复建议", default=None)
    fix_example: Optional[str] = Field(description="修复示例代码", default=None)


class ChangeType(str, Enum):
    """变更类型，用于分类PR的变更性质"""
    
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    PERF = "perf"
    DOCS = "docs"
    TEST = "test"
    CHORE = "chore"


class Summary(BaseModel):
    """变更摘要，对PR变更进行概括性描述"""
    
    title: str = Field(description="PR标题")
    description: str = Field(description="PR描述")
    author: str = Field(description="作者")
    change_type: List[ChangeType] = Field(description="变更类型列表", default_factory=list)
    file_count: int = Field(description="变更文件数量")
    additions: int = Field(description="新增行数")
    deletions: int = Field(description="删除行数")
    key_changes: List[str] = Field(description="核心变更点", default_factory=list)
    impact_assessment: Optional[str] = Field(description="影响评估", default=None)
    ai_summary: Optional[str] = Field(description="AI生成的摘要", default=None)


class AnalysisResult(BaseModel):
    """完整分析结果，包含PR的所有分析信息"""

    pr_url: str = Field(description="PR URL", default="")
    summary: str = Field(description="AI分析结果（Markdown格式）", default="")
    risks: List[Risk] = Field(description="风险列表", default_factory=list)
    suggestions: List[str] = Field(description="Review建议列表", default_factory=list)
    analysis_time: float = Field(description="分析耗时（秒）", default=0.0)
    model_used: str = Field(description="使用的AI模型", default="")
    input_tokens: int = Field(description="输入 token 数量", default=0)
    context_window: int = Field(description="模型上下文窗口大小", default=0)
    diff_budget: int = Field(description="Diff 内容分配的 token 预算", default=0)

    @property
    def critical_risks(self) -> List[Risk]:
        """获取严重风险列表"""
        return [r for r in self.risks if r.severity == RiskSeverity.CRITICAL]
    
    @property
    def major_risks(self) -> List[Risk]:
        """获取重要风险列表"""
        return [r for r in self.risks if r.severity == RiskSeverity.MAJOR]
    
    @property
    def minor_risks(self) -> List[Risk]:
        """获取次要风险列表"""
        return [r for r in self.risks if r.severity == RiskSeverity.MINOR]
