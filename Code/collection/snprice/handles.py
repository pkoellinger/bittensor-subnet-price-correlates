"""Find a subnet's X account when no source lists it: guess handles, keep only verified ones.

Guesses are built from the subnet's name, its GitHub owner and its website. A guess is
accepted only if the profile itself points back to the subnet: its link goes to the
subnet's site, or its text names the subnet together with the subnet's number.
"""
import re
from urllib.parse import urlparse

from .textmatch import _ID
from .webtext import site_of

_SUFFIXES = ("", "ai", "_ai", "hq", "_io")
MAX_HANDLE = 15
MIN_HANDLE = 4
MIN_HANDLE_SHORT_STEM = 5      # a two- or three-letter stem alone is anybody's handle


def _stem(text):
    return re.sub(r"[^a-z0-9_]", "", (text or "").lower())[:MAX_HANDLE]


def candidate_handles(name, gh_owner, website):
    """Handles worth looking up, most likely first, without duplicates."""
    stems = [_stem(re.sub(r"[^A-Za-z0-9]", "", name or ""))]
    if website:
        host = site_of(website if "//" in website else "https://" + website)
        stems.append(_stem(host.split(".")[0]))
    out = []
    for stem in stems:
        if not stem:
            continue
        floor = MIN_HANDLE if len(stem) >= MIN_HANDLE else MIN_HANDLE_SHORT_STEM
        for suffix in _SUFFIXES:
            handle = stem + suffix
            if floor <= len(handle) <= MAX_HANDLE and handle not in out:
                out.append(handle)
    owner = _stem((gh_owner or "").replace("-", "_"))
    if len(owner) >= MIN_HANDLE and owner not in out:
        out.append(owner)
    return out


def profile_matches(profile, netuid, name, website):
    """Why an X profile is the subnet's own account ("site" or "name and number"), or None."""
    urls = ((profile.get("entities") or {}).get("url") or {}).get("urls") or []
    linked = next((u.get("expanded_url") for u in urls if u.get("expanded_url")), None)
    if linked and website:
        home = website if "//" in website else "https://" + website
        if urlparse(linked).hostname and site_of(linked) == site_of(home):
            return "site"
    text = " ".join(filter(None, [profile.get("username"), profile.get("name"), profile.get("description")]))
    numbers = {int(m.group(1)) for m in _ID.finditer(text)}
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if netuid in numbers and key and key in re.sub(r"[^a-z0-9]", "", text.lower()):
        return "name and number"
    return None
