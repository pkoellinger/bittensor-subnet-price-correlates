"""Find mentions of subnets in free text (posts, episode titles, transcripts).

Evidence, from strongest to weakest:
  id       "SN64", "subnet 64", "netuid 64"
  handle   "@chutes_ai" (ignored when several subnets share the handle)
  name     the subnet's name or an alias, as a whole word

Aliases listed in config/name_aliases.csv are distinctive forms ("DeSci Claims",
"Beam Network") and always count. How the NAME itself is treated depends on the
subnet's rule in that file:
  plain        distinctive name: a match is enough
  context      needs a Bittensor term in the same text ("iota")
  strict       ordinary English word ("Claims", "Score"): strong only next to
               the word "subnet" ("the Claims subnet", exact case), followed by its
               own number ("SOMA 114"), or together with the subnet's id or handle;
               an exact-case match with Bittensor context is a WEAK candidate
               that a human coder must confirm
  placeholder  "Unknown", "Parked", "for sale": never matched by name
"""
import re

_ID = re.compile(r"(?<![A-Za-z0-9])(?:sn|subnet|netuid)[\s\-_#]{0,3}(\d{1,3})(?![0-9])", re.I)
_CONTEXT = re.compile(
    r"bittensor|opentensor|dtao|subnet|(?<![A-Za-z0-9])\$?tao(?![A-Za-z])|(?<![A-Za-z0-9])sn[\s\-]?\d", re.I)
RULES = ("plain", "context", "strict", "placeholder")

# numbers written as words, as speech recognition produces them ("subnet forty-four")
_UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_NUMBER_WORDS = "|".join(list(_UNITS) + list(_TEENS) + list(_TENS) + ["hundred", "and"])
_SPOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:subnet|netuid)\s+(number\s+)?((?:(?:" + _NUMBER_WORDS + r")(?![A-Za-z])[\s\-]*)+)([A-Za-z]*)",
    re.I)
# a number followed by one of these is a quantity ("the subnet four months"), not a subnet number
_QUANTITY = {"month", "months", "year", "years", "week", "weeks", "day", "days", "hour", "hours", "minute",
             "minutes", "second", "seconds", "time", "times", "percent", "thousand", "million", "billion", "of"}


def _below_hundred(words):
    if len(words) == 1:
        w = words[0]
        if w in _TEENS:
            return _TEENS[w]
        if w in _TENS:
            return _TENS[w]
        return _UNITS[w] if w in _UNITS and w != "oh" else None
    if len(words) == 2 and words[0] in _TENS and _UNITS.get(words[1], 0) > 0:
        return _TENS[words[0]] + _UNITS[words[1]]
    return None


def _spoken_value(words):
    if not words:
        return None
    if "hundred" in words:
        i = words.index("hundred")
        if i != 1 or _UNITS.get(words[0], 0) == 0:
            return None
        rest = [w for w in words[2:] if w != "and"]
        low = _below_hundred(rest) if rest else 0
        return None if low is None else 100 * _UNITS[words[0]] + low
    if "and" in words:
        return None
    if len(words) in (2, 3) and all(w in _UNITS for w in words) and _UNITS[words[0]] > 0:
        return int("".join(str(_UNITS[w]) for w in words))          # "one one two", "one oh five"
    value = _below_hundred(words)
    if value is None and words[0] == "one":                         # "one eleven", "one twenty-four"
        low = _below_hundred(words[1:])
        if low is not None and low >= 10:
            value = 100 + low
    return value


def spoken_ids(text):
    """Subnet numbers written as words after "subnet" or "netuid", in order of appearance."""
    out = []
    for m in _SPOKEN.finditer(text or ""):
        words = re.split(r"[\s\-]+", m.group(2).strip().lower())
        while words and words[-1] == "and":      # "subnet eighty and we see"
            words.pop()
        value = _spoken_value(words)
        if value is None or m.group(3).lower() in _QUANTITY:
            continue
        if m.group(1) and value == 1:            # "the subnet number one" is a rank
            continue
        out.append(value)
    return out


def _word(text, flags=0):
    # "_" and a leading "@" count as part of a word, so a name inside somebody
    # else's handle ("@chutes_ai_fan") is not a mention of the subnet
    return re.compile(r"(?<![A-Za-z0-9_@])" + re.escape(text) + r"(?![A-Za-z0-9_])", flags)


