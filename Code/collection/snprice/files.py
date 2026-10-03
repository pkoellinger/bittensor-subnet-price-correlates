"""Atomic file writes that tolerate the short file locks Windows tools impose."""
import os
import time


def atomic_write(path, text, tries=8, sleep=time.sleep, replace=os.replace):
    """Write `text` (UTF-8, "\\n" line ends) to `path` via a temporary file and a rename.

    On Windows an antivirus scanner or the search indexer can hold a freshly written
    file for a moment, which makes the rename fail with PermissionError. The rename is
    retried a few times before giving up.
    """
    path = str(path)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    for attempt in range(tries):
        try:
            replace(tmp, path)
            return
        except PermissionError:
            if attempt == tries - 1:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            sleep(0.25 * (attempt + 1))
