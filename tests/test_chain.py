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


class StructDecodeTest(unittest.TestCase):
    # raw values read from the chain at block 9,184,186 (netuid 64 unless noted)
    def test_lock_state(self):
        out = chain.decode_lock("0x8126a8a11ccc020000000000000000008126a8a11ccc020003238c0000000000")
        self.assertEqual(out["locked_mass_rao"], 787373296723585)
        self.assertEqual(out["last_update"], 9184003)

    def test_absent_lock_is_none(self):
        self.assertIsNone(chain.decode_lock(None))

    def test_lock_of_wrong_size_raises(self):
        with self.assertRaises(ValueError):
            chain.decode_lock("0x8126a8a11ccc0200")

    def test_share_value_is_mantissa_times_power_of_ten(self):
        self.assertAlmostEqual(chain.decode_decimal("0x7d38d04e99c5ca3a2100000000000000faffffffffffffff"),
                               612978970094153513085e-6, delta=1.0)
        self.assertEqual(chain.decode_decimal("0x" + "00" * 24), 0.0)
        self.assertIsNone(chain.decode_decimal(None))

    def test_vec_bool(self):
        raw = "0x0104" + "00" + "01" + "00" * 254
        out = chain.decode_vec_bool(raw)
        self.assertEqual(len(out), 256)
        self.assertEqual(sum(out), 1)
        self.assertTrue(out[1])
        self.assertIsNone(chain.decode_vec_bool(None))

    def test_vec_account(self):
        a = bytes.fromhex(HOTKEY_HEX)
        raw = "0x08" + (a + a).hex()
        self.assertEqual(chain.decode_vec_account(raw), [HOTKEY, HOTKEY])
        self.assertEqual(chain.decode_vec_account("0x00"), [])
        self.assertIsNone(chain.decode_vec_account(None))

    def test_account(self):
        self.assertEqual(chain.decode_account("0x" + HOTKEY_HEX), HOTKEY)
        self.assertIsNone(chain.decode_account(None))

    def test_axon_ipv4(self):
        out = chain.decode_axon("0xd44e63000000000068778900d89ab693000000000000000000000000282304040000")
        self.assertEqual(out["ip"], "147.182.154.216")
        self.assertEqual(out["port"], 9000)
        self.assertEqual(out["block"], 6508244)
        self.assertIsNone(chain.decode_axon(None))

    def test_mechanism_split_real_value(self):
        self.assertEqual(chain.decode_vec_u16("0x080000ffff"), [0, 65535])

    def test_decay_of_a_decaying_lock(self):
        # unlock rate is the e-folding time in blocks
        self.assertAlmostEqual(chain.decayed_mass(1000.0, last_update=100, at_block=100, unlock_rate=934866), 1000.0)
        self.assertAlmostEqual(chain.decayed_mass(1000.0, last_update=0, at_block=934866, unlock_rate=934866),
                               1000.0 / 2.718281828459045)
        half_life = 934866 * 0.6931471805599453
        self.assertAlmostEqual(chain.decayed_mass(1000.0, 0, half_life, 934866), 500.0, places=6)


