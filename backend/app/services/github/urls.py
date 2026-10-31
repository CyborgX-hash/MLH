"""Parse and validate public GitHub repository URLs."""
import re
from typing import Tuple

from app.services.github.errors import InvalidRepositoryURL

_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
_REPO = r"[A-Za-z0-9._-]{1,100}"
_HTTP = re.compile(rf"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>{_OWNER})/(?P<repo>{_REPO})(?:[/?#].*)?$", re.I)
_SSH = re.compile(rf"^git@github\.com:(?P<owner>{_OWNER})/(?P<repo>{_REPO})$", re.I)
# First path segments that are GitHub pages, not user or organisation names.
_RESERVED = {
    "about", "apps", "collections", "enterprise", "explore", "features", "issues", "login", "marketplace",
    "new", "notifications", "orgs", "organizations", "pricing", "pulls", "search", "settings", "sponsors",
    "topics", "trending",
}


def parse_repo_url(url: str) -> Tuple[str, str]:
    """Return (owner, repo) for a GitHub repository URL or raise InvalidRepositoryURL."""
    text = (url or "").strip()
    if not text:
        raise InvalidRepositoryURL("Enter a GitHub repository URL, for example https://github.com/psf/requests")
    if len(text) > 300:
        raise InvalidRepositoryURL("The URL is too long.")
    m = _HTTP.match(text) or _SSH.match(text)
    if not m:
        raise InvalidRepositoryURL(
            "Not a GitHub repository URL. Use the form https://github.com/<owner>/<repository>."
        )
    owner, repo = m.group("owner"), m.group("repo")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if owner.lower() in _RESERVED or repo in ("", ".", "..") or repo.startswith("."):
        raise InvalidRepositoryURL("That URL points to a GitHub page, not a repository.")
    return owner, repo
