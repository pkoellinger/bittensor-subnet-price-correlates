"""Read Bittensor chain state at a pinned block from the public archive node.

Everything read through this module can be reproduced by anyone without an API
key. A value that is absent on chain is returned as None; callers must pass an
explicit default if (and only if) the runtime defines one.
"""
import hashlib
import json
import os
import struct
import time
import urllib.request

from .files import atomic_write

# Two independent public nodes that serve historical state. They return identical
# values (checked at the snapshot block). OnFinality answers a batched read of
# 1,280 keys in about a second; the Opentensor archive enforces a work budget of
# roughly 500 keys a minute and is used for cross-checks and as a fallback.
ARCHIVE_URL = os.environ.get("SNPRICE_ARCHIVE_URL", "https://bittensor-finney.api.onfinality.io/public")
ARCHIVE_URL_OPENTENSOR = "https://archive.chain.opentensor.ai"
_M = (1 << 64) - 1
_P1, _P2, _P3, _P4, _P5 = (11400714785074694791, 14029467366897019727, 1609587929392839161,
                           9650029242287828579, 2870177450012600261)


class ChainError(RuntimeError):
    """A chain read failed. Never swallowed: a failed read is not an absent value."""


# ------------------------------------------------------------------ hashing

def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M


def xxh64(data, seed):
    n = len(data)
    i = 0
    if n >= 32:
        v1, v2, v3, v4 = (seed + _P1 + _P2) & _M, (seed + _P2) & _M, seed, (seed - _P1) & _M
        while i + 32 <= n:
            a, b, c, d = struct.unpack_from("<QQQQ", data, i)
            v1 = (_rotl((v1 + a * _P2) & _M, 31) * _P1) & _M
            v2 = (_rotl((v2 + b * _P2) & _M, 31) * _P1) & _M
            v3 = (_rotl((v3 + c * _P2) & _M, 31) * _P1) & _M
            v4 = (_rotl((v4 + d * _P2) & _M, 31) * _P1) & _M
            i += 32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M
        for v in (v1, v2, v3, v4):
            k = (_rotl((v * _P2) & _M, 31) * _P1) & _M
            h = ((h ^ k) * _P1 + _P4) & _M
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while i + 8 <= n:
        (k,) = struct.unpack_from("<Q", data, i)
        k = (_rotl((k * _P2) & _M, 31) * _P1) & _M
        h = (_rotl(h ^ k, 27) * _P1 + _P4) & _M
        i += 8
    if i + 4 <= n:
        (k,) = struct.unpack_from("<I", data, i)
        h = (_rotl(h ^ ((k * _P1) & _M), 23) * _P2 + _P3) & _M
        i += 4
    while i < n:
        h = (_rotl(h ^ ((data[i] * _P5) & _M), 11) * _P1) & _M
        i += 1
    h ^= h >> 33
    h = (h * _P2) & _M
    h ^= h >> 29
    h = (h * _P3) & _M
    h ^= h >> 32
    return h


def twox128(name):
    b = name.encode()
    return struct.pack("<Q", xxh64(b, 0)) + struct.pack("<Q", xxh64(b, 1))


def twox64_concat(raw):
    return struct.pack("<Q", xxh64(raw, 0)) + raw


def blake2_128(raw):
    return hashlib.blake2b(raw, digest_size=16).digest()


def blake2_128_concat(raw):
    return blake2_128(raw) + raw


def u16(n):
    return struct.pack("<H", n)


def key(pallet, item, *parts):
    """Storage key: twox128(pallet) + twox128(item) + already-hashed key parts."""
    return "0x" + (twox128(pallet) + twox128(item) + b"".join(parts)).hex()


def mech_index(netuid, mechanism):
    """Storage index of a subnet mechanism (per-mechanism vectors such as Incentive)."""
    return netuid + 4096 * mechanism


def netuid_from_key(storage_key):
    return int.from_bytes(bytes.fromhex(storage_key[-4:]), "little")


# ------------------------------------------------------------------ addresses

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(raw):
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + out


def _b58decode(text):
    n = 0
    for ch in text:
        if ch not in _B58:
            raise ValueError(f"invalid base58 character {ch!r}")
        n = n * 58 + _B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\0" * (len(text) - len(text.lstrip("1"))) + raw


def ss58_encode(pubkey, prefix=42):
    body = bytes([prefix]) + pubkey
    check = hashlib.blake2b(b"SS58PRE" + body, digest_size=64).digest()[:2]
    return _b58encode(body + check)


def ss58_decode(address):
    """SS58 address -> 32-byte public key. Raises ValueError on a bad checksum."""
    raw = _b58decode(address)
    if len(raw) != 35:
        raise ValueError(f"unexpected SS58 length for {address!r}")
    body, check = raw[:-2], raw[-2:]
    if hashlib.blake2b(b"SS58PRE" + body, digest_size=64).digest()[:2] != check:
        raise ValueError(f"bad SS58 checksum for {address!r}")
    return body[1:]


# ------------------------------------------------------------------ decoding

