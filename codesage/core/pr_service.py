"""PR 服务：统一封装多平台 PR 获取。"""

from __future__ import annotations

import concurrent.futures
from typing import Callable, List, Optional, Tuple

from codesage.models.pr import Commit, FileChange, PR, PRMetadata, PRReference
from codesage.providers.github import GitHubProvider
from codesage.providers.gitee import GiteeProvider


class PRService:
    """PR 服务，根据平台类型选择对应的 API 提供者"""

    def __init__(self, github_token: str | None = None):
        self.github = GitHubProvider(token=github_token)
        self.gitee = GiteeProvider()

    def _get_provider(self, platform: str):
        """根据平台类型获取对应的提供者"""
        if platform == "github":
            return self.github
        elif platform == "gitee":
            return self.gitee
        else:
            raise ValueError(f"不支持的平台：{platform}")

    def get_pr_metadata(self, pr_ref: PRReference) -> PRMetadata:
        """获取 PR 元数据"""
        provider = self._get_provider(pr_ref.platform)
        return provider.get_pr_metadata(pr_ref)

    def get_pr_files(self, pr_ref: PRReference) -> List[FileChange]:
        """获取 PR 文件变更"""
        provider = self._get_provider(pr_ref.platform)
        return provider.get_pr_files(pr_ref)

    def get_pr_commits(self, pr_ref: PRReference) -> List[Commit]:
        """获取 PR 的 Commit 列表"""
        provider = self._get_provider(pr_ref.platform)
        return provider.get_pr_commits(pr_ref)

    def get_pr(self, pr_ref: PRReference, progress_callback: Optional[Callable[[str], None]] = None) -> PR:
        """获取完整的 PR 对象（并行请求优化）
        
        Args:
            pr_ref: PR 引用
            progress_callback: 进度回调函数
        """
        provider = self._get_provider(pr_ref.platform)
        
        metadata: Optional[PRMetadata] = None
        files: Optional[List[FileChange]] = None
        commits: Optional[List[Commit]] = None
        
        # 使用线程池并行请求三个 API
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 提交任务
            future_metadata = executor.submit(provider.get_pr_metadata, pr_ref)
            future_files = executor.submit(provider.get_pr_files, pr_ref)
            future_commits = executor.submit(provider.get_pr_commits, pr_ref)
            
            # 等待并处理结果，同时更新进度
            if progress_callback:
                progress_callback("正在获取 PR 信息...")
            
            for future in concurrent.futures.as_completed([future_metadata, future_files, future_commits]):
                if future == future_metadata:
                    metadata = future.result()
                    if progress_callback:
                        progress_callback("获取 PR 信息完成！")
                elif future == future_files:
                    files = future.result()
                    if progress_callback:
                        progress_callback("获取文件变更完成！")
                elif future == future_commits:
                    commits = future.result()
                    if progress_callback:
                        progress_callback("获取提交记录完成！")
        
        # 确保所有数据都获取成功
        if not metadata or not files or not commits:
            raise RuntimeError("获取 PR 数据失败")
        
        return PR(
            reference=pr_ref,
            metadata=metadata,
            files=files,
            commits=commits,
        )

    def post_comment(self, pr_ref: PRReference, body: str) -> bool:
        """在 PR 上发布评论"""
        provider = self._get_provider(pr_ref.platform)
        return provider.post_comment(pr_ref, body)
