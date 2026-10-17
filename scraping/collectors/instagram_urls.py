"""Instagram input validation shared by both collectors and access probes."""

import re
from urllib.parse import urlsplit


def target_kind(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in
            {"www.instagram.com", "instagram.com"} or parsed.query or parsed.fragment):
        raise ValueError("Use a plain HTTPS Instagram URL without query parameters.")
    for kind, pattern in (
        ("post", r"/(?:p|reel)/[A-Za-z0-9_-]+/?"),
        ("hashtag", r"/explore/tags/[\w]+/?"),
        ("location", r"/explore/locations/\d+(?:/[^/]+)?/?"),
        ("profile", r"/(?!accounts/?$|stories/?$|explore/?$)[A-Za-z0-9._]+/?"),
    ):
        if re.fullmatch(pattern, parsed.path):
            return kind
    raise ValueError("Use a public profile, post, hashtag, or location URL.")
