"""GitHub API 封装，用于获取 PR 信息。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from codesage.models.pr import Commit, FileChange, PRMetadata, PRReference
from codesage.utils.config import load_config


class GitHubProvider:
    """GitHub API 提供者"""

    BASE_URL = "https://api.github.com"
    TIMEOUT = 30  # 超时时间（秒）
    MAX_RETRIES = 2  # 最大重试次数

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.session = requests.Session()
        
        # 配置连接池和重试策略
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        if self.token:
            self.session.headers["Authorization"] = f"token {self.token}"
        self.session.headers["Accept"] = "application/vnd.github.v3+json"

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送 API 请求（带超时）。"""
        url = f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("timeout", self.TIMEOUT)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_pr_metadata(self, pr_ref: PRReference) -> PRMetadata:
        """获取 PR 元数据。"""
        endpoint = f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.pr_number}"
        data = self._request("GET", endpoint)

        return PRMetadata(
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            author=data.get("user", {}).get("login", ""),
            state=data.get("state", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            base_ref=data.get("base", {}).get("ref", ""),
            head_ref=data.get("head", {}).get("ref", ""),
            labels=[label.get("name") for label in data.get("labels", [])],
            assignees=[a.get("login") for a in data.get("assignees", [])],
        )

    def get_pr_files(self, pr_ref: PRReference) -> List[FileChange]:
        """获取 PR 文件变更。"""
        endpoint = f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.pr_number}/files"
        data = self._request("GET", endpoint)

        return [
            FileChange(
                filename=f.get("filename", ""),
                status=f.get("status", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                changes=f.get("changes", 0),
                patch=f.get("patch", ""),
            )
            for f in data
        ]

    def get_pr_commits(self, pr_ref: PRReference) -> List[Commit]:
        """获取 PR 的 Commit 列表。"""
        endpoint = f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.pr_number}/commits"
        data = self._request("GET", endpoint)

        return [
            Commit(
                sha=c.get("sha", ""),
                message=c.get("commit", {}).get("message", ""),
                author=c.get("commit", {}).get("author", {}).get("name", ""),
                date=c.get("commit", {}).get("author", {}).get("date", ""),
            )
            for c in data
        ]

    def post_comment(self, pr_ref: PRReference, body: str) -> bool:
        """在 PR 上发布评论。"""
        endpoint = f"/repos/{pr_ref.owner}/{pr_ref.repo}/issues/{pr_ref.pr_number}/comments"
        try:
            self._request("POST", endpoint, json={"body": body})
            return True
        except Exception:
            return False
