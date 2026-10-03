"""White papers (Y9): read the document of every subnet that offers one, and measure it.

Which document: snprice.whitepaper.choose_document (a PDF version where the project offers
one, else the web page the coders named). config/whitepaper_documents.csv corrects the
address where the coders named a page that only lists the paper. If the first address cannot
be read (dead link), the other address named by a coder is tried.

How it is read
  PDF        inside headless Chrome with pdf.js (collect/pdf_text.html). The file is held in
             the browser's memory only; the extracted text is what gets saved.
  web page   rendered with headless Chrome, as in collect/12_web.py; a white paper spread
             over several pages is read page by page (up to 60)
  Markdown   the file as GitHub serves it

Measured by rule
  wp_pages        pages of the PDF (missing for web pages and Markdown)
  wp_references   the document has a heading "References" or "Bibliography"
                  (snprice.whitepaper.has_reference_list)
The two items that need reading, named authors and a formula for the mechanism, are coded
from an excerpt written by this script (first lines, lines that look like formulas).

Writes  data/evidence/whitepapers_wave<N>.csv        one row per subnet with a white paper
        Temp/collection-cache/raw/wave<N>/whitepapers/<netuid>.json   text of the document (not committed)
        Temp/collection-cache/raw/wave<N>/whitepapers/excerpts.txt    excerpts for the coders (not committed)
"""
import hashlib
import html
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.browser import chrome, http_answer, profile_dir, remove_profiles, render  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import read_json, read_table, write_json, write_table  # noqa: E402
from snprice.webtext import MIN_TEXT, page_links, safe_url, same_site, visible_text  # noqa: E402
from snprice.whitepaper import choose_document, equation_lines, has_reference_list, is_pdf, raw_github  # noqa: E402

HELPER = Path(__file__).resolve().parent / "pdf_text.html"
PDF_TIMEOUT = 180
HEAD_CHARS = 1500
FORMULA_LINES = 20
MAX_WEB_PAGES = 60
MIN_WORDS = 150                    # fewer words than this is a login gate or a viewer, not the document
PAPER = re.compile(r"white[\s_\-]?paper|lite[\s_\-]?paper|yellow[\s_\-]?paper|\bpaper\b", re.I)


def pdf_pages(url):
    """Text of every page of a PDF, read in the browser. Returns (pages, error)."""
    page = HELPER.as_uri() + "?url=" + urllib.parse.quote(url, safe="")
    cmd = [chrome(), "--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
           "--mute-audio", "--disable-web-security", "--allow-file-access-from-files",
           f"--user-data-dir={profile_dir()}", "--virtual-time-budget=120000", "--dump-dom", page]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = proc.communicate(timeout=PDF_TIMEOUT)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        return None, "timeout"
    dom = (out or b"").decode("utf-8", "replace")
    status = re.search(r'<div id="status"[^>]*>(.*?)</div>', dom, re.S)
    if not status or status.group(1).strip() != "done":
        return None, html.unescape(status.group(1).strip()) if status else "no answer"
    return [html.unescape(t) for _, t in re.findall(r'<section data-page="(\d+)">(.*?)</section>', dom, re.S)], None


def read_pdf(url):
    pages, problem = pdf_pages(raw_github(url))
    return ("\f".join(pages), None) if pages else (None, problem)


def page_html(url):
    """HTML of a page: as rendered, or as the server sends it if that shows more text
    (some pages crash the headless browser)."""
    rendered = render(url) or ""
    if len(visible_text(rendered)) >= MIN_TEXT:
        return rendered
    static = http_answer(url)[3]
    return static if len(visible_text(static)) > len(visible_text(rendered)) else rendered


def read_web(url):
    """Text of a white paper published as web pages: the page, plus the pages of the same
    document that it links to (their address contains "whitepaper", "litepaper" or "paper").
    Returns (text, number of pages read, PDF version offered on the page or None)."""
    html_text = page_html(url)
    links = page_links(html_text, url)
    for link, label in links:
        if is_pdf(link) and same_site(link, url) and PAPER.search(f"{link} {label}"):
            return None, 0, link
    texts, seen = [visible_text(html_text)], {url.rstrip("/")}
    for link, _ in links:
        key = link.rstrip("/")
        path = urlparse(link).path.lower()
        if key in seen or not same_site(link, url) or not PAPER.search(path) or path.endswith((".md", ".txt", ".pdf")):
            continue
        if len(texts) >= MAX_WEB_PAGES:
            break
        seen.add(key)
        texts.append(visible_text(page_html(link)))
    return "\n\n".join(t for t in texts if t), len(texts), None


