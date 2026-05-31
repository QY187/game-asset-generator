"""Gitee API 封装，用于获取 PR 信息。"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import requests

from codesage.models.pr import Commit, FileChange, PRMetadata, PRReference
from codesage.utils.config import load_config

_GITEE_RE = re.compile(r"https?://gitee\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls?/(?P<number>\d+)")


class GiteeProvider:
    """Gitee API 提供者"""

    BASE_URL = "https://gitee.com/api/v5"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITEE_TOKEN")
        self.session = requests.Session()
        if self.token:
            self.session.params["access_token"] = self.token
        self._resolved: Dict[tuple, PRReference] = {}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送 API 请求。"""
        url = f"{self.BASE_URL}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def _resolve_redirect(self, pr_ref: PRReference) -> PRReference:
        """Resolve Gitee web redirect to get the canonical owner/repo.

        Gitee web pages may redirect (e.g. czy22533/code-sage → QY/CodeSage)
        but the API does NOT follow redirects, returning 404 instead.
        This method fetches the web page once to extract the real repo path.
        Results are cached per PR reference.
        """
        key = (pr_ref.owner, pr_ref.repo, pr_ref.pr_number)
        if key in self._resolved:
            return self._resolved[key]
        url = f"https://gitee.com/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.pr_number}"
        resp = requests.head(url, allow_redirects=True)
        final_url = resp.url
        m = _GITEE_RE.match(final_url)
        resolved = pr_ref
        if m:
            resolved = PRReference(
                platform="gitee",
                owner=m.group("owner"),
                repo=m.group("repo"),
                pr_number=pr_ref.pr_number,
            )
        self._resolved[key] = resolved
        return resolved

    def get_pr_metadata(self, pr_ref: PRReference) -> PRMetadata:
        """获取 PR 元数据。"""
        resolved_ref = self._resolve_redirect(pr_ref)
        endpoint = f"/repos/{resolved_ref.owner}/{resolved_ref.repo}/pulls/{resolved_ref.pr_number}"
        data = self._request("GET", endpoint)

        return PRMetadata(
            title=data.get("title", ""),
            body=data.get("description", "") or "",
            author=data.get("user", {}).get("name", "") if isinstance(data.get("user"), dict) else (data.get("user", {}).get("login", "") if isinstance(data.get("user"), dict) else str(data.get("user", ""))),
            state=data.get("state", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            base_ref=data.get("base_branch", ""),
            head_ref=data.get("head_branch", ""),
            labels=[],
            assignees=[],
        )

    def get_pr_files(self, pr_ref: PRReference) -> List[FileChange]:
        """获取 PR 文件变更。"""
        resolved_ref = self._resolve_redirect(pr_ref)
        endpoint = f"/repos/{resolved_ref.owner}/{resolved_ref.repo}/pulls/{resolved_ref.pr_number}/files"
        data = self._request("GET", endpoint)

        return [
            FileChange(
                filename=f.get("filename", "") or f.get("new_path", ""),
                status=self._convert_status(f.get("status", "") or ""),
                additions=f.get("additions", 0) or 0,
                deletions=f.get("deletions", 0) or 0,
                changes=(f.get("additions", 0) or 0) + (f.get("deletions", 0) or 0),
                patch=self._extract_patch(f),
            )
            for f in data
        ]

    def _extract_patch(self, f: dict) -> str:
        """从 Gitee API 文件对象中提取 patch 文本。

        Gitee API v5 的 patch 字段是一个对象：{"diff": "...", "too_large": bool}，
        而 GitHub API 的 patch 是纯字符串。此方法兼容两种格式。
        """
        patch_raw = f.get("patch", "")
        if isinstance(patch_raw, dict):
            return patch_raw.get("diff", "")
        if isinstance(patch_raw, str) and patch_raw:
            return patch_raw
        # fallback: 顶层 diff 字段
        top_diff = f.get("diff", "")
        if isinstance(top_diff, dict):
            return top_diff.get("diff", "")
        return top_diff or ""

    def _convert_status(self, status: str) -> str:
        """转换 Gitee 文件状态到统一格式。"""
        mapping = {
            "add": "added",
            "modify": "modified",
            "delete": "deleted",
            "renamed": "renamed",
        }
        return mapping.get(status, status)

    def get_pr_commits(self, pr_ref: PRReference) -> List[Commit]:
        """获取 PR 的 Commit 列表。"""
        resolved_ref = self._resolve_redirect(pr_ref)
        endpoint = f"/repos/{resolved_ref.owner}/{resolved_ref.repo}/pulls/{resolved_ref.pr_number}/commits"
        data = self._request("GET", endpoint)

        return [
            Commit(
                sha=c.get("sha", ""),
                message=c.get("message", ""),
                author=c.get("author", {}).get("name", "") if isinstance(c.get("author"), dict) else str(c.get("author", "")),
                date=c.get("author", {}).get("date", "") if isinstance(c.get("author"), dict) else "",
            )
            for c in data
        ]

    def post_comment(self, pr_ref: PRReference, body: str) -> bool:
        """在 PR 上发布评论。"""
        resolved_ref = self._resolve_redirect(pr_ref)
        endpoint = f"/repos/{resolved_ref.owner}/{resolved_ref.repo}/pulls/{resolved_ref.pr_number}/comments"
        try:
            self._request("POST", endpoint, json={"body": body})
            return True
        except Exception:
            return False
