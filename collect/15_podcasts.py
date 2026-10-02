"""Appearances on Bittensor podcasts in the 12 months before T (Y17).

Shows and sources: config/podcasts.json (three audio feeds, three YouTube channels).
No key is needed: audio feeds are RSS, YouTube lists are the public "uploads" and
"live" playlist pages of a channel (the 100 newest entries each), and the exact
publication time comes from each video's public page.

An episode counts for a subnet when its TITLE names the subnet by number, handle or
name (rules: snprice/textmatch.py; aliases: config/name_aliases.csv). Descriptions are
not used: they carry sponsor lines and passing mentions. A title that says only
"Subnet 78" counts for the project that held the netuid when the episode was published
(snprice.textmatch.valid_for_project). Titles with a common-word name and no number
("Score", "Apex") are weak matches: they are listed and count only if confirmed in
data/manual/podcast_weak_matches.csv.

Within a show, episodes on the same subnet less than 14 days apart count once (a live
stream and its edited re-upload).

Needs  data/intermediate/history_wave<N>.csv (project start dates)
Writes data/intermediate/podcasts_wave<N>.csv          one row per subnet
       data/evidence/podcast_episodes_wave<N>.csv      every episode considered, with its matches
"""
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.feeds import parse_rss, youtube_list, youtube_watch  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import archive, read_json, read_table, write_json, write_table  # noqa: E402
from snprice.metrics import spaced_count  # noqa: E402
from snprice.textmatch import Matcher, subnet_entries, valid_for_project  # noqa: E402
from snprice.timeutil import epoch  # noqa: E402

DAY = 86400
YEAR = 365 * DAY
SAME_EPISODE = 14 * DAY
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/126.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
PAUSE = 1.5
WATCH_NEEDS = (re.compile(r'"publishDate":"[^"]+"'), re.compile(r'"externalChannelId":"[^"]+"'))


def get(url, cache):
    """Fetch a page once; later runs read the saved copy."""
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    time.sleep(PAUSE)
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=90) as resp:
        text = resp.read().decode("utf-8", "replace")
    atomic_write(cache, text)
    return text


def video_facts(video_id, cache_dir):
    """Publication time and channel of a video; the page is read only as far as needed."""
    cache = cache_dir / f"{video_id}.json"
    facts = read_json(cache)
    if facts:
        return facts
    time.sleep(PAUSE)
    req = urllib.request.Request(f"https://www.youtube.com/watch?v={video_id}", headers=HEADERS)
    data = b""
    with urllib.request.urlopen(req, timeout=90) as resp:
        while True:
            chunk = resp.read(131072)
            if not chunk:
                break
            data += chunk
            text = data.decode("utf-8", "replace")
            if all(pattern.search(text) for pattern in WATCH_NEEDS):
                break
    facts = youtube_watch(data.decode("utf-8", "replace"))
    write_json(cache, facts)
    return facts


def youtube_episodes(show, raw, oldest):
    """Episodes of a channel, newest first, back to `oldest` (epoch seconds)."""
    out, seen = [], set()
    for prefix, kind in (("UULF", "video"), ("UULV", "live")):
        playlist = prefix + show["channel_id"][2:]
        listed = youtube_list(get(f"https://www.youtube.com/playlist?list={playlist}", raw / f"{playlist}.html"))
        older = 0
        for v in listed:
            if v["video_id"] in seen:
                continue
            facts = video_facts(v["video_id"], raw / "videos")
            if facts["channel_id"] != show["channel_id"]:
                raise SystemExit(f"{show['show']}: video {v['video_id']} belongs to another channel")
            seen.add(v["video_id"])
            if epoch(facts["published"]) < oldest:
                older += 1
                if older >= 3:          # lists run newest first; three older entries in a row end the walk
                    break
                continue
            older = 0
            out.append({"show": show["show"], "episode_id": v["video_id"], "title": v["title"],
                        "published": facts["published"], "kind": kind,
                        "url": f"https://www.youtube.com/watch?v={v['video_id']}"})
        else:
            if len(listed) >= 100:
                raise SystemExit(f"{show['show']}: the {kind} list ends before the window does; older entries are needed")
    return out


