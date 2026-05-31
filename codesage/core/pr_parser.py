"""PR URL 解析器：将用户提供的 PR/merge request URL 解析为 `PRReference` 对象。"""

from __future__ import annotations

import re
from typing import Optional

from codesage.models.pr import PRReference


_GH_RE = re.compile(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull[s]?/(?P<number>\d+)")
_GH_RE_ALT = re.compile(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)")
_GH_FILES_RE = re.compile(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(/files)?")

_GITEE_RE = re.compile(r"https?://gitee\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls?/(?P<number>\d+)")
_GITLAB_RE = re.compile(r"https?://gitlab\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/-/merge_requests/(?P<number>\d+)")


def parse_pr_url(url: str) -> PRReference:
    """解析 PR/merge request URL，支持 `github`、`gitee`、`gitlab`。

    返回：`PRReference` 实例或在无法解析时抛出 `ValueError`。
    """

    url = url.strip()

    m = _GH_FILES_RE.match(url) or _GH_RE.match(url) or _GH_RE_ALT.match(url)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        number = int(m.group("number"))
        return PRReference(platform="github", owner=owner, repo=repo, pr_number=number)

    m = _GITEE_RE.match(url)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        number = int(m.group("number"))
        return PRReference(platform="gitee", owner=owner, repo=repo, pr_number=number)

    m = _GITLAB_RE.match(url)
    if m:
        owner = m.group("owner")
        repo = m.group("repo")
        number = int(m.group("number"))
        return PRReference(platform="gitlab", owner=owner, repo=repo, pr_number=number)

    raise ValueError(f"无法解析的 PR URL：{url}")


def try_parse_pr_url(url: str) -> Optional[PRReference]:
    """尝试解析，解析失败返回 None。"""

    try:
        return parse_pr_url(url)
    except ValueError:
        return None
