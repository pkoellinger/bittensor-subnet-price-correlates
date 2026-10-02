"""Throttled, cached, budgeted HTTP access to the Taostats REST API.

Rule that every caller relies on: a request either returns a body that contains
a `data` key, or it raises. A rate-limited or failed request is never returned
as an empty list, because an empty list would be read downstream as "zero".
"""
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.parse


class FetchError(RuntimeError):
    """The API did not deliver a valid answer."""


class BudgetExceeded(RuntimeError):
    """A ledger ceiling would be exceeded. Nothing was sent."""


class Ledger:
    """Persistent counters with hard ceilings (API calls, US dollars)."""

    def __init__(self, path, ceilings):
        self.path = path
        self.ceilings = dict(ceilings)

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        return {}

    def used(self, bucket):
        return self._load().get(bucket, 0)

    def book(self, bucket, amount=1):
        ceiling = self.ceilings[bucket]
        state = self._load()
        new = state.get(bucket, 0) + amount
        if new > ceiling + 1e-9:
            raise BudgetExceeded(f"{bucket}: {state.get(bucket, 0)} used, {amount} more would pass the ceiling {ceiling}")
        state[bucket] = round(new, 6)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh)
        os.replace(tmp, self.path)


def curl_transport(url, headers):
    """GET through curl. Taostats sits behind a filter that rejects Python's default client."""
    exe = shutil.which("curl") or shutil.which("curl.exe")
    if not exe:
        raise FetchError("curl was not found on PATH")
    cmd = [exe, "-s", "-m", "120", "-w", "\n%{http_code}"]
    for name, value in headers.items():
        cmd += ["-H", f"{name}: {value}"]
    cmd.append(url)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
    body, _, code = p.stdout.rpartition("\n")
    return (int(code) if code.isdigit() else 0), body


class Taostats:
    BASE = "https://api.taostats.io"
    RETRY_STATUS = {0, 429, 500, 502, 503, 504}

    def __init__(self, key, cache_dir, ledger, transport=curl_transport, min_gap=4.0,
                 sleep=time.sleep, clock=time.time, tries=7):
        if not key:
            raise FetchError("TAOSTATS_API_KEY is not set")
        self.key = key
        self.cache_dir = cache_dir
        self.ledger = ledger
        self.transport = transport
        self.min_gap = min_gap
        self.sleep = sleep
        self.clock = clock
        self.tries = tries
        self.stats = {"requests": 0, "retries": 0, "cache_hits": 0}
        os.makedirs(cache_dir, exist_ok=True)
        self._gap_file = os.path.join(cache_dir, ".last_call")

    # -- helpers
    def _url(self, path, params):
        query = urllib.parse.urlencode(sorted((k, v) for k, v in params.items() if v is not None))
        return f"{self.BASE}{path}" + (f"?{query}" if query else "")

    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")

    def _wait(self):
        """Keep at least `min_gap` seconds between calls, also across processes."""
        if self.min_gap <= 0:
            return
        last = 0.0
        if os.path.exists(self._gap_file):
            try:
                with open(self._gap_file, encoding="utf-8") as fh:
                    last = float(fh.read().strip() or 0)
            except (OSError, ValueError):
                last = 0.0
        wait = self.min_gap - (self.clock() - last)
        if wait > 0:
            self.sleep(wait)
        with open(self._gap_file, "w", encoding="utf-8") as fh:
            fh.write(str(self.clock()))

    # -- public
    def get(self, path, **params):
        """One request. Returns the parsed body (with `data`) or raises FetchError."""
        url = self._url(path, params)
        cache = self._cache_path(url)
        if os.path.exists(cache):
            self.stats["cache_hits"] += 1
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)["body"]

        problem = "no attempt made"
        for attempt in range(self.tries):
            self._wait()
            self.ledger.book("taostats", 1)
            self.stats["requests"] += 1
            status, body = self.transport(url, {"Authorization": self.key})
            if status == 200:
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict) and "data" in parsed:
                    record = {"url": url, "fetched_at": int(self.clock()),
                              "sha256": hashlib.sha256(body.encode()).hexdigest(), "body": parsed}
                    tmp = cache + ".tmp"
                    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                        json.dump(record, fh)
                    os.replace(tmp, cache)
                    return parsed
                problem = "HTTP 200 without a `data` key"
                self.stats["retries"] += 1
                self.sleep(10)
                continue
            problem = f"HTTP {status}"
            if status in self.RETRY_STATUS:
                self.stats["retries"] += 1
                self.sleep(15 * (attempt + 1))
                continue
            break  # other client errors will not improve on retry
        raise FetchError(f"{problem} for {url}")

    def get_all(self, path, per_page=200, max_pages=1000, partial_ok=False, **params):
        """All rows of a paginated endpoint. Raises if fewer rows arrive than announced."""
        rows, pg, total = [], 1, None
        while True:
            body = self.get(path, limit=per_page, page=pg, **params)
            rows.extend(body["data"])
            pagination = body.get("pagination") or {}
            if total is None:
                total = pagination.get("total_items")
            nxt = pagination.get("next_page")
            if not nxt:
                break
            if pg >= max_pages:
                if partial_ok:
                    return rows
                raise FetchError(f"{path}: stopped at page {pg} of a longer result ({total} rows announced)")
            pg = nxt
        if total is not None and len(rows) != total:
            raise FetchError(f"{path}: {len(rows)} rows received, {total} announced")
        return rows
