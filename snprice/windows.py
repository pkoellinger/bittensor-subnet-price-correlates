"""Block windows of a wave.

Windows are defined in blocks, counted back from the snapshot block T:
  window   (T - 30 days of blocks, T]          the feature window, suffix _30d
  lag      (T - 60 days of blocks, T - 30]     the lagged window, suffix _lag30
A "day" is 7,200 blocks (12-second target block time), so 30 days are 216,000
blocks, about 30.07 calendar days at the block time observed in September 2026.
Within a window the chain is sampled every `grid_blocks` blocks (900 = 8 a day).
"""

NAMES = ("window", "lag", "all")


def _per_window(cfg):
    return cfg["window_days"] * cfg["blocks_per_day"] // cfg["grid_blocks"]


def sample_blocks(cfg, which="window"):
    """Sample blocks in ascending order."""
    if which not in NAMES:
        raise ValueError(f"window must be one of {NAMES}, got {which!r}")
    t, step, n = cfg["t_block"], cfg["grid_blocks"], _per_window(cfg)
    lag = [t - step * k for k in range(2 * n - 1, n - 1, -1)]
    window = [t - step * k for k in range(n - 1, -1, -1)]
    return {"window": window, "lag": lag, "all": lag + window}[which]


def emitting_blocks(lo, hi, first_emission):
    """Number of blocks in (lo, hi] in which a subnet emitted alpha.

    first_emission is the subnet's first emission block, or None if its emissions have
    not started. Between registration and that block a subnet emits nothing.
    """
    if first_emission is None or first_emission > hi:
        return 0
    return hi - max(lo, first_emission - 1)


def bounds(cfg, which="window", days=None):
    """(start, end] block range of a window; `days` overrides the window length."""
    if which not in ("window", "lag"):
        raise ValueError(f"window must be 'window' or 'lag', got {which!r}")
    span = (days or cfg["window_days"]) * cfg["blocks_per_day"]
    end = cfg["t_block"] - (cfg["lag_days"] * cfg["blocks_per_day"] if which == "lag" else 0)
    return end - span, end