class Matcher:
    def __init__(self, subnets):
        """subnets: dicts with netuid, name, handles, aliases, rule."""
        self.netuids = set()
        self.names = []       # (netuid, rule, case-insensitive, exact-case, next-to-"subnet", with-own-number)
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
            # the name follows the subnet's rule; aliases are distinctive forms and always plain
            labels = [(s.get("name"), rule)] + [(a, "plain") for a in (s.get("aliases") or [])]
            for label, label_rule in labels:
                label = (label or "").strip()
                if not label:
                    continue
                # the label in its exact case: "the Actual subnet" counts, "the actual subnet" does not
                near = re.compile(
                    r"(?<![A-Za-z0-9])(?:" + re.escape(label) + r"\s+(?i:subnet)|(?i:subnet)\s+" + re.escape(label)
                    + r")(?![A-Za-z0-9])")
                # the label in its exact case followed by the subnet's own number: "SOMA 114"
                own = re.compile(r"(?<![A-Za-z0-9_@])" + re.escape(label) + r"[\s,:]{1,3}#?" + str(n) + r"(?![0-9A-Za-z])")
                self.names.append((n, label_rule, _word(label, re.I), _word(label), near, own))
        self.handles = [
            (next(iter(owners)), re.compile(r"(?<![A-Za-z0-9_])@" + re.escape(h) + r"(?![A-Za-z0-9_])", re.I))
            for h, owners in handle_owners.items() if len(owners) == 1
        ]

    def find(self, text, assume_context=False, spoken_numbers=False):
        """Return {netuid: {"strength": "strong" | "weak", "rules": [...]}}.

        assume_context: the source itself is about Bittensor (a Bittensor podcast,
        a summit talk), so "context" names need no further term in the text.
        spoken_numbers: the text is a speech transcript, so "subnet forty-four"
        counts as an id (rule "id_spoken").
        """
        if not text:
            return {}
        strong, weak = {}, {}
        for m in _ID.finditer(text):
            n = int(m.group(1))
            if n in self.netuids:
                strong.setdefault(n, set()).add("id")
        if spoken_numbers:
            for n in spoken_ids(text):
                if n in self.netuids:
                    strong.setdefault(n, set()).add("id_spoken")
        for n, pattern in self.handles:
            if pattern.search(text):
                strong.setdefault(n, set()).add("handle")
        has_context = assume_context or bool(_CONTEXT.search(text))
        for n, rule, loose, exact, near, own in self.names:
            if rule == "plain":
                if loose.search(text):
                    strong.setdefault(n, set()).add("name")
            elif rule == "context":
                if has_context and loose.search(text):
                    strong.setdefault(n, set()).add("name")
            elif rule == "strict":
                if own.search(text):
                    strong.setdefault(n, set()).update({"name", "id"})
                elif near.search(text):
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


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def subnet_entries(roster, links, alias_rows):
    """Matcher input per subnet: on-chain name, X handle (links) and the hand-kept alias table."""
    handle = {int(l["netuid"]): l.get("x_handle") for l in links}
    alias = {int(a["netuid"]): a for a in alias_rows}
    out = []
    for r in roster:
        n = int(r["netuid"])
        a = alias[n]                      # every subnet must have a row in the alias table
        split = lambda s: [x.strip() for x in (s or "").split("|") if x.strip()]  # noqa: E731
        out.append({
            "netuid": n,
            "name": (r.get("subnet_name") or "").strip(),
            "rule": a["rule"],
            "handles": [handle[n]] if handle.get(n) else [],
            "aliases": split(a.get("aliases")),
            "team_aliases": split(a.get("team_aliases")),
        })
    return out


def speaker_affiliations(speakers):
    """Affiliation labels from a speaker line such as "A (X), B (Y); moderated by C (Z)".

    Whoever follows "moderated by" is left out: a moderator does not present.
    """
    return re.findall(r"\(([^)]*)\)", re.split(r";?\s*moderated by", speakers or "", flags=re.I)[0])


def subnets_of_affiliation(text, entries):
    """Subnets that a speaker's affiliation label stands for.

    The label ("Macrocosmos", "Claims", "Bitcast, SN93") is compared with subnet
    names, aliases and team names. A team name returns every subnet of that team.
    """
    found = set()
    known = {e["netuid"] for e in entries}
    for m in _ID.finditer(text or ""):
        if int(m.group(1)) in known:
            found.add(int(m.group(1)))
    for part in re.split(r",|/|&|\band\b", text or ""):
        key = _norm(part)
        if not key:
            continue
        for e in entries:
            # a placeholder name ("for sale") identifies nobody; the team behind it still can be known
            own = [] if e["rule"] == "placeholder" else [e["name"]] + e["aliases"]
            if key in {_norm(x) for x in own + e["team_aliases"] if x}:
                found.add(e["netuid"])
    return found


def valid_for_project(hit, when, project_start):
    """Netuids are reused. A mention by number alone, dated before the current
    project started, refers to the previous occupant and does not count."""
    if not project_start:
        return True
    if set(hit["rules"]) <= {"id", "id_spoken"} and str(when)[:10] < str(project_start)[:10]:
        return False
    return True
