import pytest

from greenlit.github import GitHubAPI, GitHubError, mask, parse_repo_url


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/octo/hello-world",
        "https://github.com/octo/hello-world.git",
        "https://github.com/octo/hello-world/",
        "https://github.com/octo/hello-world/tree/main/src",
        "http://www.github.com/octo/hello-world",
        "github.com/octo/hello-world",
        "git@github.com:octo/hello-world.git",
        "octo/hello-world",
        "  https://github.com/octo/hello-world  ",
    ],
)
def test_parse_repo_url_accepts_common_forms(text):
    ref = parse_repo_url(text)
    assert (ref.owner, ref.name) == ("octo", "hello-world")
    assert ref.clone_url == "https://github.com/octo/hello-world.git"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "https://gitlab.com/octo/hello-world",
        "https://github.com.evil.com/octo/hello-world",
        "https://github.com/octo",
        "file:///etc/passwd",
        "../../etc",
        "octo/..",
    ],
)
def test_parse_repo_url_rejects_non_github_and_malformed(text):
    with pytest.raises(ValueError):
        parse_repo_url(text)


def test_mask_scrubs_raw_and_basic_auth_forms():
    import base64

    token = "github_pat_SECRET123"
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    text = f"failed with {token} and header basic {encoded}"
    masked = mask(text, token)
    assert token not in masked and encoded not in masked


def test_api_errors_are_friendly_and_never_contain_the_token():
    import httpx

    token = "github_pat_SECRET123"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {token}"
        return httpx.Response(403, json={"message": f"Resource not accessible by token {token}"})

    api = GitHubAPI(token, transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubError) as exc:
        api.get_repo(parse_repo_url("octo/hello"))
    assert token not in str(exc.value)
    assert "Read and write" in str(exc.value)