def decode_uint(raw, default=None):
    """Little-endian unsigned integer of any width; `default` only when absent."""
    if raw is None:
        return default
    return int.from_bytes(bytes.fromhex(raw[2:]), "little")


def decode_fixed(raw, frac_bits, default=None):
    """Unsigned fixed-point number (for example U96F32 -> frac_bits=32)."""
    if raw is None:
        return default
    return int.from_bytes(bytes.fromhex(raw[2:]), "little") / float(1 << frac_bits)


def decode_bool(raw, default=None):
    if raw is None:
        return default
    return bytes.fromhex(raw[2:]) != b"\x00"


def _compact(data):
    mode = data[0] & 3
    if mode == 0:
        return data[0] >> 2, 1
    if mode == 1:
        return int.from_bytes(data[:2], "little") >> 2, 2
    if mode == 2:
        return int.from_bytes(data[:4], "little") >> 2, 4
    n = (data[0] >> 2) + 4
    return int.from_bytes(data[1:1 + n], "little"), 1 + n


def decode_vec_u16(raw):
    """SCALE Vec<u16> (Incentive, Dividends, ...). None when absent."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    length, offset = _compact(data)
    if len(data) - offset != 2 * length:
        raise ValueError(f"Vec<u16> of declared length {length} has {len(data) - offset} payload bytes")
    return list(struct.unpack_from(f"<{length}H", data, offset))


def decode_account(raw):
    """32-byte account id -> SS58 address. None when absent."""
    if raw is None:
        return None
    return ss58_encode(bytes.fromhex(raw[2:]))


def decode_vec_account(raw):
    """SCALE Vec<AccountId32> -> list of SS58 addresses. None when absent."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    length, offset = _compact(data)
    if len(data) - offset != 32 * length:
        raise ValueError(f"Vec<AccountId> of declared length {length} has {len(data) - offset} payload bytes")
    return [ss58_encode(data[offset + 32 * i: offset + 32 * (i + 1)]) for i in range(length)]


def decode_vec_bool(raw):
    """SCALE Vec<bool> (ValidatorPermit, Active). None when absent."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    length, offset = _compact(data)
    if len(data) - offset != length:
        raise ValueError(f"Vec<bool> of declared length {length} has {len(data) - offset} payload bytes")
    return [b != 0 for b in data[offset:]]


def decode_lock(raw):
    """LockState {locked_mass: u64, conviction: U64F64, last_update: u64}. None when absent.

    locked_mass is the value as of `last_update`; a decaying lock must be rolled
    forward with decayed_mass() before it is compared across subnets.
    """
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    if len(data) != 32:
        raise ValueError(f"LockState must be 32 bytes, got {len(data)}")
    return {
        "locked_mass_rao": int.from_bytes(data[0:8], "little"),
        "conviction": int.from_bytes(data[8:24], "little") / float(1 << 64),
        "last_update": int.from_bytes(data[24:32], "little"),
    }


def decayed_mass(mass, last_update, at_block, unlock_rate):
    """Locked mass of a DECAYING lock at a later block.

    The runtime computes mass * exp(-dt / UnlockRate) (pallets/subtensor/src/
    staking/lock.rs, calculate_decayed_mass_and_conviction). Perpetual locks do
    not decay and must not be passed through this function.
    """
    import math
    dt = max(0.0, float(at_block) - float(last_update))
    if dt == 0:
        return float(mass)
    if not unlock_rate:
        return 0.0
    return float(mass) * math.exp(-dt / float(unlock_rate))


def decode_decimal(raw):
    """Share amounts (AlphaV2, TotalHotkeySharesV2): {mantissa: i128, exponent: i64} -> float."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    if len(data) != 24:
        raise ValueError(f"decimal share value must be 24 bytes, got {len(data)}")
    mantissa = int.from_bytes(data[0:16], "little", signed=True)
    exponent = int.from_bytes(data[16:24], "little", signed=True)
    return float(mantissa) * (10.0 ** exponent)


