"""Episode lists of podcasts: RSS feeds and public YouTube pages.

Every parser raises ValueError when the page does not have the expected shape,
so a changed page layout or a consent page is never read as "no episodes".
"""
import datetime
import email.utils
import json
import re
import xml.etree.ElementTree as ET

_UTC = datetime.timezone.utc


def _iso_utc(moment):
    return moment.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rss(xml_text):
    """Episodes of an RSS feed: episode_id (guid, else link), title, published (UTC), url."""
    items = ET.fromstring(xml_text).findall("./channel/item")
    if not items:
        raise ValueError("RSS feed without items")
    out = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        when = item.findtext("pubDate")
        if not when:
            raise ValueError(f"RSS item without pubDate: {title!r}")
        link = (item.findtext("link") or "").strip()
        out.append({
            "episode_id": (item.findtext("guid") or "").strip() or link,
            "title": title,
            "published": _iso_utc(email.utils.parsedate_to_datetime(when)),
            "url": link,
        })
    return out


def _walk(node, key, found):
    if isinstance(node, dict):
        if key in node:
            found.append(node[key])
        for value in node.values():
            _walk(value, key, found)
    elif isinstance(node, list):
        for value in node:
            _walk(value, key, found)
    return found


def youtube_list(html):
    """Videos on a YouTube playlist page, in page order: video_id, title, age label ("5d ago").

    The page shows at most the 100 newest entries and gives ages only roughly;
    exact dates come from each video's own page (youtube_watch).
    """
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        raise ValueError("YouTube page without its data block")
    out, seen = [], set()
    for entry in _walk(json.loads(m.group(1)), "lockupViewModel", []):
        video_id = entry.get("contentId")
        if entry.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO" or video_id in seen:
            continue
        seen.add(video_id)
        meta = entry["metadata"]["lockupMetadataViewModel"]
        parts = [p["text"]["content"] for row in _walk(meta.get("metadata", {}), "metadataParts", []) for p in row
                 if "text" in p]
        ages = [p for p in parts if p.endswith(" ago")]
        out.append({"video_id": video_id, "title": meta["title"]["content"], "age": ages[0] if ages else None})
    return out


def youtube_watch(html):
    """Publication time (UTC) and channel of a video, from its public page."""
    when = re.search(r'"publishDate":"([^"]+)"', html)
    channel = re.search(r'"externalChannelId":"([^"]+)"', html)
    if not when or not channel:
        raise ValueError("YouTube video page without a publication date")
    return {"published": _iso_utc(datetime.datetime.fromisoformat(when.group(1))), "channel_id": channel.group(1)}
