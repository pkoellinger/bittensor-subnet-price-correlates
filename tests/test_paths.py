import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from snprice import paths


class SnapshotConfigTest(unittest.TestCase):
    def test_default_is_the_first_wave(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SNPRICE_SNAPSHOT", None)
            self.assertEqual(paths.snapshot()["wave"], 1)

    def test_another_wave_is_chosen_through_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "snapshot_wave2.json").write_text(json.dumps({"wave": 2, "t_block": 123}), encoding="utf-8")
            with mock.patch.object(paths, "CONFIG", Path(tmp)), \
                    mock.patch.dict(os.environ, {"SNPRICE_SNAPSHOT": "snapshot_wave2.json"}):
                self.assertEqual(paths.snapshot(), {"wave": 2, "t_block": 123})

    def test_file_name_must_stay_inside_the_config_folder(self):
        with mock.patch.dict(os.environ, {"SNPRICE_SNAPSHOT": "../secrets.json"}):
            with self.assertRaises(ValueError):
                paths.snapshot()


if __name__ == "__main__":
    unittest.main()
