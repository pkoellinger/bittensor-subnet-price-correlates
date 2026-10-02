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


def _answers_over_waves(cfg, stem, field):
    """{(post_id, netuid): answer} of one coder for a wave: the wave's own file
    data/manual/<stem with the wave number>.json, and the files of earlier waves for pairs
    whose netuid still belongs to the same subnet (snprice.kol.carry_labels)."""
    from .kol import carry_labels

    def uids(wave):
        return {int(r["netuid"]): r["subnet_uid"] for r in read_table(paths.CHAIN / f"roster_wave{wave}.csv")}

    def own(wave):
        return read_json(paths.MANUAL / stem.format(wave=wave), default=[])

    chain, earlier = [], paths.snapshot_before(cfg)
    while earlier:
        chain.append(earlier)
        earlier = paths.snapshot_before(earlier)
    answers, current = {}, uids(cfg["wave"])
    for old in reversed(chain):
        answers.update(carry_labels(own(old["wave"]), uids(old["wave"]), current, field=field))
    answers.update({(str(r["post_id"]), int(r["netuid"])): r[field] for r in own(cfg["wave"])})
    return answers


def polarity_labels(cfg, coder):
    """One coder's labels that apply to a wave: {(post_id, netuid): label}.

    A wave's own file data/manual/kol_polarity_wave<N>_coder_<X>.json holds what was labelled
    in that wave. The 90-day window of a follow-up wave overlaps earlier waves, so their labels
    are carried over where the netuid still belongs to the same subnet.
    """
    return _answers_over_waves(cfg, "kol_polarity_wave{wave}_coder_" + coder + ".json", "label")


def attribution_readings(cfg, reader):
    """One reader's answers that apply to a wave: {(post_id, netuid): "yes" | "no"}, for the
    posts that name a subnet by number alone (config/kol_attribution.md). Files:
    data/manual/kol_attribution_wave<N>_reader_<X>.json; earlier waves are carried over like labels."""
    return _answers_over_waves(cfg, "kol_attribution_wave{wave}_reader_" + reader + ".json", "refers_to_current")


def write_json(path, obj):
    atomic_write(path, json.dumps(obj, indent=1, sort_keys=True) + "\n")


def read_json(path, default=None):
    if not os.path.exists(str(path)):
        return default
    with open(str(path), encoding="utf-8") as fh:
        return json.load(fh)
