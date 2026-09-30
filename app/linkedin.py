"""LinkedIn REST API publisher module.

Supports:
- Auto-fetching user profile and URN (urn:li:person:...) via OpenID /v2/userinfo
- Publishing text posts (with hashtags & links) via POST https://api.linkedin.com/rest/posts
- Automatic draft status updating to POSTED with linkedin_post_id
"""
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.db import Draft, DraftStatus, session, utcnow

log = logging.getLogger(__name__)

USERINFO_ENDPOINT = "https://api.linkedin.com/v2/userinfo"
POSTS_ENDPOINT = "https://api.linkedin.com/rest/posts"

# Candidate active LinkedIn API versions in YYYYMM format
CANDIDATE_VERSIONS = [
    "202604",
    "202601",
    "202511",
    "202506",
    "202501",
    "202411",
    "202408",
]
_ACTIVE_VERSION: str | None = None


def get_profile(access_token: str | None = None) -> dict[str, Any]:
    """Fetch user profile and Person URN using the access token."""
    token = access_token or get_settings().linkedin_access_token
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN is not configured in .env")

    headers = {
        "Authorization": f"Bearer {token}",
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(USERINFO_ENDPOINT, headers=headers)
        if resp.status_code != 200:
            log.error("Failed to fetch LinkedIn profile: %s - %s", resp.status_code, resp.text)
            resp.raise_for_status()
        data = resp.json()

    sub = data.get("sub", "")
    person_urn = f"urn:li:person:{sub}" if sub else ""

    return {
        "sub": sub,
        "person_urn": person_urn,
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "picture": data.get("picture", ""),
    }


def post_to_linkedin(
    text: str,
    author_urn: str | None = None,
    access_token: str | None = None,
) -> str:
    """Publish a post to LinkedIn personal profile feed.

    Returns the published post URN (e.g., 'urn:li:share:...' or 'urn:li:restPost:...').
    """
    settings = get_settings()
    token = access_token or settings.linkedin_access_token
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN is not configured in .env")

    urn = author_urn or settings.linkedin_person_urn
    if not urn:
        # Auto-resolve Person URN from /v2/userinfo
        log.info("LINKEDIN_PERSON_URN not set; auto-detecting via userinfo...")
        profile = get_profile(token)
        urn = profile.get("person_urn")
        if not urn:
            raise ValueError("Could not resolve LinkedIn Person URN from profile")
        log.info("Auto-detected LinkedIn Person URN: %s (%s)", urn, profile.get("name"))

    payload = {
        "author": urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    global _ACTIVE_VERSION
    versions_to_try = [_ACTIVE_VERSION] if _ACTIVE_VERSION else CANDIDATE_VERSIONS
    last_err = None

    with httpx.Client(timeout=20.0) as client:
        for ver in versions_to_try:
            headers = {
                "Authorization": f"Bearer {token}",
                "LinkedIn-Version": ver,
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
            resp = client.post(POSTS_ENDPOINT, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                _ACTIVE_VERSION = ver
                log.info("Successfully posted to LinkedIn! Active version: %s", ver)
                post_urn = resp.headers.get("x-restli-id") or ""
                if not post_urn and resp.content:
                    try:
                        res_data = resp.json()
                        post_urn = res_data.get("id") or ""
                    except Exception:
                        pass
                return post_urn or "urn:li:post:success"

            if resp.status_code == 426:
                log.warning("LinkedIn version %s returned 426 Upgrade Required, trying next...", ver)
                last_err = resp.text
                continue

            # Non-426 error (e.g. 401, 403, 400 bad payload)
            log.error("LinkedIn post creation failed (%d): %s", resp.status_code, resp.text)
            err_detail = resp.text
            try:
                err_json = resp.json()
                err_detail = err_json.get("message") or err_json.get("description") or resp.text
            except Exception:
                pass
            raise RuntimeError(f"LinkedIn API error ({resp.status_code}): {err_detail}")

    raise RuntimeError(f"LinkedIn API error (426 Upgrade Required): None of candidate versions was accepted. Last response: {last_err}")


def publish_draft(draft_id: int) -> dict[str, Any]:
    """Publish a database Draft to LinkedIn and update its status."""
    with session() as s:
        draft = s.get(Draft, draft_id)
        if not draft:
            raise ValueError(f"Draft #{draft_id} not found")

        if draft.status == DraftStatus.POSTED and draft.linkedin_post_id:
            return {
                "success": True,
                "already_posted": True,
                "draft_id": draft.id,
                "linkedin_post_id": draft.linkedin_post_id,
            }

        post_urn = post_to_linkedin(draft.text)

        draft.linkedin_post_id = post_urn
        draft.status = DraftStatus.POSTED
        draft.posted_at = utcnow()
        s.add(draft)
        s.commit()
        s.refresh(draft)

        return {
            "success": True,
            "draft_id": draft.id,
            "linkedin_post_id": post_urn,
            "posted_at": draft.posted_at.isoformat() if draft.posted_at else None,
        }
