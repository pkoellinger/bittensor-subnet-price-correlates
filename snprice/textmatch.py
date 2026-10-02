"""Find mentions of subnets in free text (posts, episode titles, transcripts).

Evidence, from strongest to weakest:
  id       "SN64", "subnet 64", "netuid 64"
  handle   "@chutes_ai" (ignored when several subnets share the handle)
  name     the subnet's name or an alias, as a whole word

How a name is treated depends on the subnet's rule in config/name_aliases.csv:
  plain        distinctive name: a match is enough
  context      needs a Bittensor term in the same text ("iota")
  strict       ordinary English word ("Claims", "Score"): strong only next to
               the word "subnet" or together with the subnet's id or handle;
               an exact-case match with Bittensor context is a WEAK candidate
               that a human coder must confirm
  placeholder  "Unknown", "Parked", "for sale": never matched by name
"""
import re

_ID = re.compile(r"(?<![A-Za-z0-9])(?:sn|subnet|netuid)[\s\-_#]{0,3}(\d{1,3})(?![0-9])", re.I)
_CONTEXT = re.compile(
    r"bittensor|opentensor|dtao|subnet|(?<![A-Za-z0-9])\$?tao(?![A-Za-z])|(?<![A-Za-z0-9])sn[\s\-]?\d", re.I)
RULES = ("plain", "context", "strict", "placeholder")


def _word(text, flags=0):
    # "_" and a leading "@" count as part of a word, so a name inside somebody
    # else's handle ("@chutes_ai_fan") is not a mention of the subnet
    return re.compile(r"(?<![A-Za-z0-9_@])" + re.escape(text) + r"(?![A-Za-z0-9_])", flags)


class Matcher:
    def __init__(self, subnets):
        """subnets: dicts with netuid, name, handles, aliases, rule."""
        self.netuids = set()
        self.names = []       # (netuid, rule, case-insensitive pattern, exact-case pattern, adjacency pattern)
        handle_owners = {}
        for s in subnets:
            rule = s.get("rule", "plain")
            if rule not in RULES:
                raise ValueError(f"netuid {s['netuid']}: unknown rule {rule!r}")
            n = int(s["netuid"])
            self.netuids.add(n)
            for h in s.get("handles") or []:
                h = h.lstrip("@").lower()
                if h:
                    handle_owners.setdefault(h, set()).add(n)
            if rule == "placeholder":
                continue
            for label in [s.get("name")] + list(s.get("aliases") or []):
                label = (label or "").strip()
                if not label:
                    continue
                near = re.compile(
                    r"(?<![A-Za-z0-9])(?:" + re.escape(label) + r"\s+subnet|subnet\s+" + re.escape(label)
                    + r")(?![A-Za-z0-9])", re.I)
                self.names.append((n, rule, _word(label, re.I), _word(label), near))
        self.handles = [
            (next(iter(owners)), re.compile(r"(?<![A-Za-z0-9_])@" + re.escape(h) + r"(?![A-Za-z0-9_])", re.I))
            for h, owners in handle_owners.items() if len(owners) == 1
        ]

    def find(self, text, assume_context=False):
        """Return {netuid: {"strength": "strong" | "weak", "rules": [...]}}.

        assume_context: the source itself is about Bittensor (a Bittensor podcast,
        a summit talk), so "context" names need no further term in the text.
        """
        if not text:
            return {}
        strong, weak = {}, {}
        for m in _ID.finditer(text):
            n = int(m.group(1))
            if n in self.netuids:
                strong.setdefault(n, set()).add("id")
        for n, pattern in self.handles:
            if pattern.search(text):
                strong.setdefault(n, set()).add("handle")
        has_context = assume_context or bool(_CONTEXT.search(text))
        for n, rule, loose, exact, near in self.names:
            if rule == "plain":
                if loose.search(text):
                    strong.setdefault(n, set()).add("name")
            elif rule == "context":
                if has_context and loose.search(text):
                    strong.setdefault(n, set()).add("name")
            elif rule == "strict":
                if near.search(text):
                    strong.setdefault(n, set()).add("name")
                elif exact.search(text):
                    if n in strong:
                        strong[n].add("name")
                    elif has_context:
                        weak.setdefault(n, set()).add("name")
        # a strict name that was seen before its id/handle evidence was collected
        for n in list(weak):
            if n in strong:
                strong[n] |= weak.pop(n)
        out = {n: {"strength": "strong", "rules": sorted(r)} for n, r in strong.items()}
        out.update({n: {"strength": "weak", "rules": sorted(r)} for n, r in weak.items()})
        return out


def valid_for_project(hit, when, project_start):
    """Netuids are reused. A mention by number alone, dated before the current
    project started, refers to the previous occupant and does not count."""
    if not project_start:
        return True
    if set(hit["rules"]) <= {"id"} and str(when)[:10] < str(project_start)[:10]:
        return False
    return True
