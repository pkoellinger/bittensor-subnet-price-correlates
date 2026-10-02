import unittest

from snprice import chain

HOTKEY = "5CS3g6nVJM6ouns8n9buN9CzFf2C1YDHVcVGRcxoirKs2xbV"
HOTKEY_HEX = "1046ddb9e982f422f9f020aa3f624ef74e9f5aa95b0ecbec5737640f36ee7c34"


class HashersTest(unittest.TestCase):
    def test_twox128_known_vector(self):
        self.assertEqual(chain.twox128("System").hex(), "26aa394eea5630e07c48ae0c9558cef7")

    def test_blake2_128_of_empty_input(self):
        self.assertEqual(chain.blake2_128(b"").hex(), "cae66941d9efbd404e4d88758ea67670")

    def test_ss58_round_trip(self):
        self.assertEqual(chain.ss58_decode(HOTKEY).hex(), HOTKEY_HEX)
        self.assertEqual(chain.ss58_encode(bytes.fromhex(HOTKEY_HEX)), HOTKEY)

    def test_ss58_rejects_a_corrupted_address(self):
        with self.assertRaises(ValueError):
            chain.ss58_decode(HOTKEY[:-1] + ("a" if HOTKEY[-1] != "a" else "b"))


class StorageKeyTest(unittest.TestCase):
    # reference keys produced by substrate-interface against the live runtime (spec 470)
    def test_plain_value(self):
        self.assertEqual(
            chain.key("SubtensorModule", "SubnetMovingAlpha"),
            "0x658faa385070e074c85bf6b568cf055565ef4b6311933743a027c3602fbabe20",
        )

    def test_identity_hashed_netuid(self):
        self.assertEqual(
            chain.key("SubtensorModule", "MinerBurned", chain.u16(95)),
            "0x658faa385070e074c85bf6b568cf05551eac6222ebba7feba4ca36a94736815e5f00",
        )

    def test_two_identity_parts(self):
        self.assertEqual(
            chain.key("SubtensorModule", "Keys", chain.u16(64), chain.u16(1)),
            "0x658faa385070e074c85bf6b568cf05559f99a2ce711f3a31b2fc05604c93f17940000100",
        )

    def test_blake2_concat_then_identity(self):
        self.assertEqual(
            chain.key("SubtensorModule", "TotalHotkeyAlpha",
                      chain.blake2_128_concat(chain.ss58_decode(HOTKEY)), chain.u16(64)),
            "0x658faa385070e074c85bf6b568cf0555ee25c3b5b1886863480497907f1829e6"
            "d9a7169ba94409efe45f138dc9a56b9a" + HOTKEY_HEX + "4000",
        )

    def test_twox64_concat(self):
        self.assertEqual(
            chain.key("AlphaAssets", "AlphaBurned", chain.twox64_concat(chain.u16(64))),
            "0x22675d5b0c6bb35f892f28ed2a462afda5747a0c54d7c3c36fa930aea935e15162cf9476b03dd8654000",
        )

    def test_incentive_index_of_second_mechanism(self):
        # mechanism m of netuid n is stored under index n + 4096 * m
        self.assertEqual(chain.mech_index(44, 0), 44)
        self.assertEqual(chain.mech_index(44, 1), 4140)

    def test_netuid_is_read_back_from_key_suffix(self):
        k = chain.key("SubtensorModule", "MinerBurned", chain.u16(111))
        self.assertEqual(chain.netuid_from_key(k), 111)


