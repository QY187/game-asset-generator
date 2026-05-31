from codesage.core.pr_service import fetch_pr, try_fetch_pr


def test_fetch_pr_minimal():
    url = "https://github.com/owner/repo/pull/123"
    pr = fetch_pr(url)
    assert pr.reference.pr_number == 123
    assert pr.metadata.state == "open"


def test_try_fetch_invalid():
    assert try_fetch_pr("invalid-url") is None
