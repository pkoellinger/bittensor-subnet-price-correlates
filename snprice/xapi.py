"""X API v2 client with a spending ledger.

Pay-per-use prices (docs.x.com, October 2026): a post read costs $0.005, a user
read $0.010, an archive count request $0.010. Before each request the worst-case
cost is booked in the ledger; if that would pass the ceiling nothing is sent.
After the answer the booking is settled to what was actually returned. Answers
are cached, so a rerun does not pay twice.

Posts are only ever read for accounts on the approved list
(config/kol_accounts.csv, approved = yes with an approval date).
"""
import csv
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

COST_POST = 0.005
COST_USER = 0.010
COST_COUNT = 0.010
PAGE = 100


class XError(RuntimeError):
    """The X API refused or failed a request. Nothing is cached, nothing charged."""


def http_transport(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def load_approved(path):
    """Usernames (lower case) that Philipp approved for post reading."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8", newline="") as fh:
        return {
            row["username"].strip().lstrip("@").lower()
            for row in csv.DictReader(fh)
            if (row.get("approved") or "").strip().lower() == "yes" and (row.get("approved_on") or "").strip()
        }


class XClient:
    BASE = "https://api.x.com/2"

    def __init__(self, bearer, ledger, cache_dir, transport=http_transport, approved=None, sleep=time.sleep):
        if not bearer:
            raise XError("X_BEARER_TOKEN is not set")
        self.bearer = bearer
        self.ledger = ledger
        self.cache_dir = cache_dir
        self.transport = transport
        self.approved = {a.lstrip("@").lower() for a in (approved or ())}
        self.sleep = sleep
        os.makedirs(cache_dir, exist_ok=True)

    def _get(self, path, params, worst_cost, actual_cost):
        url = f"{self.BASE}{path}?" + urllib.parse.urlencode(sorted(params.items()))
        cache = os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)["body"]
        self.ledger.book("x_usd", worst_cost)          # raises before anything is sent
        try:
            status, body = self.transport(url, {"Authorization": f"Bearer {self.bearer}"})
            parsed = json.loads(body) if status == 200 else None
        except Exception as exc:
            self.ledger.book("x_usd", -worst_cost)
            raise XError(f"{path}: {exc!r}") from exc
        if status != 200 or not isinstance(parsed, dict):
            self.ledger.book("x_usd", -worst_cost)
            raise XError(f"{path}: HTTP {status}: {str(body)[:300]}")
        cost = actual_cost(parsed)
        if cost < worst_cost:
            self.ledger.book("x_usd", cost - worst_cost)
        tmp = cache + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"url": url, "fetched_at": int(time.time()), "cost_usd": cost, "body": parsed}, fh)
        os.replace(tmp, cache)
        return parsed

    def users_by(self, usernames, fields="created_at,public_metrics,verified,description,url"):
        """Profiles for up to any number of usernames (unknown names are simply absent)."""
        out = []
        names = [u.lstrip("@") for u in usernames]
        for i in range(0, len(names), PAGE):
            batch = names[i:i + PAGE]
            body = self._get("/users/by", {"usernames": ",".join(batch), "user.fields": fields},
                             worst_cost=COST_USER * len(batch),
                             actual_cost=lambda b: COST_USER * len(b.get("data") or []))
            out.extend(body.get("data") or [])
        return out

    def counts_all(self, query, start, end, granularity="day"):
        """Posts per period matching a query over the full archive."""
        rows, token = [], None
        while True:
            params = {"query": query, "start_time": start, "end_time": end, "granularity": granularity}
            if token:
                params["next_token"] = token
            body = self._get("/tweets/counts/all", params, worst_cost=COST_COUNT,
                             actual_cost=lambda b: COST_COUNT)
            rows.extend(body.get("data") or [])
            token = (body.get("meta") or {}).get("next_token")
            if not token:
                return rows

    def user_posts(self, user_id, username, start, end, exclude=("retweets", "replies"), max_pages=40,
                   fields="created_at,referenced_tweets,entities,note_tweet,public_metrics"):
        """All posts of an APPROVED account in a time window (expansions are not requested)."""
        if username.lstrip("@").lower() not in self.approved:
            raise PermissionError(f"@{username} is not on the approved list; no post is read")
        rows, token = [], None
        for _ in range(max_pages):
            params = {"start_time": start, "end_time": end, "max_results": PAGE, "tweet.fields": fields}
            if exclude:
                params["exclude"] = ",".join(exclude)
            if token:
                params["pagination_token"] = token
            body = self._get(f"/users/{user_id}/tweets", params, worst_cost=COST_POST * PAGE,
                             actual_cost=lambda b: COST_POST * len(b.get("data") or []))
            rows.extend(body.get("data") or [])
            token = (body.get("meta") or {}).get("next_token")
            if not token:
                return rows
        raise XError(f"@{username}: more than {max_pages} pages in the window; window not complete")
