"""White papers (Y9): which document to measure, and what can be read off its text."""
import re
from urllib.parse import urlparse

from .webtext import same_site

_PAPER_WORD = re.compile(r"white[\s_\-]?paper|lite[\s_\-]?paper|yellow[\s_\-]?paper", re.I)
_GITHUB_BLOB = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
_REFERENCE_HEADING = re.compile(r"^\s*(?:\d+\.?\s*)?(?:references|bibliography|works cited|literature)\s*$", re.I)
_MATH = re.compile(r"[Α-Ωα-ω∑∏√∫≤≥≠≈∈∀·×]"
                   r"|\w_\{?\w|\^|\\(?:frac|sum|prod)|\b(?:sum|exp|log|argmax|softmax|min|max)\b")
MAX_FORMULA_LINE = 160


def is_pdf(url):
    return urlparse(url or "").path.lower().endswith(".pdf")


def choose_document(named, links):
    """The address of the white paper to measure.

    named  addresses given by the coders (page or file)
    links  (address, label) of the documents linked on the subnet's site

    A PDF is preferred because it has pages to count: one named by a coder, or one on the same
    site that is called a white paper, litepaper or yellow paper. Otherwise the web page.
    """
    named = [u for u in named if u and u.startswith("http")]
    for url in named:
        if is_pdf(url):
            return url
    if not named:
        return None
    for url, label in links:
        if is_pdf(url) and same_site(url, named[0]) and _PAPER_WORD.search(f"{url} {label}"):
            return url
    return named[0]


def raw_github(url):
    """Address of the file itself for a GitHub page that shows a file."""
    m = _GITHUB_BLOB.match(url or "")
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}/{m.group(4)}" if m else url


def has_reference_list(text):
    """A heading "References" or "Bibliography" on a line of its own, past the first 30% of the
    text (a heading at the very start belongs to a table of contents)."""
    offset, floor = 0, 0.3 * len(text or "")
    for line in (text or "").split("\n"):
        if offset >= floor and _REFERENCE_HEADING.match(line):
            return True
        offset += len(line) + 1
    return False


def equation_lines(text, limit=12):
    """Lines that look like formulas: an equals sign together with a mathematical symbol,
    a subscript or a function such as sum or exp. Each distinct line once."""
    out = []
    for line in (text or "").split("\n"):
        line = " ".join(line.split())
        if "=" in line and len(line) <= MAX_FORMULA_LINE and _MATH.search(line) and line not in out:
            out.append(line)
            if len(out) >= limit:
                break
    return out
