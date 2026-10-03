"""Read a web page the way a visitor sees it: visible text, links, and which links to follow.

Used for the website snapshots that the coding step (white paper, API, MCP server,
named team, live product, category) reads. Standard library only.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

_HIDDEN = {"script", "style", "noscript", "svg", "template", "iframe", "canvas"}
_BLOCK = {"address", "article", "aside", "blockquote", "br", "button", "dd", "details", "div", "dl", "dt",
          "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
          "main", "nav", "ol", "option", "p", "pre", "section", "summary", "table", "td", "th", "title", "tr", "ul"}
_SPACE = re.compile(r"[ \t\r\f\v\xa0​]+")

# hosts on which every subdomain (or path) is somebody else's site
SHARED_HOSTS = ("github.io", "gitbook.io", "notion.site", "vercel.app", "netlify.app", "webflow.io",
                "framer.website", "framer.app", "pages.dev", "web.app", "readme.io", "mintlify.app",
                "readthedocs.io", "substack.com", "medium.com", "carrd.co", "wixsite.com", "super.site",
                "herokuapp.com", "onrender.com", "streamlit.app", "hf.space",
                # object storage: a page kept there belongs to whoever uploaded it
                "amazonaws.com", "storage.googleapis.com", "ipfs.io", "us-east-1.hippius.com")
_TWO_PART_SUFFIXES = ("co.uk", "com.au", "co.jp", "com.br", "co.in", "com.sg", "co.kr")
# documentation hosts that a project links to instead of hosting its docs itself
DOC_HOSTS = ("gitbook.io", "gitbook.com", "notion.site", "readme.io", "mintlify.app", "readthedocs.io", "github.io")
_FILE = re.compile(r"\.(pdf|zip|gz|tar|png|jpe?g|gif|svg|webp|mp4|webm|mov|mp3|dmg|exe|apk|csv|json|xml|pptx?|docx?)$", re.I)

# topics a page can be about, in the order in which pages are picked
TOPICS = (
    ("paper", re.compile(r"white[\s\-]?paper|lite[\s\-]?paper|yellow[\s\-]?paper|\bpapers?\b|\bresearch\b", re.I)),
    ("docs", re.compile(r"\bdocs?\b|documentation|\bdevelopers?\b|\bguides?\b|getting[\s\-]?started|\blearn\b", re.I)),
    ("api", re.compile(r"\bapi\b|\bsdk\b|\bmcp\b", re.I)),
    ("team", re.compile(r"\bteam\b|\babout\b|\bcompany\b|who[\s\-]we[\s\-]are", re.I)),
    ("product", re.compile(r"\bapp\b|\bproducts?\b|\bpricing\b|\bplatform\b|playground|\bdashboard\b|\blaunch\b|"
                           r"get[\s\-]?started|sign[\s\-]?up|log[\s\-]?in", re.I)),
)
_DOCUMENT = re.compile(r"white[\s\-]?paper|lite[\s\-]?paper|yellow[\s\-]?paper|technical[\s\-]paper", re.I)
_PAPER_HOSTS = ("arxiv.org", "openreview.net", "ssrn.com", "zenodo.org", "researchgate.net", "biorxiv.org")
_PARKED = re.compile(
    r"buy this domain|parked free|sedoparking|hugedomains|\bdomain\b.{0,40}\b(?:for sale|parked)\b|"
    r"\bis for sale\b.{0,40}\bdomain\b", re.I | re.S)


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title, self.links = [], [], []
        self._hidden = 0
        self._in_title = False
        self._href, self._anchor = None, []

    def handle_starttag(self, tag, attrs):
        if tag in _HIDDEN:
            self._hidden += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "a":
            self._href, self._anchor = dict(attrs).get("href"), []
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _HIDDEN:
            self._hidden = max(0, self._hidden - 1)
            return
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, _SPACE.sub(" ", " ".join("".join(self._anchor).split())).strip()))
            self._href = None
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._hidden:
            return
        if self._in_title:
            self.title.append(data)
            return
        self.parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def _read(html):
    reader = _Reader()
    reader.feed(html or "")
    reader.close()
    return reader


def _lines(text):
    out = []
    for line in text.split("\n"):
        line = _SPACE.sub(" ", line).strip()
        if line:
            out.append(line)
    return out


def visible_text(html):
    """Title, then the text a visitor sees, one block per line."""
    reader = _read(html)
    return "\n".join(_lines("".join(reader.title)) + _lines("".join(reader.parts)))


def page_links(html, base_url):
    """(absolute URL without fragment, anchor text) for every http(s) link, in page order."""
    out, seen = [], set()
    for href, text in _read(html).links:
        href = (href or "").strip()
        if not href or href.startswith("#"):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        if urlparse(url).scheme not in ("http", "https") or (url, text) in seen:
            continue
        seen.add((url, text))
        out.append((url, text))
    return out


def site_of(url):
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if any(host == h or host.endswith("." + h) for h in SHARED_HOSTS):
        return host
    labels = host.split(".")
    keep = 3 if ".".join(labels[-2:]) in _TWO_PART_SUFFIXES else 2
    return ".".join(labels[-keep:])


def same_site(url, home_url):
    return site_of(url) == site_of(home_url)


def _key(url):
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return (host[4:] if host.startswith("www.") else host) + p.path.rstrip("/") + ("?" + p.query if p.query else "")


def _topic(url, text):
    path = urlparse(url)
    where = f"{text} {path.hostname or ''} {path.path}"
    for i, (_, pattern) in enumerate(TOPICS):
        if pattern.search(where):
            return i
    return None


def pick_pages(links, home_url, limit):
    """Pages worth reading besides the home page: on the same site (or a linked documentation
    host), about one of TOPICS, most relevant topic first, at most `limit`."""
    seen = {_key(home_url)}
    ranked = []
    for order, (url, text) in enumerate(links):
        if _FILE.search(urlparse(url).path) or _key(url) in seen:
            continue
        topic = _topic(url, text)
        if topic is None:
            continue
        host = (urlparse(url).hostname or "").lower()
        external_docs = topic <= 2 and any(host == h or host.endswith("." + h) for h in DOC_HOSTS)
        if not (same_site(url, home_url) or external_docs):
            continue
        seen.add(_key(url))
        ranked.append((topic, order, url))
    return [url for _, _, url in sorted(ranked)[:limit]]


def doc_links(links):
    """Links that point to a document: PDF files, paper archives, anything called a white paper."""
    out, seen = [], set()
    for url, text in links:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if url in seen:
            continue
        if (p.path.lower().endswith(".pdf") or any(host == h or host.endswith("." + h) for h in _PAPER_HOSTS)
                or _DOCUMENT.search(f"{text} {p.path}")):
            seen.add(url)
            out.append((url, text))
    return out


def is_parked(text):
    """A domain-parking page instead of a real site."""
    return bool(_PARKED.search(text or ""))


def windows(text, pattern, radius=250, limit=6):
    """Stretches of text around each match of `pattern`, overlapping stretches merged."""
    spans = []
    for m in re.finditer(pattern, text or "", re.I):
        lo, hi = max(0, m.start() - radius), min(len(text), m.end() + radius)
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    return [text[lo:hi].strip() for lo, hi in spans[:limit]]


_HOSTNAME = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_BLOCKED = re.compile(r"just a moment|verif(?:y|ying) you are human|checking your browser|attention required|"
                      r"access denied|enable javascript and cookies to continue|are you a robot", re.I)


def safe_url(text):
    """A public http(s) address, or None.

    Website fields on chain are free text written by subnet owners. Before such text is
    handed to a browser it must be a plain web address: no command-line switch, no file or
    script scheme, no local or private host.
    """
    url = (text or "").strip()
    if not url or url.startswith("-") or any(c.isspace() for c in url):
        return None
    if "://" not in url:
        if ":" in url.split("/")[0]:
            return None                    # "javascript:...", "host:port" without a scheme
        url = "https://" + url
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not _HOSTNAME.match(host):
        return None                        # also refuses IP addresses and "localhost"
    if host.endswith((".local", ".localhost", ".internal", ".lan", ".test")):
        return None
    return url


def is_blocked(text):
    """A short page that only asks the visitor to prove they are human, or denies access."""
    return len(text or "") < 1500 and bool(_BLOCKED.search(text or ""))


_SECURITY_WARNING = re.compile(r"web protection by bitdefender|blocked for your protection|"
                               r"your connection is not private|net::err_cert", re.I)
MIN_TEXT = 200                                   # characters of text that make a page a real page
_DEAD_CODES = {402, 404, 410}                    # hosting paused, page gone
_BOT_CODES = {401, 403, 429}                     # scripts are refused, a browser may still get the site
# statuses that say the site could not be read on the day: nothing follows about what it offers
UNREAD = ("blocked", "replaced_by_security_software", "server_error")


def is_security_warning(text):
    """The page was replaced by a warning of the browser or of security software on this computer
    (bad certificate, suspected phishing). The site's own content was never shown."""
    return bool(_SECURITY_WARNING.search(text or ""))


