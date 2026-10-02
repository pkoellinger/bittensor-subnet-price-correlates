"""Locations, configuration and secrets. Paths are relative to the repository root."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"                    # API caches, not committed
INTERMEDIATE = DATA / "intermediate"  # per-block tables incl. wallet-level rows, not committed
CHAIN = DATA / "chain"                # small tables read from the archive node, committed
EVIDENCE = DATA / "evidence"
MANUAL = DATA / "manual"
FINAL = DATA / "final"


def snapshot():
    """The wave definition (config/snapshot.json)."""
    with open(CONFIG / "snapshot.json", encoding="utf-8") as fh:
        return json.load(fh)


def raw_dir(name):
    d = RAW / f"wave{snapshot()['wave']}" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def secret(name):
    """A secret from the environment or from .env; never printed, never written.

    A `.env` line `X_ENV_FILE=<path>` points at another env file that holds
    X_BEARER_TOKEN, so the token does not have to be copied.
    """
    if os.environ.get(name):
        return os.environ[name]
    local = _read_env_file(ROOT / ".env")
    if local.get(name):
        return local[name]
    other = local.get("X_ENV_FILE") or os.environ.get("X_ENV_FILE")
    if other:
        return _read_env_file(other).get(name)
    return None
