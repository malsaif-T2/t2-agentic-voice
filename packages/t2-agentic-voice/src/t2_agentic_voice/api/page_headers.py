"""The headers of an app's own page and its files (`page_headers`): a Content-Security-Policy
with no inline script or style and nothing loaded from another origin, framed only by the
website's origin (`frame-ancestors`, `'none'` while it is unset); `nosniff`; no referrer; and
the microphone for the page's own origin alone."""

from __future__ import annotations


def page_headers(website_origin: str | None) -> dict[str, str]:
    """The headers of a page's files: its policy, framed only by `website_origin` (none when
    unset)."""
    ancestors = website_origin or "'none'"
    policy = "; ".join(
        (
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self'",
            "connect-src 'self'",
            "img-src 'self' data:",
            "base-uri 'none'",
            "form-action 'none'",
            f"frame-ancestors {ancestors}",
        )
    )
    return {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "microphone=(self)",
    }
