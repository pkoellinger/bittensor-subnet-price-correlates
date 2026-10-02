"""Find the snapshot block of a date: the last block produced on that UTC day.

Usage: python collect/find_block.py 2026-10-30

Prints the block number and its time. Put the number into the wave's config file as t_block
(config/snapshot.json for wave 1, config/snapshot_wave2.json for wave 2).
Source: public archive node only.
"""
import calendar
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snprice.io import archive  # noqa: E402


def last_block_before(arch, moment, low, high):
    """Largest block in [low, high] whose time is before `moment` (seconds since 1970)."""
    while low < high:
        mid = (low + high + 1) // 2
        if arch.timestamp(mid) < moment:
            low = mid
        else:
            high = mid - 1
    return low


def main():
    day = sys.argv[1]
    midnight_after = calendar.timegm(time.strptime(day, "%Y-%m-%d")) + 86400
    arch = archive()
    head = arch.head()
    if arch.timestamp(head) < midnight_after:
        raise SystemExit(f"{day} is not over yet: the chain is at block {head}")
    block = last_block_before(arch, midnight_after, 1, head)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(arch.timestamp(block)))
    print(f"last block of {day} UTC: {block} ({stamp})")


if __name__ == "__main__":
    main()
