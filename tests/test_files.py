import os
import tempfile
import unittest

from snprice.files import atomic_write


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "deep", "a.json")

    def test_writes_text_and_creates_folders(self):
        atomic_write(self.path, "héllo\n")
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), "héllo\n".encode("utf-8"))

    def test_no_temporary_file_is_left_behind(self):
        atomic_write(self.path, "x")
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["a.json"])

    def test_existing_file_is_replaced(self):
        atomic_write(self.path, "old")
        atomic_write(self.path, "new")
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "new")

    def test_transient_lock_on_windows_is_retried(self):
        # antivirus or the search indexer can hold a freshly written file for a moment
        calls, slept = [], []

        def flaky_replace(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(32, "The process cannot access the file")
            os.replace(src, dst)

        atomic_write(self.path, "x", replace=flaky_replace, sleep=slept.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(slept), 2)
        with open(self.path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "x")

    def test_persistent_lock_raises(self):
        def always_locked(src, dst):
            raise PermissionError(32, "locked")

        with self.assertRaises(PermissionError):
            atomic_write(self.path, "x", replace=always_locked, sleep=lambda s: None, tries=3)


if __name__ == "__main__":
    unittest.main()
