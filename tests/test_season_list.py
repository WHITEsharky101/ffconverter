"""Unit tests for the season selection list in create_ffmpeg_config.

Covers _parse_season_note (pure), list_seasons (real temp dirs) and the
season block of prompt_user_for_media (integration, mocked
find_media_folder). Bracket notes are shown verbatim — no splitting or
filtering (user directive).

Stdlib unittest + tempfile + unittest.mock only.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

import create_ffmpeg_config as cfc


NAME = "Fushigi no umi no Nadia"


def make_season_dir(tmp, name, season_dir):
    """Create <tmp>/<name>/<season_dir>/."""
    path = os.path.join(tmp, name, season_dir)
    os.makedirs(path)
    return path


class ParseSeasonNoteTest(unittest.TestCase):
    """_parse_season_note: first [...] content verbatim, '' when absent."""

    def test_dub_list_verbatim(self):
        self.assertEqual(
            cfc._parse_season_note("Name S01 [Anidub, AniLibria]"),
            "Anidub, AniLibria",
        )

    def test_sub_marker_not_filtered(self):
        self.assertEqual(cfc._parse_season_note("Name S02 [Sub]"), "Sub")

    def test_no_brackets(self):
        self.assertEqual(cfc._parse_season_note("Name S03"), "")

    def test_first_bracket_pair_only(self):
        self.assertEqual(
            cfc._parse_season_note("Name S04 [Anidub, Vid, Rus] [extra]"),
            "Anidub, Vid, Rus",
        )


class ListSeasonsTest(unittest.TestCase):
    """list_seasons: [(digits, note), ...] sorted by season number."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_season_with_dubs(self):
        make_season_dir(self.tmp, NAME, f"{NAME} S01 [Anidub, AniLibria]")
        self.assertEqual(
            cfc.list_seasons(f"{NAME}/", NAME),
            [("01", "Anidub, AniLibria")],
        )

    def test_two_seasons_one_plain_sorted(self):
        make_season_dir(self.tmp, NAME, f"{NAME} S02 [Sub]")
        make_season_dir(self.tmp, NAME, f"{NAME} S01 [Anidub]")
        self.assertEqual(
            cfc.list_seasons(f"{NAME}/", NAME),
            [("01", "Anidub"), ("02", "Sub")],
        )

    def test_same_season_folders_keep_first_note(self):
        make_season_dir(self.tmp, NAME, f"{NAME} S01")
        make_season_dir(self.tmp, NAME, f"{NAME} S01 [Anidub]")
        self.assertEqual(
            cfc.list_seasons(f"{NAME}/", NAME),
            [("01", "Anidub")],
        )

    def test_no_season_folders(self):
        os.makedirs(os.path.join(self.tmp, NAME))
        self.assertEqual(cfc.list_seasons(f"{NAME}/", NAME), [])

    def test_unreadable_base(self):
        self.assertEqual(
            cfc.list_seasons(os.path.join(self.tmp, "missing"), NAME), []
        )


class PromptUserForMediaSeasonListTest(unittest.TestCase):
    """prompt_user_for_media: numbered season list with verbatim notes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        make_season_dir(self.tmp, NAME, f"{NAME} S01 [Anidub, AniLibria]")
        make_season_dir(self.tmp, NAME, f"{NAME} S02 [Sub]")
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_picks_season_from_list(self):
        inputs = iter([NAME, "2"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc, "find_media_folder",
                    side_effect=[(f"{NAME} S02 [Sub]", [])],
                ) as m:
            base_path, media_folder, audio_tags, name, season = (
                cfc.prompt_user_for_media()
            )
        self.assertEqual(name, NAME)
        self.assertEqual(base_path, f"{NAME}/")
        self.assertEqual(season, "02")
        self.assertEqual(m.call_count, 1)
        self.assertEqual(m.call_args_list[0].args, (f"{NAME}/", NAME, "02"))

    def test_list_prints_verbatim_notes(self):
        import io
        buf = io.StringIO()
        inputs = iter([NAME, "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc, "find_media_folder",
                    side_effect=[(f"{NAME} S01 [Anidub, AniLibria]", [])],
                ), \
                mock.patch("sys.stdout", new=buf):
            cfc.prompt_user_for_media()
        out = buf.getvalue()
        self.assertIn("1: S01 [Anidub, AniLibria]", out)
        self.assertIn("2: S02 [Sub]", out)

    def test_no_matching_season_folders_free_form_fallback(self):
        # A media whose season folders don't follow the "<name> SNN" prefix
        # keeps the old free-form season input (default 1).
        shutil.rmtree(os.path.join(self.tmp, NAME))
        odd_media = "Nadia Media"
        make_season_dir(self.tmp, odd_media, "Nadia S01")
        inputs = iter([odd_media, ""])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc, "find_media_folder",
                    side_effect=[("Nadia S01", [])],
                ) as m:
            base_path, media_folder, audio_tags, name, season = (
                cfc.prompt_user_for_media()
            )
        self.assertEqual(name, odd_media)
        self.assertEqual(season, "01")
        self.assertEqual(m.call_args_list[0].args, (f"{odd_media}/", odd_media, "01"))


if __name__ == "__main__":
    unittest.main()