class IdentityTest(unittest.TestCase):
    # SubnetIdentitiesV3 of netuid 111 at block 9,184,186, as returned by the archive node
    RAW = ("0x18436c61696d739468747470733a2f2f6769746875622e636f6d2f4465536369436c61696d732f436c61696d7300000d01"
           "68747470733a2f2f646973636f72642e636f6d2f6368616e6e656c732f3739393637323031313236353031353831392f31"
           "35313530303733363630313634303135393911015475726e696e6720736369656e7469666963206c697465726174757265"
           "20696e746f2061207374727563747572656420636c61696d2d65766964656e6365206772617068fd0168747470733a2f2f"
           "7777772e64726f70626f782e636f6d2f73636c2f66692f3731326b756f6637383737353938746c76783365702f4d61696e"
           "2d4c6f676f5f4461726b5f436c61696d732e7376673f726c6b65793d7a68706d6c627969727664657a33676d346a303567"
           "62306c6b2673743d78666d347478397426646c3d3000")

    def test_real_identity_record(self):
        out = chain.decode_identity(self.RAW)
        self.assertEqual(out["subnet_name"], "Claims")
        self.assertEqual(out["github_repo"], "https://github.com/DeSciClaims/Claims")
        self.assertEqual(out["subnet_contact"], "")
        self.assertEqual(out["subnet_url"], "")
        self.assertTrue(out["discord"].startswith("https://discord.com/channels/"))
        self.assertEqual(out["description"], "Turning scientific literature into a structured claim-evidence graph")
        self.assertEqual(out["additional"], "")

    def test_absent_identity_is_none(self):
        self.assertIsNone(chain.decode_identity(None))

    def test_trailing_bytes_raise(self):
        with self.assertRaises(ValueError):
            chain.decode_identity(self.RAW + "00")

    def test_identity_key_uses_blake2_concat(self):
        self.assertEqual(
            chain.key("SubtensorModule", "SubnetIdentitiesV3", chain.blake2_128_concat(chain.u16(111))),
            "0x658faa385070e074c85bf6b568cf0555c7cb9786b286b680ca204a6c0920ee5239f31be776036f28fcb145f7f8ed2d386f00",
        )


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

    def test_too_many_requests_is_retried(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            slept = []
            rpc = FakeRpc([
                {"result": "0xabc"},
                {"error": {"code": -32029, "message": "Too Many Requests, Please apply an OnFinality API key"}},
                {"result": [{"block": "0xabc", "changes": [["0x01", "0x05"]]}]},
            ])
            arch = chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=slept.append)
            self.assertEqual(arch.read(["0x01"], block=7), {"0x01": "0x05"})
            self.assertTrue(slept)

    def test_other_rpc_errors_are_not_retried(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rpc = FakeRpc([{"result": "0xabc"}, {"error": {"code": 4003, "message": "UnknownBlock: State already discarded"}}])
            arch = chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=lambda s: None)
            with self.assertRaises(chain.ChainError):
                arch.read(["0x01"], block=7)
            self.assertEqual(len(rpc.calls), 2)

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

    def test_keys_under_a_prefix_are_listed_across_pages(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            rpc = FakeRpc([{"result": "0xabc"}, {"result": ["0xp1", "0xp2"]}, {"result": ["0xp3"]}])
            arch = chain.Archive(rpc=rpc, cache_dir=tmp, pace=0, sleep=lambda s: None)
            self.assertEqual(arch.keys("0xp", block=7, page=2), ["0xp1", "0xp2", "0xp3"])
            # the second page starts after the last key of the first page
            self.assertEqual(rpc.calls[2][1][2], "0xp2")

    def test_unknown_block_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            arch, rpc = self.make([{"result": None}], tmp)
            with self.assertRaises(chain.ChainError):
                arch.read(["0x01"], block=10 ** 12)


class PositionAlphaTest(unittest.TestCase):
    """Alpha of a (hotkey, coldkey) stake position. Raw values are from block 9,184,186,
    subnet 43; expected balances are Taostats' stake history at that block."""

    HOTKEY_ALPHA = "0x17967311474d0600"                                   # 1,773,817.49 alpha
    SHARES_V2 = "0x0eecbdef6e175ccc2b00000000000000faffffffffffffff"

    def raw(self, **kw):
        base = {"alpha_v1": None, "alpha_v2": None, "row_epoch": None, "shares_v1": None,
                "shares_v2": self.SHARES_V2, "hotkey_alpha": self.HOTKEY_ALPHA, "pool_epoch": None}
        base.update(kw)
        return base

    def test_position_still_in_the_old_share_map(self):
        raw = self.raw(alpha_v1="0xb80ee1f0e8d133f56b712a7c75710100")
        self.assertAlmostEqual(chain.position_alpha(raw), 891862.990906276, places=5)

    def test_position_in_the_new_share_map(self):
        raw = self.raw(alpha_v2="0x4b1ff3f646ce42361000000000000000faffffffffffffff")
        self.assertAlmostEqual(chain.position_alpha(raw), 656579.494326866, places=5)

    def test_old_map_position_on_another_hotkey(self):
        raw = {"alpha_v1": "0xee04d183e92961eb405995c800000000", "alpha_v2": None, "row_epoch": None,
               "shares_v1": None, "shares_v2": "0x667d1b7645afe5361300000000000000f6ffffffffffffff",
               "hotkey_alpha": "0x7c3234f0e4680000", "pool_epoch": None}
        self.assertAlmostEqual(chain.position_alpha(raw), 10950.124091598, places=5)

    def test_no_share_row_is_no_position(self):
        self.assertEqual(chain.position_alpha(self.raw()), 0.0)

    def test_empty_pool_is_worth_nothing(self):
        raw = self.raw(alpha_v2="0x4b1ff3f646ce42361000000000000000faffffffffffffff", shares_v2=None)
        self.assertEqual(chain.position_alpha(raw), 0.0)

    def test_old_maps_are_read_first_like_the_runtime_does(self):
        one, four = "0x" + (1 << 64).to_bytes(16, "little").hex(), "0x" + (4 << 64).to_bytes(16, "little").hex()
        eight_alpha = "0x" + (8 * 10 ** 9).to_bytes(8, "little").hex()
        raw = {"alpha_v1": one, "alpha_v2": "0x4b1ff3f646ce42361000000000000000faffffffffffffff", "row_epoch": None,
               "shares_v1": four, "shares_v2": self.SHARES_V2, "hotkey_alpha": eight_alpha, "pool_epoch": None}
        self.assertAlmostEqual(chain.position_alpha(raw), 2.0)

    def test_row_left_over_from_a_closed_pool_is_worth_nothing(self):
        epoch = lambda n: "0x" + n.to_bytes(8, "little").hex()  # noqa: E731
        share = "0x4b1ff3f646ce42361000000000000000faffffffffffffff"
        self.assertEqual(chain.position_alpha(self.raw(alpha_v2=share, pool_epoch=epoch(2), row_epoch=epoch(1))), 0.0)
        self.assertEqual(chain.position_alpha(self.raw(alpha_v2=share, pool_epoch=epoch(2))), 0.0)
        self.assertGreater(chain.position_alpha(self.raw(alpha_v2=share, pool_epoch=epoch(2), row_epoch=epoch(2))), 0)
        self.assertGreater(chain.position_alpha(self.raw(alpha_v2=share, pool_epoch=epoch(0), row_epoch=None)), 0)

    def test_storage_keys_of_a_position(self):
        keys = chain.position_keys("5HjMs5JDrLH3Hknmfm1gDq7nFYAv6M7t9v3EWMctSRXJS9HC",
                                   "5DndzoBo7wnQYHDFmpTMo78Gxc8wnX6kFjKoHRy2jMCWpJYK", 43)
        self.assertEqual(set(keys), {"alpha_v1", "alpha_v2", "row_epoch", "shares_v1", "shares_v2", "hotkey_alpha",
                                     "pool_epoch"})
        h = chain.blake2_128_concat(chain.ss58_decode("5HjMs5JDrLH3Hknmfm1gDq7nFYAv6M7t9v3EWMctSRXJS9HC"))
        c = chain.blake2_128_concat(chain.ss58_decode("5DndzoBo7wnQYHDFmpTMo78Gxc8wnX6kFjKoHRy2jMCWpJYK"))
        self.assertEqual(keys["alpha_v1"], chain.key("SubtensorModule", "Alpha", h, c, chain.u16(43)))
        self.assertEqual(keys["shares_v2"], chain.key("SubtensorModule", "TotalHotkeySharesV2", h, chain.u16(43)))
        self.assertEqual(len(set(keys.values())), 7)


if __name__ == "__main__":
    unittest.main()
