"""Write the configuration of the next wave: config/snapshot_wave<N>.json.

    python collect/make_wave_config.py 2

The snapshot block of a wave is the snapshot block of the wave before it plus one window
(30 days of blocks = 216,000). The windows of consecutive waves then join without a gap: the
lagged window of wave N+1 is the feature window of wave N, and the price 30 days before the
new snapshot is the price at the old one. With the block time of September 2026 (12.03
seconds) the new block falls about 1.6 hours after the end of the 30th calendar day.

The date in the file name of the dataset is the UTC date of the snapshot block, read from the
chain, so the script can only run once that block exists. The X budget of a follow-up wave
is 25 USD. Source: public archive node only.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice import paths  # noqa: E402
from snprice.files import atomic_write  # noqa: E402
from snprice.io import archive  # noqa: E402

X_USD_FOLLOW_UP = 25.0


def main():
    wave = int(sys.argv[1])
    if wave < 2:
        raise SystemExit("wave 1 is defined by hand in config/snapshot.json")
    before = paths.snapshot_before({"wave": wave})
    t_block = before["t_block"] + before["window_days"] * before["blocks_per_day"]
    arch = archive()
    head = arch.head()
    if head < t_block:
        left = (t_block - head) * 12 / 3600
        raise SystemExit(f"block {t_block} does not exist yet: the chain is at {head}, about {left:.1f} hours to go")
    stamp = time.gmtime(arch.timestamp(t_block))
    config = dict(before)
    config.update({
        "wave": wave,
        "snapshot_date": time.strftime("%Y-%m-%d", stamp),
        "t_block": t_block,
        "t_note": f"Snapshot block of wave {wave - 1} plus {before['window_days']} days of blocks "
                  f"({time.strftime('%Y-%m-%d %H:%M:%S', stamp)} UTC).",
        "x_usd_ceiling": X_USD_FOLLOW_UP,
    })
    path = paths.CONFIG / f"snapshot_wave{wave}.json"
    atomic_write(path, json.dumps(config, indent=2) + "\n")
    print(f"wrote {path.relative_to(paths.PROJECT)}: T = block {t_block} = {time.strftime('%Y-%m-%d %H:%M:%S', stamp)} UTC")
    print(f"run the wave with: python collect/run_all.py --config snapshot_wave{wave}.json")


if __name__ == "__main__":
    main()