def decode_axon(raw):
    """AxonInfo {block u64, version u32, ip u128, port u16, ip_type u8, protocol u8, 2 placeholders}."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    if len(data) != 34:
        raise ValueError(f"AxonInfo must be 34 bytes, got {len(data)}")
    ip_int = int.from_bytes(data[12:28], "little")
    ip_type = data[30]
    if ip_type == 4:
        ip = ".".join(str((ip_int >> s) & 255) for s in (24, 16, 8, 0))
    else:
        ip = format(ip_int, "032x")
    return {"block": int.from_bytes(data[0:8], "little"), "ip": ip,
            "port": int.from_bytes(data[28:30], "little"), "ip_type": ip_type}


IDENTITY_FIELDS = ("subnet_name", "github_repo", "subnet_contact", "subnet_url", "discord",
                   "description", "logo_url", "additional")


def decode_identity(raw):
    """SubnetIdentitiesV3: eight consecutive SCALE byte strings. None when absent."""
    if raw is None:
        return None
    data = bytes.fromhex(raw[2:])
    out, pos = {}, 0
    for name in IDENTITY_FIELDS:
        if pos >= len(data):
            raise ValueError(f"identity record ends before field {name}")
        length, used = _compact(data[pos:])
        pos += used
        if pos + length > len(data):
            raise ValueError(f"identity record ends inside field {name}")
        out[name] = data[pos:pos + length].decode("utf-8", "replace")
        pos += length
    if pos != len(data):
        raise ValueError(f"identity record has {len(data) - pos} unexpected trailing bytes")
    return out


# ------------------------------------------------------------------ archive node

def _http_rpc(url):
    def call(method, params):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "User-Agent": "curl/8.4.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    return call


class Archive:
    """Batched, cached, paced storage reads at historical blocks.

    The public archive enforces a "historical work" budget: when it is used up the
    node answers with error -32004 and the client must wait. Reads are cached on
    disk per block, so an interrupted run resumes without repeating work.
    """

    def __init__(self, url=ARCHIVE_URL, cache_dir=None, rpc=None, pace=0.35, sleep=time.sleep,
                 tries=12, batch=400):
        self.rpc = rpc or _http_rpc(url)
        self.cache_dir = cache_dir
        self.pace = pace
        self.sleep = sleep
        self.tries = tries
        self.batch = batch
        self.calls = 0
        self._mem = {}
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    # -- low level
    def _call(self, method, params):
        last = None
        for attempt in range(self.tries):
            try:
                out = self.rpc(method, params)
            except Exception as exc:  # network trouble: back off and retry
                last = exc
                self.sleep(3 + 3 * attempt)
                continue
            self.calls += 1
            if "error" in out:
                last = out["error"]
                msg = json.dumps(out["error"]).lower()
                if "-32004" in msg or "budget" in msg:      # archive.chain.opentensor.ai work budget
                    self.sleep(40)
                    continue
                if "-32029" in msg or "too many requests" in msg or "rate" in msg or "429" in msg:
                    self.sleep(5 + 5 * attempt)
                    continue
                raise ChainError(f"{method}: {out['error']}")
            if self.pace:
                self.sleep(self.pace)
            return out.get("result")
        raise ChainError(f"{method} failed after {self.tries} attempts: {last}")

    def _path(self, block):
        return os.path.join(self.cache_dir, f"{block}.json") if self.cache_dir else None

    def _load(self, block):
        if block not in self._mem:
            path = self._path(block)
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    self._mem[block] = json.load(fh)
            else:
                self._mem[block] = {"hash": None, "values": {}}
        return self._mem[block]

    def _save(self, block):
        path = self._path(block)
        if not path:
            return
        atomic_write(path, json.dumps(self._mem[block]))

    # -- public
    def block_hash(self, block):
        entry = self._load(block)
        if not entry["hash"]:
            h = self._call("chain_getBlockHash", [block])
            if not h:
                raise ChainError(f"block {block} is unknown to the node")
            entry["hash"] = h
            self._save(block)
        return entry["hash"]

    def read(self, keys, block):
        """Return {key: hex value or None} for every key, at the given block."""
        entry = self._load(block)
        block_hash = self.block_hash(block)
        missing = [k for k in dict.fromkeys(keys) if k not in entry["values"]]
        for i in range(0, len(missing), self.batch):
            chunk = missing[i:i + self.batch]
            res = self._call("state_queryStorageAt", [chunk, block_hash])
            if not res or "changes" not in res[0]:
                raise ChainError(f"unexpected state_queryStorageAt answer at block {block}: {res!r:.200}")
            got = {k: v for k, v in res[0]["changes"]}
            absent = [k for k in chunk if k not in got]
            if absent:
                raise ChainError(f"{len(absent)} of {len(chunk)} keys missing from the answer at block {block}")
            entry["values"].update({k: got[k] for k in chunk})
            self._save(block)
        return {k: entry["values"][k] for k in keys}

    def forget(self, block):
        """Drop a block from memory (it stays on disk). For long passes over many blocks."""
        self._mem.pop(block, None)

    def read_map(self, pallet, item, netuids, block, part=u16):
        """Read a netuid-keyed map for many subnets; returns {netuid: hex or None}."""
        keys = {n: key(pallet, item, part(n)) for n in netuids}
        values = self.read(list(keys.values()), block)
        return {n: values[k] for n, k in keys.items()}

    def keys(self, prefix, block, page=500):
        """All storage keys under a prefix at a block (for maps keyed by something we cannot enumerate)."""
        block_hash = self.block_hash(block)
        out, start = [], prefix
        while True:
            chunk = self._call("state_getKeysPaged", [prefix, page, start, block_hash]) or []
            out.extend(chunk)
            if len(chunk) < page:
                return out
            start = chunk[-1]

    def timestamp(self, block):
        """Block time as Unix seconds (Timestamp.Now is in milliseconds)."""
        k = key("Timestamp", "Now")
        return decode_uint(self.read([k], block)[k]) / 1000.0

    def spec_version(self, block):
        entry = self._load(block)
        if "spec" not in entry:
            entry["spec"] = self._call("state_getRuntimeVersion", [self.block_hash(block)])["specVersion"]
            self._save(block)
        return entry["spec"]
