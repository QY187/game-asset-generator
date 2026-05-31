from codesage.core.pr_parser import parse_pr_url, try_parse_pr_url


def test_parse_github():
    url = "https://github.com/owner/repo/pull/123"
    pr = parse_pr_url(url)
    assert pr.platform == "github"
    assert pr.owner == "owner"
    assert pr.repo == "repo"
    assert pr.pr_number == 123


def test_parse_gitee_and_gitlab():
    gitee = "https://gitee.com/test/repo/pulls/45"
    gitlab = "https://gitlab.com/acme/project/-/merge_requests/7"

    p1 = parse_pr_url(gitee)
    assert p1.platform == "gitee" and p1.pr_number == 45

    p2 = parse_pr_url(gitlab)
    assert p2.platform == "gitlab" and p2.pr_number == 7


def test_try_parse_invalid():
    assert try_parse_pr_url("not-a-url") is None
