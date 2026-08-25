"""Unit tests for media name search in create_ffmpeg_config.

Covers find_media_candidates (pure, no I/O prompts),
select_media_name (interactive, mocked input) and
prompt_user_for_media (integration, mocked find_media_folder).

Stdlib unittest + tempfile + unittest.mock only.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import create_ffmpeg_config as cfc


MEDIA_NAMES = [
    "Blue Lock",
    "Blue Archive",
    "Blue Period",
    "Blue Lock Extra",
    "Grand Blue",
]


def make_media_dir(tmp, name):
    """Create <tmp>/<name>/<name> S01/ (the layout find_media_folder expects)."""
    season = os.path.join(tmp, name, f"{name} S01")
    os.makedirs(season)
    return season


class FindMediaCandidatesTest(unittest.TestCase):
    """find_media_candidates: case-insensitive substring, junk filtered."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        for name in MEDIA_NAMES:
            make_media_dir(self.tmp, name)
        # Junk dir without a season subfolder must never be a candidate.
        os.makedirs(os.path.join(self.tmp, "docs"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_exact_case_insensitive(self):
        # "blue lock" is a substring of both "Blue Lock" and "Blue Lock Extra".
        self.assertEqual(
            cfc.find_media_candidates("BLUE LOCK", self.tmp),
            ["Blue Lock", "Blue Lock Extra"],
        )

    def test_single_substring(self):
        self.assertEqual(
            cfc.find_media_candidates("archive", self.tmp), ["Blue Archive"]
        )

    def test_multiple_sorted_by_lower_name(self):
        self.assertEqual(
            cfc.find_media_candidates("blu", self.tmp),
            [
                "Blue Archive",
                "Blue Lock",
                "Blue Lock Extra",
                "Blue Period",
                "Grand Blue",
            ],
        )

    def test_empty_query_lists_all_media(self):
        self.assertEqual(cfc.find_media_candidates("", self.tmp), sorted(MEDIA_NAMES))

    def test_junk_dir_excluded(self):
        self.assertEqual(cfc.find_media_candidates("doc", self.tmp), [])

    def test_path_like_query_no_match(self):
        self.assertEqual(cfc.find_media_candidates("2024/Blue Lock", self.tmp), [])

    def test_nonexistent_base_returns_empty(self):
        self.assertEqual(
            cfc.find_media_candidates("blu", os.path.join(self.tmp, "no-such-dir")), []
        )


class SelectMediaNameTest(unittest.TestCase):
    """select_media_name: exact/single auto-pick, multiple -> numbered list, zero -> None."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        for name in MEDIA_NAMES:
            make_media_dir(self.tmp, name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_exact_case_insensitive_no_prompt(self):
        with mock.patch("builtins.input", side_effect=AssertionError("no prompt")):
            self.assertEqual(cfc.select_media_name("blue lock", self.tmp), "Blue Lock")

    def test_single_match_no_prompt(self):
        with mock.patch("builtins.input", side_effect=AssertionError("no prompt")):
            self.assertEqual(cfc.select_media_name("archive", self.tmp), "Blue Archive")

    def test_multiple_match_picks_number(self):
        with mock.patch("builtins.input", return_value="4"):
            self.assertEqual(cfc.select_media_name("blu", self.tmp), "Blue Period")

    def test_multiple_match_invalid_input_retries(self):
        inputs = iter(["abc", "0", "99", "2"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)):
            self.assertEqual(cfc.select_media_name("blu", self.tmp), "Blue Lock")

    def test_zero_match_returns_none(self):
        with mock.patch("builtins.input", side_effect=AssertionError("no prompt")):
            self.assertIsNone(cfc.select_media_name("zzz", self.tmp))


class PromptUserForMediaTest(unittest.TestCase):
    """prompt_user_for_media: 0 matches -> error + re-prompt (user directive)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        for name in MEDIA_NAMES:
            make_media_dir(self.tmp, name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_zero_match_reprompts_then_resolves(self):
        # The script assumes CWD = media root; run the search in the temp dir.
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.tmp)
        inputs = iter(["zzz", "blu", "4", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Period S01", [])],
                ) as m:
            base_path, media_folder, audio_tags, name, season = (
                cfc.prompt_user_for_media()
            )
        self.assertEqual(name, "Blue Period")
        self.assertEqual(base_path, "Blue Period/")
        self.assertEqual(media_folder, "Blue Period S01")
        self.assertEqual(season, "01")
        # find_media_folder is called once, after search resolved the name.
        self.assertEqual(m.call_count, 1)
        self.assertEqual(m.call_args_list[0].args, ("Blue Period/", "Blue Period", "01"))

    def test_run_from_foreign_dir_prompts_for_library_root(self):
        # Source code moved above the library root: CWD has no media folders,
        # so the wizard asks for the library root first, then resolves the
        # name inside it (absolute base_path).
        self._outside = tempfile.TemporaryDirectory()
        self.addCleanup(self._outside.cleanup)
        self._settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._settings_dir.cleanup)
        self._settings_patch = mock.patch.object(
            cfc, "SETTINGS_FILE",
            os.path.join(self._settings_dir.name, "settings.json"),
        )
        self._settings_patch.start()
        self.addCleanup(self._settings_patch.stop)
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self._outside.name)
        inputs = iter([self.tmp, "Blue Period", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Period S01", [])],
                ):
            base_path, media_folder, audio_tags, name, season = (
                cfc.prompt_user_for_media()
            )
        self.assertEqual(name, "Blue Period")
        self.assertEqual(base_path, os.path.join(self.tmp, "Blue Period") + "/")
        self.assertEqual(media_folder, "Blue Period S01")
        self.assertEqual(season, "01")

    def test_run_from_foreign_dir_bad_root_reprompts(self):
        # A root without media folders is rejected; the second attempt wins.
        self._outside = tempfile.TemporaryDirectory()
        self.addCleanup(self._outside.cleanup)
        self._settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._settings_dir.cleanup)
        self._settings_patch = mock.patch.object(
            cfc, "SETTINGS_FILE",
            os.path.join(self._settings_dir.name, "settings.json"),
        )
        self._settings_patch.start()
        self.addCleanup(self._settings_patch.stop)
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self._outside.name)
        inputs = iter([os.path.join(self._outside.name, "nope"), self.tmp, "archive", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Archive S01", [])],
                ):
            base_path, _, _, name, season = cfc.prompt_user_for_media()
        self.assertEqual(name, "Blue Archive")
        self.assertEqual(base_path, os.path.join(self.tmp, "Blue Archive") + "/")
        self.assertEqual(season, "01")


class PromptLibraryRootTest(unittest.TestCase):
    """prompt_library_root: entered root persisted to settings.json.

    Empty input -> saved directory; entered path -> new directory (saved).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        for name in MEDIA_NAMES:
            make_media_dir(self.tmp, name)

    def tearDown(self):
        self._tmp.cleanup()

    def _setup_outside(self):
        """chdir into an empty dir (no media in CWD) + tmp settings.json."""
        self._outside = tempfile.TemporaryDirectory()
        self.addCleanup(self._outside.cleanup)
        self._settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._settings_dir.cleanup)
        self._settings_patch = mock.patch.object(
            cfc, "SETTINGS_FILE",
            os.path.join(self._settings_dir.name, "settings.json"),
        )
        self._settings_patch.start()
        self.addCleanup(self._settings_patch.stop)
        self.settings_path = os.path.join(self._settings_dir.name, "settings.json")
        old_cwd = os.getcwd()
        self.addCleanup(os.chdir, old_cwd)

    def _write_saved_root(self, root):
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump({"library_root": root}, f, ensure_ascii=False, indent=2)

    def test_entered_root_is_persisted(self):
        self._setup_outside()
        os.chdir(self._outside.name)
        inputs = iter([self.tmp, "Blue Period", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Period S01", [])],
                ):
            base_path, _, _, name, _ = cfc.prompt_user_for_media()
        self.assertEqual(name, "Blue Period")
        with open(self.settings_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"library_root": os.path.abspath(self.tmp)})
        # base_path is resolved against the saved root, not the foreign CWD.
        self.assertEqual(base_path, os.path.join(self.tmp, "Blue Period") + "/")

    def test_empty_input_uses_saved_root(self):
        self._setup_outside()
        os.chdir(self._outside.name)
        self._write_saved_root(self.tmp)
        inputs = iter(["", "Blue Period", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)) as m, \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Period S01", [])],
                ):
            base_path, _, _, name, _ = cfc.prompt_user_for_media()
        # The saved root is used on empty input — the root prompt is
        # asked exactly once (no re-prompt).
        self.assertEqual(name, "Blue Period")
        root_prompts = [
            c for c in m.call_args_list if "корню библиотеки" in str(c.args)
        ]
        self.assertEqual(len(root_prompts), 1)
        self.assertEqual(base_path, os.path.join(self.tmp, "Blue Period") + "/")

    def test_stale_saved_root_reprompts_then_saves_new(self):
        self._setup_outside()
        os.chdir(self._outside.name)
        stale = os.path.join(self._outside.name, "moved-away")
        os.makedirs(stale)
        self._write_saved_root(stale)
        inputs = iter(["", self.tmp, "archive", "1"])
        with mock.patch("builtins.input", side_effect=lambda prompt=None: next(inputs)), \
                mock.patch.object(
                    cfc,
                    "find_media_folder",
                    side_effect=[("Blue Archive S01", [])],
                ):
            base_path, _, _, name, _ = cfc.prompt_user_for_media()
        # Stale saved root is not used silently; the new entry overwrites it.
        self.assertEqual(name, "Blue Archive")
        with open(self.settings_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"library_root": os.path.abspath(self.tmp)})
        self.assertEqual(base_path, os.path.join(self.tmp, "Blue Archive") + "/")

    def test_saved_root_not_used_when_media_in_cwd(self):
        # Classic path: media in CWD -> "." without a prompt; settings untouched.
        self._setup_outside()
        os.chdir(self.tmp)
        self._write_saved_root(os.path.join(self.tmp, "unrelated"))
        with mock.patch("builtins.input", side_effect=AssertionError("no prompt")):
            self.assertEqual(cfc.prompt_library_root(), ".")
        # The file must keep the old saved root (no overwrite, no delete).
        with open(self.settings_path, encoding="utf-8") as f:
            self.assertEqual(
                json.load(f), {"library_root": os.path.join(self.tmp, "unrelated")}
            )


if __name__ == "__main__":
    unittest.main()