class DecodeTest(unittest.TestCase):
    def test_fixed_point_one(self):
        # MinerBurned of SN95 at block 9,184,186: bits = 2**32
        self.assertEqual(chain.decode_fixed("0x00000000010000000000000000000000", 32), 1.0)

    def test_fixed_point_fraction(self):
        raw = "0x" + int(0.25 * 2 ** 32).to_bytes(16, "little").hex()
        self.assertAlmostEqual(chain.decode_fixed(raw, 32), 0.25)

    def test_uint(self):
        self.assertEqual(chain.decode_uint("0x" + (202926020237521).to_bytes(8, "little").hex()), 202926020237521)

    def test_reserve_price_known_value(self):
        # SubnetTAO(64) / SubnetAlphaIn(64) at block 9,184,186
        tao = chain.decode_uint("0x" + (202926020237521).to_bytes(8, "little").hex())
        alpha = chain.decode_uint("0x" + (2881037904642989).to_bytes(8, "little").hex())
        self.assertEqual(round(tao / alpha, 8), 0.07043504)

    def test_absent_value_is_not_silently_zero(self):
        self.assertIsNone(chain.decode_uint(None))
        self.assertIsNone(chain.decode_fixed(None, 32))

    def test_absent_value_takes_an_explicit_default_only(self):
        self.assertEqual(chain.decode_uint(None, default=0), 0)
        self.assertIs(chain.decode_bool(None, default=True), True)
        self.assertIsNone(chain.decode_bool(None))

    def test_bool(self):
        self.assertIs(chain.decode_bool("0x01"), True)
        self.assertIs(chain.decode_bool("0x00"), False)

    def test_vec_u16_short(self):
        self.assertEqual(chain.decode_vec_u16("0x0c010002000300"), [1, 2, 3])

    def test_vec_u16_two_byte_length_prefix(self):
        raw = "0x0104" + "0500" * 256
        out = chain.decode_vec_u16(raw)
        self.assertEqual(len(out), 256)
        self.assertEqual(set(out), {5})

    def test_vec_u16_absent(self):
        self.assertIsNone(chain.decode_vec_u16(None))

    def test_vec_u16_with_wrong_length_raises(self):
        with self.assertRaises(ValueError):
            chain.decode_vec_u16("0x0c01000200")


class FakeRpc:
    """Stands in for the archive node: scripted responses per call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class ArchiveTest(unittest.TestCase):
    def make(self, responses, tmp):
        rpc = FakeRpc(responses)
        return chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=lambda s: None), rpc

    def test_read_returns_every_requested_key_with_none_for_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arch, rpc = self.make([
                {"result": "0xabc"},
                {"result": [{"block": "0xabc", "changes": [["0x01", "0xff"], ["0x02", None]]}]},
            ], tmp)
            out = arch.read(["0x01", "0x02"], block=100)
            self.assertEqual(out, {"0x01": "0xff", "0x02": None})

    def test_second_read_is_served_from_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arch, rpc = self.make([
                {"result": "0xabc"},
                {"result": [{"block": "0xabc", "changes": [["0x01", "0xff"]]}]},
            ], tmp)
            arch.read(["0x01"], block=100)
            again = chain.Archive(rpc=FakeRpc([]), cache_dir=tmp, pace=0, sleep=lambda s: None)
            self.assertEqual(again.read(["0x01"], block=100), {"0x01": "0xff"})

    def test_budget_error_is_retried(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            slept = []
            rpc = FakeRpc([
                {"result": "0xabc"},
                {"error": {"code": -32004, "message": "Historical work rate limit exceeded"}},
                {"result": [{"block": "0xabc", "changes": [["0x01", "0x05"]]}]},
            ])
            arch = chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=slept.append)
            self.assertEqual(arch.read(["0x01"], block=7), {"0x01": "0x05"})
            self.assertTrue(any(s >= 30 for s in slept))

    def test_persistent_error_raises_instead_of_returning_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rpc = FakeRpc([{"result": "0xabc"}] + [{"error": {"code": -32004, "message": "budget"}}] * 20)
            arch = chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=lambda s: None, tries=3)
            with self.assertRaises(chain.ChainError):
                arch.read(["0x01"], block=7)

    def test_missing_key_in_response_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arch, rpc = self.make([
                {"result": "0xabc"},
                {"result": [{"block": "0xabc", "changes": [["0x01", "0xff"]]}]},
            ], tmp)
            with self.assertRaises(chain.ChainError):
                arch.read(["0x01", "0x02"], block=100)

    def test_unknown_block_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arch, rpc = self.make([{"result": None}], tmp)
            with self.assertRaises(chain.ChainError):
                arch.read(["0x01"], block=10 ** 12)


if __name__ == "__main__":
    unittest.main()
