"""Conservative URL normalization for GEO citation deduplication.

Only known tracking parameters are removed. Product and content parameters
remain part of the identity, so variants are never merged by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_KEYS = {"fbclid", "gclid", "gbraid", "wbraid", "msclkid"}


@dataclass(frozen=True)
class CanonicalURL:
    url: str
    domain: str
    url_hash: str


def normalize_url(raw_url: str) -> CanonicalURL:
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("URL is empty")
    parts = urlsplit(raw_url.strip())
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are supported")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Credential-bearing URLs are not supported")

    try:
        domain = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Invalid URL host or port") from exc
    if not domain:
        raise ValueError("Invalid URL host")
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    host = f"[{domain}]" if ":" in domain else domain
    netloc = host if port is None or default_port else f"{host}:{port}"

    # Retain path and non-tracking query semantics. In particular, variant=50ml
    # and variant=100ml must produce different identities.
    path = parts.path or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    query = urlencode(sorted(query_pairs))
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    source_domain = domain[4:] if domain.startswith("www.") else domain
    return CanonicalURL(
        url=canonical,
        domain=source_domain,
        url_hash=sha256(canonical.encode("utf-8")).hexdigest(),
    )
