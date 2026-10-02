"""Websites: is the site there (Y7), and text snapshots of the pages the coding step reads.

For every subnet with a website (data/evidence/links_wave<N>.csv) the home page and up to
eight further pages of the same site are rendered with headless Chrome and saved as plain
text. Pages are picked by topic from the links on the home page: white paper, docs, API,
team, product (snprice/webtext.py). Links to documents (PDF files, paper archives) are
listed, not fetched.

website_status (snprice.webtext.site_status)
  live          the home page has at least 200 characters of text (as rendered by the browser,
                or, where the browser fails on a page, in the HTML the server sends)
  live_no_text  the server answers with HTTP 200 but the page shows almost no text
  parked        domain-parking page
  blocked       the site asks visitors to prove they are human
  replaced_by_security_software
                the browser or the security software on the collecting computer showed a
                certificate or phishing warning instead of the site; the warning is not overridden
  dead          no answer, an error status (402, 404, 410, 500 and up), or an error page
  not_listed    no website found for the subnet
website_live = 1 for live and live_no_text; missing for blocked and replaced_by_security_software,
where the site could not be judged; 0 otherwise. A site that answered with a server error is
visited once more later the same day before it counts as dead.

Website addresses come from free-text fields written by subnet owners, so each address is
validated before it is passed to the browser (snprice.webtext.safe_url), and Chrome runs
with an empty throw-away profile.

Writes  data/intermediate/web_wave<N>.csv        one row per subnet
        data/evidence/web_pages_wave<N>.csv      every page read: address, topic, size, hash, time
        data/evidence/doc_links_wave<N>.csv      links to documents found on those pages
        data/raw/wave<N>/web/<netuid>/           page texts (not committed)
"""
import hashlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.browser import chrome, http_answer, remove_profiles, render  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import read_json, read_table, write_json, write_table  # noqa: E402
from snprice.timeutil import iso  # noqa: E402
from snprice.webtext import (MIN_TEXT, TOPICS, doc_links, page_links, pick_pages, safe_url, site_status,  # noqa: E402
                             visible_text)

MAX_PAGES = 8
WORKERS = 4
_lock = threading.Lock()


def topic_of(url, text=""):
    where = f"{text} {urlparse(url).hostname or ''} {urlparse(url).path}"
    return next((name for name, pattern in TOPICS if pattern.search(where)), "other")


def read_site(netuid, listed_url, out_dir):
    done = read_json(out_dir / "pages.json")
    if done is not None:
        return done
    home = safe_url(listed_url)
    if not home:
        result = {"status": "dead", "http_status": None, "error": "not a web address", "pages": [], "documents": []}
        write_json(out_dir / "pages.json", result)
        return result
    code, final, error, home_html = http_answer(home)
    base = safe_url(final) or home
    pages, documents, seen_docs = [], [], set()

    def read_page(index, url, topic, static_html=None):
        html = render(url)
        text = visible_text(html) if html else ""
        how = "browser"
        if len(text) < MIN_TEXT:
            # the browser gave up (some sites crash it); read the HTML as the server sends it
            if static_html is None:
                static_html = http_answer(url)[3]
            if len(visible_text(static_html)) > len(text):
                html, text, how = static_html, visible_text(static_html), "static"
        links = page_links(html, url) if html else []
        atomic_write(out_dir / f"{index:02d}.txt", text)
        pages.append({"page": index, "url": url, "topic": topic, "how": how, "chars": len(text),
                      "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "fetched_utc": iso(time.time())})
        for doc_url, label in doc_links(links):
            if doc_url not in seen_docs:
                seen_docs.add(doc_url)
                documents.append({"url": doc_url, "label": label, "found_on": url})
        return text, links

    text, links = read_page(0, base, "home", static_html=home_html)
    status = site_status(text, code)
    if status in ("live", "live_no_text"):
        anchor = {u: t for u, t in reversed(links)}
        for i, url in enumerate(pick_pages(links, base, MAX_PAGES), 1):
            if safe_url(url):
                read_page(i, url, topic_of(url, anchor.get(url, "")))
    result = {"status": status, "http_status": code, "error": error, "pages": pages, "documents": documents}
    write_json(out_dir / "pages.json", result)
    return result


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    links = read_table(paths.EVIDENCE / f"links_wave{wave}.csv")
    raw = paths.raw_dir("web")
    chrome()
    todo = [l for l in links if l["website_url"]]
    only = {int(a) for a in sys.argv[1:]}          # trial run: python collect/12_web.py 3 64 111
    if only:
        todo = [l for l in todo if int(l["netuid"]) in only]
    print(f"{len(todo)} subnets with a website; rendering with {WORKERS} browsers", flush=True)

    results = {}

    def work(link):
        n = int(link["netuid"])
        out_dir = raw / str(n)
        out_dir.mkdir(parents=True, exist_ok=True)
        results[n] = read_site(n, link["website_url"], out_dir)
        with _lock:
            done = len(results)
            if done % 10 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)} sites read", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, todo))

    remove_profiles()
    if only:
        for n, r in sorted(results.items()):
            print(n, r["status"], r["http_status"], r["error"], [(p["topic"], p["chars"], p["url"]) for p in r["pages"]],
                  "documents:", [d["url"] for d in r["documents"]])
        return

    rows, page_rows, doc_rows = [], [], []
    for link in links:
        n = int(link["netuid"])
        r = results.get(n)
        status = "not_listed"
        if r:      # the status is worked out again from the saved page, so a changed rule needs no new visit
            home = raw / str(n) / "00.txt"
            status = site_status(home.read_text(encoding="utf-8") if home.exists() else "", r["http_status"])                 if r["pages"] else r["status"]
        rows.append({
            "netuid": n,
            "website_url": link["website_url"],
            "website_status": status,
            "website_live": (None if status in ("blocked", "replaced_by_security_software")
                             else int(status in ("live", "live_no_text"))),
            "website_http_status": r["http_status"] if r else None,
            "website_chars": r["pages"][0]["chars"] if r and r["pages"] else None,
            "website_pages_read": len(r["pages"]) if r else 0,
            "website_doc_links": len(r["documents"]) if r else 0,
        })
        for p in (r["pages"] if r else []):
            page_rows.append({"netuid": n, **p})
        for d in (r["documents"] if r else []):
            doc_rows.append({"netuid": n, **d})
    write_table(paths.INTERMEDIATE / f"web_wave{wave}.csv", rows)
    write_table(paths.EVIDENCE / f"web_pages_wave{wave}.csv", page_rows)
    write_table(paths.EVIDENCE / f"doc_links_wave{wave}.csv", doc_rows)
    counts = {}
    for r in rows:
        counts[r["website_status"]] = counts.get(r["website_status"], 0) + 1
    print(f"website status: {counts}; pages read: {len(page_rows)}; document links: {len(doc_rows)}")
    print("blocked (check by hand):", [r["netuid"] for r in rows if r["website_status"] == "blocked"])


if __name__ == "__main__":
    main()
