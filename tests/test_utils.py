import gzip
import logging
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from zipfile import BadZipFile, ZipFile

from context import _utils


class TestPreparePath(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_returns_resolved_path_for_string(self):
        result = _utils.prepare_path(str(self.tmpdir))
        self.assertIsInstance(result, Path)
        self.assertTrue(result.is_absolute())

    def test_returns_resolved_path_for_path(self):
        result = _utils.prepare_path(self.tmpdir)
        self.assertEqual(result, self.tmpdir.resolve())

    def test_does_not_create_when_is_folder_false(self):
        target = self.tmpdir / "does_not_exist.txt"
        result = _utils.prepare_path(target, is_folder=False)
        self.assertEqual(result, target.resolve())
        self.assertFalse(result.exists())

    def test_creates_folder_when_is_folder_true(self):
        target = self.tmpdir / "new" / "nested" / "dir"
        result = _utils.prepare_path(target, is_folder=True)
        self.assertTrue(result.is_dir())

    def test_existing_folder_ok_when_is_folder_true(self):
        result = _utils.prepare_path(self.tmpdir, is_folder=True)
        self.assertEqual(result, self.tmpdir.resolve())

    def test_raises_when_is_folder_true_and_file_exists(self):
        target = self.tmpdir / "file.txt"
        target.write_text("hello")
        with self.assertRaises(NotADirectoryError):
            _utils.prepare_path(target, is_folder=True)

    def test_raises_when_is_folder_true_and_symlink_to_file(self):
        real_file = self.tmpdir / "real.txt"
        real_file.write_text("data")
        link = self.tmpdir / "link.txt"
        link.symlink_to(real_file)

        with self.assertRaises(NotADirectoryError):
            _utils.prepare_path(link, is_folder=True)

    def test_broken_symlink_creates_target_dir(self):
        link = self.tmpdir / "broken_link"
        target = self.tmpdir / "target_dir"
        link.symlink_to(target)

        result = _utils.prepare_path(link, is_folder=True)
        self.assertTrue(result.is_dir())
        # resolved path is the target, not the link
        self.assertEqual(result, target.resolve())

    def test_expanduser(self):
        with patch.object(Path, "expanduser", return_value=self.tmpdir) as mock_expand:
            _utils.prepare_path("~/some/path")
            mock_expand.assert_called_once()

    def test_concurrent_mkdir_does_not_raise(self):
        target = self.tmpdir / "concurrent"
        # Two sequential calls should not raise.
        _utils.prepare_path(target, is_folder=True)
        _utils.prepare_path(target, is_folder=True)


class TestConsumeArchive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _make_zip(self, name="test.zip", members=None):
        members = members or {"a.txt": b"alpha", "b.txt": b"beta", "c.txt": b"gamma"}
        zip_path = self.tmpdir / name
        with ZipFile(zip_path, "w") as zf:
            for member_name, content in members.items():
                zf.writestr(member_name, content)
        return zip_path

    def _make_gz(self, name="data.csv.gz", content=b"col1,col2\n1,2\n"):
        gz_path = self.tmpdir / name
        with gzip.open(gz_path, "wb") as f:
            f.write(content)
        return gz_path

    # ---------- zip ----------

    def test_zip_extract_first_member_by_default(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        result = _utils.consume_archive(zip_path, out_dir)

        self.assertEqual(result, out_dir / "a.txt")
        self.assertTrue(result.exists())
        self.assertEqual(result.read_bytes(), b"alpha")
        self.assertFalse(zip_path.exists())

    def test_zip_extract_specific_members_returns_last(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        result = _utils.consume_archive(
            zip_path, out_dir, extract_files=["b.txt", "c.txt"]
        )

        self.assertEqual(result, out_dir / "c.txt")
        self.assertTrue((out_dir / "b.txt").exists())
        self.assertTrue((out_dir / "c.txt").exists())
        self.assertFalse((out_dir / "a.txt").exists())
        self.assertFalse(zip_path.exists())

    def test_zip_single_member_list(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        result = _utils.consume_archive(zip_path, out_dir, extract_files=["b.txt"])
        self.assertEqual(result, out_dir / "b.txt")

    def test_zip_empty_extract_files_raises(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        with self.assertRaises(ValueError):
            _utils.consume_archive(zip_path, out_dir, extract_files=[])

    def test_zip_missing_member_raises_keyerror(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        with self.assertRaises(KeyError):
            _utils.consume_archive(zip_path, out_dir, extract_files=["missing.txt"])
        # Archive should still exist since extraction failed
        self.assertTrue(zip_path.exists())

    def test_bad_zip_raises(self):
        bad = self.tmpdir / "bad.zip"
        bad.write_bytes(b"not a zip file")
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        with self.assertRaises(BadZipFile):
            _utils.consume_archive(bad, out_dir)
        self.assertTrue(bad.exists())

    # ---------- gz ----------

    def test_gz_decompress(self):
        gz_path = self._make_gz()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()
        original_content = b"col1,col2\n1,2\n"

        result = _utils.consume_archive(gz_path, out_dir)

        self.assertEqual(result, out_dir / "data.csv")
        self.assertTrue(result.exists())
        self.assertEqual(result.read_bytes(), original_content)
        self.assertFalse(gz_path.exists())

    def test_gz_multiple_dots_in_name(self):
        gz_path = self._make_gz(name="my.data.csv.gz", content=b"x")
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        result = _utils.consume_archive(gz_path, out_dir)
        self.assertEqual(result.name, "my.data.csv")
        self.assertEqual(result.read_bytes(), b"x")

    # ---------- errors / cleanup ----------

    def test_unknown_suffix_raises(self):
        f = self.tmpdir / "file.tar"
        f.write_bytes(b"data")
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        with self.assertRaises(ValueError):
            _utils.consume_archive(f, out_dir)
        self.assertTrue(f.exists())

    def test_unlink_failure_is_logged_but_file_returned(self):
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            with self.assertLogs(level=logging.ERROR):
                result = _utils.consume_archive(zip_path, out_dir)

        self.assertTrue(result.exists())
        self.assertTrue(zip_path.exists())

    def test_unlink_missing_file_ok(self):
        """FileNotFoundError is a subclass of OSError and is therefore caught."""
        zip_path = self._make_zip()
        out_dir = self.tmpdir / "out"
        out_dir.mkdir()

        original_unlink = Path.unlink

        def unlink_then_raise(self_path, missing_ok=False):
            # emulate file disappearing between unlink call and check
            raise FileNotFoundError(str(self_path))

        with patch.object(Path, "unlink", unlink_then_raise):
            # FileNotFoundError should propagate because the code only
            # catches OSError around unlink. FileNotFoundError IS an OSError
            # subclass, so it is caught — verify no raise.
            with self.assertLogs(level=logging.ERROR):
                result = _utils.consume_archive(zip_path, out_dir)

        self.assertTrue(result.exists())


class TestSplitDateRange(unittest.TestCase):
    def test_single_day(self):
        d = date(2024, 1, 1)
        self.assertEqual(_utils.split_date_range(d, d), [(d, d)])

    def test_exact_chunk(self):
        chunks = _utils.split_date_range(
            date(2024, 1, 1), date(2024, 1, 10), max_chunk_size=5
        )
        self.assertEqual(
            chunks,
            [
                (date(2024, 1, 1), date(2024, 1, 5)),
                (date(2024, 1, 6), date(2024, 1, 10)),
            ],
        )

    def test_remainder_chunk(self):
        chunks = _utils.split_date_range(
            date(2024, 1, 1), date(2024, 1, 8), max_chunk_size=5
        )
        self.assertEqual(
            chunks,
            [
                (date(2024, 1, 1), date(2024, 1, 5)),
                (date(2024, 1, 6), date(2024, 1, 8)),
            ],
        )

    def test_chunk_size_one(self):
        chunks = _utils.split_date_range(
            date(2024, 1, 1), date(2024, 1, 3), max_chunk_size=1
        )
        self.assertEqual(
            chunks,
            [
                (date(2024, 1, 1), date(2024, 1, 1)),
                (date(2024, 1, 2), date(2024, 1, 2)),
                (date(2024, 1, 3), date(2024, 1, 3)),
            ],
        )

    def test_from_greater_than_to_returns_empty(self):
        chunks = _utils.split_date_range(date(2024, 1, 10), date(2024, 1, 1))
        self.assertEqual(chunks, [])

    def test_invalid_max_chunk_size_zero(self):
        with self.assertRaises(ValueError):
            _utils.split_date_range(
                date(2024, 1, 1), date(2024, 1, 2), max_chunk_size=0
            )

    def test_invalid_max_chunk_size_negative(self):
        with self.assertRaises(ValueError):
            _utils.split_date_range(
                date(2024, 1, 1), date(2024, 1, 2), max_chunk_size=-5
            )

    def test_no_overlap_and_contiguous(self):
        chunks = _utils.split_date_range(
            date(2024, 1, 1), date(2024, 12, 31), max_chunk_size=100
        )
        for i in range(len(chunks) - 1):
            prev_end = chunks[i][1]
            next_start = chunks[i + 1][0]
            self.assertEqual(next_start, prev_end + timedelta(days=1))

    def test_covers_full_range(self):
        start, end = date(2023, 6, 15), date(2024, 9, 3)
        chunks = _utils.split_date_range(start, end, max_chunk_size=30)
        self.assertEqual(chunks[0][0], start)
        self.assertEqual(chunks[-1][1], end)
        # verify no gaps and full coverage by counting days
        total_days = sum((c[1] - c[0]).days + 1 for c in chunks)
        self.assertEqual(total_days, (end - start).days + 1)

    def test_default_chunk_size_fits_non_leap_year(self):
        """A non-leap year (365 days inclusive) fits in a single default chunk."""
        chunks = _utils.split_date_range(date(2023, 1, 1), date(2023, 12, 31))
        self.assertEqual(chunks, [(date(2023, 1, 1), date(2023, 12, 31))])

    def test_default_chunk_size_splits_leap_year(self):
        """A leap year (366 days inclusive) spills one day into a second chunk."""
        chunks = _utils.split_date_range(date(2024, 1, 1), date(2024, 12, 31))
        self.assertEqual(
            chunks,
            [
                (date(2024, 1, 1), date(2024, 12, 30)),
                (date(2024, 12, 31), date(2024, 12, 31)),
            ],
        )

    def test_leap_year_boundary(self):
        chunks = _utils.split_date_range(
            date(2024, 2, 27), date(2024, 3, 1), max_chunk_size=2
        )
        self.assertEqual(
            chunks,
            [
                (date(2024, 2, 27), date(2024, 2, 28)),
                (date(2024, 2, 29), date(2024, 3, 1)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
