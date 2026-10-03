import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from snprice import paths


class LayoutTest(unittest.TestCase):
    """The project folder holds Input, Code, Output and Temp; the pipeline is Code/collection."""

    def test_project_is_the_parent_of_the_code_folder(self):
        self.assertEqual(paths.ROOT.name, "collection")
        self.assertEqual(paths.ROOT.parent.name, "Code")
        self.assertEqual(paths.PROJECT, paths.ROOT.parents[1])

    def test_the_dataset_and_the_codebook_live_in_input(self):
        self.assertEqual(paths.FINAL, paths.PROJECT / "Input")
        self.assertEqual(paths.CODEBOOK, paths.PROJECT / "Input" / "codebook.csv")
        self.assertEqual(paths.OUTPUT, paths.PROJECT / "Output")

    def test_caches_and_wallet_level_tables_live_in_temp(self):
        self.assertEqual(paths.TEMP, paths.PROJECT / "Temp")
        self.assertEqual(paths.RAW, paths.TEMP / "collection-cache" / "raw")
        self.assertEqual(paths.INTERMEDIATE, paths.TEMP / "collection-cache" / "intermediate")

    def test_tables_the_dataset_is_built_from_stay_with_the_code(self):
        for folder in (paths.CONFIG, paths.CHAIN, paths.EVIDENCE, paths.MANUAL):
            self.assertEqual(folder.parents[0 if folder is paths.CONFIG else 1], paths.ROOT)


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


class PreviousWaveTest(unittest.TestCase):
    def folder(self, tmp):
        (Path(tmp) / "snapshot.json").write_text(json.dumps({"wave": 1, "t_block": 100}), encoding="utf-8")
        (Path(tmp) / "snapshot_wave2.json").write_text(json.dumps({"wave": 2, "t_block": 200}), encoding="utf-8")
        (Path(tmp) / "snapshot_wave3.json").write_text(json.dumps({"wave": 3, "t_block": 300}), encoding="utf-8")
        return Path(tmp)

    def test_first_wave_has_no_wave_before_it(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(paths, "CONFIG", self.folder(tmp)):
            self.assertIsNone(paths.snapshot_before({"wave": 1}))

    def test_second_wave_follows_the_default_configuration(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(paths, "CONFIG", self.folder(tmp)):
            self.assertEqual(paths.snapshot_before({"wave": 2}), {"wave": 1, "t_block": 100})

    def test_later_waves_follow_the_numbered_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(paths, "CONFIG", self.folder(tmp)):
            self.assertEqual(paths.snapshot_before({"wave": 3}), {"wave": 2, "t_block": 200})

    def test_file_of_another_wave_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "snapshot.json").write_text(json.dumps({"wave": 5}), encoding="utf-8")
            with mock.patch.object(paths, "CONFIG", Path(tmp)), self.assertRaises(ValueError):
                paths.snapshot_before({"wave": 2})


if __name__ == "__main__":
    unittest.main()