def site_status(text, http_code):
    """Status of a website from the text of its home page and the answer to a plain request.

    live                            at least MIN_TEXT characters of the site's own text
    live_no_text                    the server answers 200 but the page shows almost no text
    parked                          domain-parking page
    blocked                         the site asks visitors to prove they are human
    replaced_by_security_software   a certificate or phishing warning was shown instead of the site
    server_error                    the server failed on the day (HTTP 500 and up); the site may work on other days
    dead                            no answer, hosting paused, page gone, or an error page
    """
    text = text or ""
    if is_security_warning(text):
        return "replaced_by_security_software"
    if is_parked(text):
        return "parked"
    if is_blocked(text):
        return "blocked"
    if http_code is not None and http_code >= 500:
        return "server_error"
    if http_code in _DEAD_CODES:
        return "dead"
    if len(text) >= MIN_TEXT:
        return "live"
    return "live_no_text" if http_code == 200 else "dead"


_X_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com"}
_X_NOT_A_PROFILE = {"intent", "share", "home", "search", "hashtag", "i", "explore", "settings", "login", "signup",
                    "compose", "messages", "notifications", "tos", "privacy"}
_X_NETWORK_ACCOUNTS = {"opentensor", "bittensor_", "bittensor", "taostats"}      # linked by many subnet sites


def x_profiles(links):
    """Handles of the X profiles a page links to, in page order, each once.

    Only bare profile addresses count (x.com/<handle>): share buttons, single posts and X's own
    pages are skipped, and so are the accounts of the network itself.
    """
    out, seen = [], set()
    for url, _ in links:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        parts = [x for x in p.path.split("/") if x]
        if host not in _X_HOSTS or len(parts) != 1:
            continue
        handle = parts[0].lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            continue
        key = handle.lower()
        if key in _X_NOT_A_PROFILE or key in _X_NETWORK_ACCOUNTS or key in seen:
            continue
        seen.add(key)
        out.append(handle)
    return out