def rss_episodes(show, raw, oldest):
    items = parse_rss(get(show["url"], raw / f"{show['show']}.xml"))
    return [{"show": show["show"], "episode_id": e["episode_id"], "title": e["title"], "published": e["published"],
             "kind": "audio", "url": e["url"]} for e in items if epoch(e["published"]) >= oldest]


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    shows = json.loads((paths.CONFIG / "podcasts.json").read_text(encoding="utf-8"))
    t_end = int(archive().timestamp(cfg["t_block"]))
    lag = cfg["lag_days"] * DAY
    oldest = t_end - lag - YEAR
    raw = paths.raw_dir("podcasts")
    (raw / "videos").mkdir(parents=True, exist_ok=True)

    # 1. episode lists
    listed = {}
    for show in shows:
        found = (youtube_episodes if show["source"] == "youtube" else rss_episodes)(show, raw, oldest)
        listed[show["show"]] = [e for e in found if epoch(e["published"]) <= t_end]
        print(f"{show['show']}: {len(listed[show['show']])} episodes between "
              f"{time.strftime('%Y-%m-%d', time.gmtime(oldest))} and T", flush=True)

    # 2. which subnets the titles name
    roster = read_table(paths.CHAIN / f"roster_wave{wave}.csv")
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    start = {int(h["netuid"]): h["project_start_utc"] for h in read_table(paths.INTERMEDIATE / f"history_wave{wave}.csv")}
    matcher = Matcher(subnet_entries(roster, links, read_table(paths.CONFIG / "name_aliases.csv")))
    manual_path = paths.MANUAL / "podcast_weak_matches.csv"
    confirmed = {(m["episode_id"], int(m["netuid"])) for m in (read_table(manual_path) if manual_path.exists() else [])
                 if (m["counts"] or "").strip().lower() == "yes"}

    episodes = []
    for show in shows:
        for e in listed[show["show"]]:
            hits = matcher.find(e["title"], assume_context=show["bittensor_only"])
            hits = {n: h for n, h in hits.items() if valid_for_project(h, e["published"], start.get(n))}
            strong = sorted(n for n, h in hits.items() if h["strength"] == "strong")
            weak = sorted(n for n, h in hits.items() if h["strength"] == "weak")
            e["netuids"] = strong + [n for n in weak if (e["episode_id"], n) in confirmed]
            e["weak_netuids"] = weak
            episodes.append(e)

    appearances = defaultdict(lambda: defaultdict(list))        # netuid -> show -> [epoch]
    for e in episodes:
        for n in e["netuids"]:
            appearances[n][e["show"]].append(epoch(e["published"]))

    def count(n, lo, hi):
        per_show = {s: spaced_count([t for t in times if lo < t <= hi], SAME_EPISODE)
                    for s, times in appearances[n].items()}
        return per_show

    rows = []
    for r in roster:
        n = int(r["netuid"])
        now, before = count(n, t_end - YEAR, t_end), count(n, t_end - lag - YEAR, t_end - lag)
        times = [t for ts in appearances[n].values() for t in ts if t_end - YEAR < t <= t_end]
        row = {"netuid": n,
               "podcast_episodes_12m": sum(now.values()),
               "podcast_shows_12m": sum(1 for v in now.values() if v),
               "podcast_days_since_last": (t_end - max(times)) / DAY if times else None,
               "podcast_episodes_12m_lag30": sum(before.values())}
        for show in shows:
            row[f"podcast_{show['show']}_12m"] = now.get(show["show"], 0)
        rows.append(row)

    write_table(paths.INTERMEDIATE / f"podcasts_wave{wave}.csv", rows)
    episodes.sort(key=lambda e: (e["show"], e["published"]), reverse=True)
    write_table(paths.EVIDENCE / f"podcast_episodes_wave{wave}.csv", [
        {"show": e["show"], "published": e["published"], "kind": e["kind"], "title": e["title"], "url": e["url"],
         "episode_id": e["episode_id"], "netuids": "|".join(map(str, e["netuids"])),
         "weak_netuids": "|".join(map(str, e["weak_netuids"]))} for e in episodes])

    featured = sum(1 for r in rows if r["podcast_episodes_12m"])
    weak = [(e["show"], e["episode_id"], n, e["title"]) for e in episodes for n in e["weak_netuids"]]
    print(f"{len(episodes)} episodes; {sum(1 for e in episodes if e['netuids'])} name at least one subnet; "
          f"{featured} subnets appeared in the 12 months before T")
    print(f"weak matches to review ({len(weak)}; confirmed so far {len(confirmed)}):")
    for show, episode_id, n, title in weak:
        mark = "counted" if (episode_id, n) in confirmed else "not counted"
        print(f"  {show} {episode_id} SN{n} [{mark}]: {title}")


if __name__ == "__main__":
    main()
