"""Checks that must pass before an unattended run sends its first request.

docs/SCANNING-POLICY.md requires the User-Agent to carry "a working contact
path". The 2026-08-22 census sent 400 requests advertising a repository URL
that returned 404, because the repository was private and nothing checked.
An unattended runner cannot notice that; a preflight can, and this is the
general shape ADR-0022 asks for: every policy line a machine can check
before the first request is checked before the first request.
"""

from __future__ import annotations

import re

import httpx

import a2a_scorecard


class PreflightFailed(Exception):
    """A precondition for scanning is not met. Never caught by the batch
    runner: refusing to start is the entire point."""


def contact_url(user_agent: str = a2a_scorecard.USER_AGENT) -> str:
    """The contact URL advertised in the User-Agent."""
    match = re.search(r"https?://\S+?(?=[);\s]|$)", user_agent)
    if match is None:
        raise PreflightFailed(
            f"User-Agent carries no contact URL, which the scanning policy requires: {user_agent!r}"
        )
    return match.group(0)


def check_contact_reachable(
    user_agent: str = a2a_scorecard.USER_AGENT,
    *,
    timeout_s: float = 10.0,
    client: httpx.Client | None = None,
) -> str:
    """Raise PreflightFailed unless the advertised contact URL resolves.

    A 404 is the failure this exists to catch, so any non-success status is
    a failure rather than a warning. `client` is injectable so tests can
    exercise this against the in-process fake agent instead of the network
    (CLAUDE.md rule 2).
    """
    url = contact_url(user_agent)
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout_s, follow_redirects=True)
    try:
        response = client.get(url, headers={"User-Agent": user_agent})
    except httpx.HTTPError as exc:
        raise PreflightFailed(f"contact URL {url} is not reachable: {exc}") from exc
    finally:
        if owns_client:
            client.close()
    if response.status_code >= 400:
        raise PreflightFailed(
            f"contact URL {url} returned HTTP {response.status_code}. The scanning policy "
            "requires a working contact path; scanning while advertising a dead link is "
            "what this check exists to prevent."
        )
    return url
