"""GitHub REST client (cached, rate-limit aware) and the documentation checklist."""
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .files import atomic_write

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def token_from_environment():
    """GITHUB_TOKEN, or the token of the logged-in GitHub CLI."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def http_transport(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read().decode("utf-8", "replace")


def parse_github_url(url):
    """(owner, repo) of a GitHub URL; repo is None for an owner or organisation page."""
    m = re.match(r"\s*(?:https?://)?(?:www\.)?github\.com/(orgs/)?([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?",
                 url or "", flags=re.I)
    if not m:
        return None, None
    is_org_page, owner, repo = m.group(1), m.group(2), m.group(3)
    if is_org_page or not repo:
        return owner, None
    return owner, re.sub(r"\.git$", "", repo)


class GitHub:
    def __init__(self, token, cache_dir, transport=http_transport, sleep=time.sleep, clock=time.time, tries=4):
        self.token = token
        self.cache_dir = cache_dir
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self.tries = tries
        self.requests = 0
        os.makedirs(cache_dir, exist_ok=True)

    def _fetch(self, url):
        """Return (status, link header, parsed body) for a full URL, cached on disk."""
        cache = os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                rec = json.load(fh)
            return rec["status"], rec.get("link"), rec.get("body")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "snprice",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        problem = None
        for attempt in range(self.tries):
            self.requests += 1
            status, resp_headers, body = self.transport(url, headers)
            if status == 200:
                rec = {"url": url, "status": 200, "link": resp_headers.get("link"), "body": json.loads(body),
                       "fetched_at": int(self.clock())}
                break
            if status in (404, 409, 451):          # missing, empty or blocked repository
                rec = {"url": url, "status": status, "link": None, "body": None, "fetched_at": int(self.clock())}
                break
            problem = f"HTTP {status}: {body[:200]}"
            if status in (403, 429):
                if resp_headers.get("x-ratelimit-remaining") == "0":
                    wait = max(5, int(resp_headers.get("x-ratelimit-reset", "0")) - self.clock() + 5)
                else:
                    wait = int(resp_headers.get("retry-after", "60"))
                self.sleep(wait)
                continue
            self.sleep(5 * (attempt + 1))
        else:
            raise GitHubError(f"{url}: {problem}")
        atomic_write(cache, json.dumps(rec))
        return rec["status"], rec["link"], rec["body"]

    @staticmethod
    def _url(path, params):
        url = path if path.startswith("http") else API + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(sorted(params.items()))
        return url

    def get(self, path, **params):
        """Parsed JSON, or None if the resource does not exist."""
        status, _, body = self._fetch(self._url(path, params))
        return body if status == 200 else None

    def pages(self, path, max_pages=200, **params):
        """All items of a paginated list endpoint; None if the resource does not exist."""
        params.setdefault("per_page", 100)
        url, out = self._url(path, params), []
        for _ in range(max_pages):
            status, link, body = self._fetch(url)
            if status != 200:
                return None if not out else out
            out.extend(body)
            nxt = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
            if not nxt:
                return out
            url = nxt.group(1)
        raise GitHubError(f"{path}: more than {max_pages} pages")

    def count(self, path, **params):
        """Number of items of a list endpoint, read from the pagination header."""
        params["per_page"] = 1
        status, link, body = self._fetch(self._url(path, params))
        if status != 200:
            return None
        last = re.search(r'[?&]page=(\d+)[^>]*>;\s*rel="last"', link or "")
        return int(last.group(1)) if last else len(body)


# ------------------------------------------------------------------ documentation checklist

DOC_ITEMS = ("doc_readme", "doc_license", "doc_contributing", "doc_miner_guide", "doc_validator_guide",
             "doc_incentive_desc", "doc_requirements", "doc_site")
MIN_README_CHARS = 500
_DOC_FILE = r"\.(md|mdx|rst|txt|ipynb)$"
_HEADING = {
    "doc_miner_guide": r"\b(miner|miners|mining)\b",
    "doc_validator_guide": r"\b(validator|validators|validating|validation)\b",
    "doc_incentive_desc": r"\b(incentive|incentives|scoring|reward|rewards|mechanism)\b",
    "doc_requirements": r"\b(requirement|requirements|hardware|prerequisite|prerequisites|specs?|specifications?)\b",
}
_PATH = {
    "doc_miner_guide": r"(miner|mining)[^/]*" + _DOC_FILE,
    "doc_validator_guide": r"validat[^/]*" + _DOC_FILE,
    "doc_incentive_desc": r"(incentive|scoring|reward|mechanism)[^/]*" + _DOC_FILE,
    "doc_requirements": r"(^|/)min_compute\.ya?ml$|(hardware|requirements?|prerequisites?)[^/]*\.(md|mdx|rst)$",
}
_DOC_SITE = re.compile(
    r"https?://(?!github\.com)(?:docs\.[^\s)\"'<>]+|[^\s)\"'<>/]*(?:gitbook\.io|readthedocs\.io|mintlify\.app)[^\s)\"'<>]*"
    r"|[^\s)\"'<>]+/docs(?:/[^\s)\"'<>]*)?)", re.I)


def doc_checklist(profile, readme, tree_paths, website_text, homepage):
    """Eight yes/no documentation items from fixed rules; all None when there is no repository.

    profile     GitHub community profile of the repository
    readme      README text
    tree_paths  file paths in the default branch
    homepage    the repository's homepage field and/or the subnet website URL

    A miner or validator guide, an incentive description and hardware requirements
    count only when they appear as a README heading or as a documentation file,
    not when the word merely occurs in running text.
    """
    if profile is None and readme is None and tree_paths is None:
        return {**{k: None for k in DOC_ITEMS}, "doc_score": None, "evidence": {}}
    files = (profile or {}).get("files") or {}
    readme = readme or ""
    paths = tree_paths or []
    headings = [re.sub(r"^#+\s*", "", line).strip() for line in readme.splitlines() if re.match(r"^#{1,6}\s", line)]
    out, evidence = {}, {}

    out["doc_readme"] = int(bool(files.get("readme")) and len(readme) >= MIN_README_CHARS)
    out["doc_license"] = int(bool(files.get("license")))
    out["doc_contributing"] = int(bool(files.get("contributing")))
    for item in ("doc_miner_guide", "doc_validator_guide", "doc_incentive_desc", "doc_requirements"):
        hit = next((h for h in headings if re.search(_HEADING[item], h, re.I)), None)
        if hit is None:
            hit = next((p for p in paths if re.search(_PATH[item], p, re.I)), None)
        out[item] = int(hit is not None)
        if hit is not None:
            evidence[item] = hit
    site = _DOC_SITE.search(homepage or "") or _DOC_SITE.search(readme) or _DOC_SITE.search(website_text or "")
    out["doc_site"] = int(site is not None)
    if site:
        evidence["doc_site"] = site.group(0)
    out["doc_score"] = sum(out[k] for k in DOC_ITEMS)
    out["evidence"] = evidence
    return out
