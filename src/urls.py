"""URL cleaning and the "is this page in scope?" decision (rule 4)."""
from urllib.parse import parse_qs, urlsplit, urlunsplit


def normalise(url):
    """Lowercase scheme and host, drop #fragment and any trailing slash.

    The site root keeps its single "/" so that "host" and "host/" are one URL.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def query_allowed(parts, cfg):
    """True if this path is on the allowed_queries list and uses only the keys listed for it."""
    keys = set(parse_qs(parts.query))
    for rule in cfg.get("allowed_queries", []):
        if parts.path.endswith(rule["path_endswith"]) and keys <= set(rule["keys"]):
            return True
    return False


def in_scope(url, cfg):
    """Return (True, "") if the crawler may follow this URL, else (False, reason)."""
    parts = urlsplit(normalise(url))
    if parts.netloc not in cfg["allowed_hosts"]:
        return False, "host not allowed"
    if parts.query and not query_allowed(parts, cfg):
        return False, "has query string"
    if parts.path.lower().endswith((".pdf", ".docx")):
        return False, "pdf/docx not crawled"
    # Match whole path segments, so "/research" matches "/research/x" but not "/researchers".
    if not any(parts.path == p or parts.path.startswith(p + "/") for p in cfg["allowed_prefixes"]):
        return False, "outside allowed prefixes"
    return True, ""
