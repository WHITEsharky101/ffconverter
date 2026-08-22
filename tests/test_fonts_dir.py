"""Unit tests for find_ttf_in_fonts() in create_ffmpeg_config.py.

2026-08-22 fix (user item 10): the function created a 'fonts/' directory
in the media tree even when there was no font archive, crashed with
FileNotFoundError on a missing subtitle folder, and — because
os.path.join(base, "/") == "/" on POSIX — walked the filesystem root
for a subtitle stream with the "/" path (meaning: the season dir itself).

New contract:
- stream.path "" or "/"  -> search the base (season) directory
- missing search dir     -> return the stream untouched, no side effects
- fonts/ is created ONLY when a font archive is actually found
- real font archive      -> extracted, fonts collected (regression guard)

Run: python3 -m unittest tests.test_fonts_dir -v
"""

import io
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

import create_ffmpeg_config as cfc


def make_stream(path):
    return cfc.AudioSubStream(
        stream=0, index=0, type="s", path=path,
        fonts=[], lang="rus", title="Полные", codec="",
    )


class FindTtfInFontsTest(unittest.TestCase):
    NAME = "Show"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.base = os.path.join(self.tmp, self.NAME)
        self.subs = os.path.join(self.base, "Subs")
        os.makedirs(self.subs)
        # one episode file so the folder looks real
        open(os.path.join(self.subs, "Show S01E01.ass"), "w").close()

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_font_archive_no_fonts_dir_created(self):
        """Item 10: no archive -> no fonts/ directory, empty fonts."""
        stream = make_stream("Subs")
        result = cfc.find_ttf_in_fonts(self.base, stream)
        self.assertEqual(result.fonts, [])
        self.assertFalse(os.path.isdir(os.path.join(self.subs, "fonts")))

    def test_missing_folder_returns_untouched(self):
        """Missing subtitle folder -> no crash, no side effects."""
        stream = make_stream("NoSuchDir")
        result = cfc.find_ttf_in_fonts(self.base, stream)
        self.assertEqual(result.fonts, [])
        self.assertEqual(result.path, "NoSuchDir")
        self.assertFalse(os.path.isdir(os.path.join(self.base, "NoSuchDir")))

    def test_slash_path_searches_base_not_root(self):
        """'/' means the season dir itself (like get_media_ext/input files)."""
        stream = make_stream("/")
        walked = []

        def fake_walk(top, *a, **kw):
            walked.append(top)
            return iter([])

        with mock.patch.object(cfc.os, "walk", side_effect=fake_walk), \
                mock.patch.object(cfc.os, "listdir", return_value=[]):
            result = cfc.find_ttf_in_fonts(self.base, stream)
        self.assertEqual(result.fonts, [])
        self.assertTrue(all(w != "/" for w in walked),
                        f"walked the filesystem root: {walked}")
        self.assertTrue(all(w.startswith(self.tmp) for w in walked),
                        f"walked outside the media tree: {walked}")

    def test_zip_with_ttf_is_extracted_and_collected(self):
        """Real font archive -> fonts/ created, ttf extracted (regression)."""
        archive = os.path.join(self.subs, "fonts.zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("MingGothic.ttf", b"fake-ttf-bytes")
        stream = make_stream("Subs")
        result = cfc.find_ttf_in_fonts(self.base, stream)
        self.assertTrue(
            any(f.endswith("MingGothic.ttf") for f in result.fonts),
            f"fonts not collected: {result.fonts}",
        )
        self.assertTrue(os.path.isfile(os.path.join(self.subs, "fonts", "MingGothic.ttf")))

    def test_existing_fonts_folder_without_archive_not_touched(self):
        """A pre-existing fonts/ dir with a ttf is found, nothing new created."""
        fonts_dir = os.path.join(self.subs, "fonts")
        os.makedirs(fonts_dir)
        open(os.path.join(fonts_dir, "MingGothic.ttf"), "w").close()
        stream = make_stream("Subs")
        result = cfc.find_ttf_in_fonts(self.base, stream)
        self.assertTrue(any(f.endswith("MingGothic.ttf") for f in result.fonts))


if __name__ == "__main__":
    unittest.main()
