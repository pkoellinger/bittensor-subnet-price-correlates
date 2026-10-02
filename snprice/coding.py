"""Double coding of facts read off subnet websites (config/coding_protocol.md):
checking evidence quotes, measuring agreement, settling disagreements."""
import re
from collections import Counter

ITEMS = ("whitepaper_available", "api_public", "mcp_server", "team_named", "product_live", "category")
MAX_QUOTE = 200


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")


def without_mailboxes(text):
    """The text with e-mail addresses reduced to "@domain": mailbox names are not republished."""
    return None if text is None else _EMAIL.sub(lambda m: "@" + m.group(1), text)


def _squash(text):
    return re.sub(r"\s+", " ", without_mailboxes(text or "")).strip()


def quote_found(quote, text):
    """The quote appears in the text, character for character apart from white space.

    E-mail addresses are compared by their domain only, so that a stored quote does not
    have to carry the mailbox name.
    """
    quote = _squash(quote)
    return bool(quote) and quote in _squash(text)


def _address(url):
    return (url or "").strip().rstrip("/")


def check_answer(answer, sources):
    """Check the evidence of one coded item against the saved material.

    answer   {"value": 0 | 1 | category name, "url": ..., "quote": ...}
    sources  {page address | "README" | "onchain": full text}

    Returns "verified" or the reason the evidence fails. A 0 needs no evidence.
    """
    if answer.get("value") in (0, "0", None):
        return "verified"
    url, quote = answer.get("url"), answer.get("quote")
    if not url or not quote:
        return "no evidence given"
    if len(_squash(quote)) > MAX_QUOTE:
        return "quote too long"
    pages = {_address(k): v for k, v in sources.items()}
    if _address(url) not in pages:
        return "page not in the dossier"
    return "verified" if quote_found(quote, pages[_address(url)]) else "quote not on the cited page"


def _word_list(text):
    return re.findall(r"[^\W_]+", (text or "").lower())


def copies_passage(reason, text, words=6):
    """Whether `reason` repeats `words` or more words in a row from `text`.

    Case, spacing and punctuation are ignored. A reader's reason for a decision about a
    post is committed, the post's text is not, so a reason has to be in the reader's own words.
    """
    said, source = _word_list(reason), " " + " ".join(_word_list(text)) + " "
    return any(" " + " ".join(said[i:i + words]) + " " in source for i in range(len(said) - words + 1))


def cohen_kappa(a, b):
    """Cohen's kappa of two coders' answers to the same cases; None if nothing varies."""
    if len(a) != len(b):
        raise ValueError("the two coders answered different numbers of cases")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def settle(value_a, check_a, value_b, check_b, third):
    """Final value of one item and how it was reached.

    Agreement of two verified answers stands. Anything else needs the third reading, which
    gives a value or "NA" (the evidence does not settle it). Without it the item is open.
    """
    if value_a == value_b and check_a == "verified" and check_b == "verified":
        return value_a, "both coders"
    if third is None:
        return None, "open"
    if third == "NA":
        return None, "third reading: not settled"
    return third, "third reading"
