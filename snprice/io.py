"""Clients configured for the current wave, and plain-text table helpers."""
import csv
import io
import json
import os

from . import paths
from .chain import Archive
from .fetch import Ledger, Taostats
from .files import atomic_write


def ledger():
    cfg = paths.snapshot()
    return Ledger(str(paths.raw_dir("") / "ledger.json"),
                  {"taostats": cfg["taostats_call_ceiling"], "x_usd": cfg["x_usd_ceiling"]})


def taostats():
    cfg = paths.snapshot()
    return Taostats(paths.secret("TAOSTATS_API_KEY"), cache_dir=str(paths.raw_dir("taostats")),
                    ledger=ledger(), min_gap=cfg["taostats_min_gap_seconds"])


def archive():
    return Archive(cache_dir=str(paths.raw_dir("chain")))


def write_table(path, rows, columns=None):
    """Write dict rows as UTF-8 CSV with \\n line ends. None becomes an empty cell (NA)."""
    rows = list(rows)
    if columns is None:
        columns = []
        for r in rows:                     # union of keys, in first-seen order
            for k in r:
                if k not in columns:
                    columns.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})
    atomic_write(path, buf.getvalue())


def read_table(path):
    """Read a CSV written by write_table. Empty cells come back as None."""
    with open(str(path), encoding="utf-8", newline="") as fh:
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(fh)]


def write_json(path, obj):
    atomic_write(path, json.dumps(obj, indent=1, sort_keys=True) + "\n")


def read_json(path, default=None):
    if not os.path.exists(str(path)):
        return default
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)
