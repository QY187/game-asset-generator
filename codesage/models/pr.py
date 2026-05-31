"""PR相关数据模型"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PRReference(BaseModel):
    """PR引用信息，用于标识一个具体的PR"""
    
    platform: str = Field(description="代码托管平台：github/gitee/gitlab")
    owner: str = Field(description="仓库所有者")
    repo: str = Field(description="仓库名称")
    pr_number: int = Field(description="PR编号")
    
    @property
    def url(self) -> str:
        """生成PR的完整URL，根据平台类型返回不同格式"""
        if self.platform == "github":
            return f"https://github.com/{self.owner}/{self.repo}/pull/{self.pr_number}"
        elif self.platform == "gitee":
            return f"https://gitee.com/{self.owner}/{self.repo}/pulls/{self.pr_number}"
        elif self.platform == "gitlab":
            return f"https://gitlab.com/{self.owner}/{self.repo}/-/merge_requests/{self.pr_number}"
        else:
            return f"https://github.com/{self.owner}/{self.repo}/pull/{self.pr_number}"


class FileChange(BaseModel):
    """文件变更信息，描述单个文件的变更内容"""
    
    filename: str = Field(description="文件名")
    status: str = Field(description="变更状态：added/modified/deleted")
    additions: int = Field(description="新增行数")
    deletions: int = Field(description="删除行数")
    changes: int = Field(description="总变更行数")
    patch: Optional[str] = Field(description="diff内容", default=None)
    content: Optional[str] = Field(description="文件完整内容", default=None)


class Commit(BaseModel):
    """Commit信息，描述PR中的单个提交"""
    
    sha: str = Field(description="Commit哈希")
    message: str = Field(description="Commit消息")
    author: str = Field(description="作者")
    date: str = Field(description="提交日期")


class PRMetadata(BaseModel):
    """PR元数据，包含PR的基本信息"""
    
    title: str = Field(description="PR标题")
    body: str = Field(description="PR描述")
    author: str = Field(description="作者")
    state: str = Field(description="状态：open/closed/merged")
    created_at: str = Field(description="创建时间")
    updated_at: str = Field(description="更新时间")
    base_ref: str = Field(description="目标分支")
    head_ref: str = Field(description="源分支")
    labels: List[str] = Field(description="标签列表", default_factory=list)
    assignees: List[str] = Field(description="负责人列表", default_factory=list)


class PR(BaseModel):
    """完整PR对象，包含所有相关信息"""
    
    reference: PRReference = Field(description="PR引用")
    metadata: PRMetadata = Field(description="PR元数据")
    files: List[FileChange] = Field(description="文件变更列表", default_factory=list)
    commits: List[Commit] = Field(description="Commit列表", default_factory=list)
    
    @property
    def total_additions(self) -> int:
        """计算总新增行数"""
        return sum(f.additions for f in self.files)
    
    @property
    def total_deletions(self) -> int:
        """计算总删除行数"""
        return sum(f.deletions for f in self.files)
    
    @property
    def total_files(self) -> int:
        """计算变更文件数量"""
        return len(self.files)
