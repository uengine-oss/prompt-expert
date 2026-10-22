import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from winwhisper import pathmenu


class RememberTest(unittest.TestCase):
    def test_new_path_goes_first(self):
        rows = pathmenu.remember([{"id": "a", "path": r"C:\a"}], r"C:\b")
        self.assertEqual([r["path"] for r in rows], [r"C:\b", r"C:\a"])

    def test_duplicate_moves_to_front_and_keeps_id(self):
        rows = [{"id": "a", "path": r"C:\a"}, {"id": "b", "path": r"C:\b"}]
        rows = pathmenu.remember(rows, r"C:\b")
        self.assertEqual(rows, [{"id": "b", "path": r"C:\b"}, {"id": "a", "path": r"C:\a"}])

    def test_keeps_ten(self):
        rows = []
        for i in range(15):
            rows = pathmenu.remember(rows, rf"C:\f{i}")
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]["path"], r"C:\f14")


class NormalizeTest(unittest.TestCase):
    def test_drive_root_and_background_suffix(self):
        self.assertEqual(pathmenu.normalize("C:\\."), "C:\\")
        self.assertEqual(pathmenu.normalize(r"C:\Users\ww\."), r"C:\Users\ww")

    def test_file_kept_verbatim(self):
        path = r"C:\공백 있는 폴더\한글 & 이름.txt"
        self.assertEqual(pathmenu.normalize(path), path)

    def test_unc_path(self):
        self.assertEqual(pathmenu.normalize(r"\\server\share\doc.txt"), r"\\server\share\doc.txt")

    def test_relative_rejected(self):
        with self.assertRaises(ValueError):
            pathmenu.normalize(r"relative\file.txt")


class LabelTest(unittest.TestCase):
    def test_name_then_parent_with_ampersand_escaped(self):
        self.assertEqual(pathmenu.menu_label(r"C:\R&D\a&b.txt"), r"a&&b.txt - C:\R&&D")

    def test_drive_root(self):
        self.assertEqual(pathmenu.menu_label("C:\\"), "C:\\")

    def test_long_parts_are_shortened(self):
        label = pathmenu.menu_label("C:\\" + "p" * 40 + "\\" + "n" * 60 + ".txt")
        name, parent = label.split(" - ")
        self.assertEqual(len(name), 30 + 3 + 14)
        self.assertTrue(parent.endswith("..."))


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"APPDATA": str(root / "roaming"),
                                                "LOCALAPPDATA": str(root / "local")})
        self.env.start()
        self.legacy = root / "local" / "CopyPath" / "history.json"
        self.legacy.parent.mkdir(parents=True)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_imports_legacy_copypath_history(self):
        # PowerShell's ConvertTo-Json writes a bare object for a single entry.
        self.legacy.write_text(json.dumps({"Id": "x1", "Path": r"C:\old.txt"}), encoding="utf-8-sig")
        self.assertEqual(pathmenu.load_history(), [{"id": "x1", "path": r"C:\old.txt"}])

    def test_own_history_wins_and_round_trips(self):
        self.legacy.write_text(json.dumps([{"Id": "x1", "Path": r"C:\old.txt"}]), encoding="utf-8")
        rows = [{"id": "n1", "path": r"C:\새 폴더"}]
        pathmenu.save_history(rows)
        self.assertEqual(pathmenu.load_history(), rows)


if __name__ == "__main__":
    unittest.main()