def read_document(candidates):
    """Read the first candidate that can be read. Returns a dict with url, format, text, pages."""
    problem = "no usable address"
    for url in candidates:
        if not url or not safe_url(url):
            continue
        if is_pdf(url) or http_answer(url)[2] == "pdf":            # some PDFs are served without ".pdf"
            text, problem = read_pdf(url)
            if text:
                return {"url": url, "format": "pdf", "text": text, "pages": text.count("\f") + 1, "web_pages": None}
            continue
        source = raw_github(url)
        if source != url or url.lower().endswith(".md"):
            text = http_answer(source)[3]
            if text:
                return {"url": url, "format": "markdown", "text": text, "pages": None, "web_pages": 1}
            problem = "file could not be read"
            continue
        text, count, pdf = read_web(url)
        if pdf:
            text, problem = read_pdf(pdf)
            if text:
                return {"url": pdf, "format": "pdf", "text": text, "pages": text.count("\f") + 1, "web_pages": None}
            text, count, _ = read_web_without_pdf(url)
        if text and len(text.split()) >= MIN_WORDS:
            return {"url": url, "format": "html", "text": text, "pages": None, "web_pages": count}
        problem = "page could not be read"
    return {"url": next((u for u in candidates if u), None), "format": None, "text": None, "pages": None,
            "web_pages": None, "problem": problem}


def read_web_without_pdf(url):
    """The web page itself when the PDF it offers cannot be read."""
    return visible_text(page_html(url)), 1, None


def main():
    cfg = paths.snapshot()
    wave = cfg["wave"]
    coded = [r for r in read_table(paths.INTERMEDIATE / f"web_coding_wave{wave}.csv") if r["whitepaper_available"] == "1"]
    coder = {c: {int(x["netuid"]): x for x in read_json(paths.MANUAL / f"web_coding_wave{wave}_coder_{c}.json")} for c in "AB"}
    site_docs = {}
    for d in read_table(paths.EVIDENCE / f"doc_links_wave{wave}.csv"):
        site_docs.setdefault(int(d["netuid"]), []).append((d["url"], d["label"] or ""))
    manual_path = paths.CONFIG / "whitepaper_documents.csv"
    manual = {int(m["netuid"]): m["document_url"] for m in (read_table(manual_path) if manual_path.exists() else [])}
    names = {int(r["netuid"]): r["subnet_name"] for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}
    out_dir = paths.raw_dir("whitepapers")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, excerpts = [], []
    for r in coded:
        n = int(r["netuid"])
        named = [coder[c][n].get("whitepaper_url") for c in "AB"]
        first = manual.get(n) or choose_document(named, site_docs.get(n, []))
        candidates = [first] + [u for u in named if u and u != first and u.startswith("http")]
        cache = out_dir / f"{n}.json"
        doc = read_json(cache)
        if doc is None:
            doc = read_document(candidates)
            if doc["text"]:
                write_json(cache, doc)
        text = doc["text"]
        row = {"netuid": n, "document_url": doc["url"], "format": doc["format"], "wp_pages": doc["pages"],
               "web_pages_read": doc["web_pages"], "wp_references": None, "words": None, "formula_lines": None,
               "sha256": None, "problem": doc.get("problem")}
        if text:
            flat = text.replace("\f", "\n")
            lines = equation_lines(flat, limit=FORMULA_LINES)
            row.update({"wp_references": int(has_reference_list(flat)), "words": len(flat.split()),
                        "formula_lines": len(lines), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
            squeezed = [" ".join(x.split()) for x in flat.split("\n") if x.strip()]
            shown = []
            for line in lines:                       # each formula line with the line before and after it
                i = squeezed.index(line)
                shown.append(" / ".join(squeezed[max(0, i - 1):i + 2]))
            excerpts += [f"=== SUBNET {n}: {names[n]} | {doc['format']} | {doc['url']}",
                         f"--- first {HEAD_CHARS} characters", flat[:HEAD_CHARS],
                         f"--- lines that look like formulas, each with its neighbours (at most {FORMULA_LINES})"]
            excerpts += (shown or ["(none found)"]) + [""]
        rows.append(row)
        print(f"  SN{n} {names[n]}: {row['format']} pages={row['wp_pages']} web pages={row['web_pages_read']} "
              f"words={row['words']} references={row['wp_references']} formula lines={row['formula_lines']} "
              f"{row['problem'] or ''}", flush=True)
    remove_profiles()
    write_table(paths.EVIDENCE / f"whitepapers_wave{wave}.csv", rows)
    atomic_write(out_dir / "excerpts.txt", "\n".join(excerpts) + "\n")
    print(f"{len(rows)} white papers; read {sum(1 for r in rows if r['words'])}; "
          f"not read: {[(r['netuid'], r['problem']) for r in rows if not r['words']]}")


if __name__ == "__main__":
    main()
