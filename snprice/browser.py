"""Fetch a web page: as the server sends it, and as a browser builds it.

Rendering uses headless Chrome with an empty throw-away profile. Addresses must be checked
with snprice.webtext.safe_url before they are passed here, because they come from free-text
fields written by subnet owners.
"""
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request

STATIC_MAX_BYTES = 3_000_000
RENDER_BUDGET_MS = 8000
RENDER_TIMEOUT = 75
AGENT = "Mozilla/5.0 (compatible; subnet-dataset-research/1.0)"
CHROME_PATHS = (
    os.environ.get("SNPRICE_CHROME") or "",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
)
_local = threading.local()
_counter = iter(range(10 ** 6))
_lock = threading.Lock()
_profiles = []


def chrome():
    for candidate in CHROME_PATHS:
        if candidate and os.path.exists(candidate):
            return candidate
    raise SystemExit("Chrome not found; set SNPRICE_CHROME to the browser's path")


def profile_dir():
    """One throw-away browser profile per thread."""
    if not hasattr(_local, "profile"):
        with _lock:
            _local.profile = os.path.join(tempfile.gettempdir(), f"snprice-chrome-{os.getpid()}-{next(_counter)}")
            _profiles.append(_local.profile)
    return _local.profile


def remove_profiles():
    for path in _profiles:
        shutil.rmtree(path, ignore_errors=True)


def render(url):
    """The page as the browser builds it (scripts run). Returns HTML, or None on failure."""
    cmd = [chrome(), "--headless=new", "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--mute-audio", f"--user-data-dir={profile_dir()}",
           f"--virtual-time-budget={RENDER_BUDGET_MS}", "--dump-dom", url]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = proc.communicate(timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        return None
    return out.decode("utf-8", "replace") if out else None


def http_answer(url):
    """(status code or None, final address, error name, HTML as sent by the server) of a plain request."""
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html = resp.read(STATIC_MAX_BYTES).decode("utf-8", "replace")
            return resp.status, resp.geturl(), None, html
    except urllib.error.HTTPError as exc:
        return exc.code, url, None, ""
    except Exception as exc:  # DNS failure, refused connection, bad certificate, timeout
        return None, url, type(exc).__name__, ""
