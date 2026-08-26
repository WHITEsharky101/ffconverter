"""Unit tests for ffcore/crf_select.py — CRF autotune pure logic.

2026-08-24 feature: CRF selection menu "manual / autotune by metrics".
Autotune = integer bisection over CRF [14, 19] on 3 samples (head +30 s,
middle, tail -30 s) of the first selected episode, gated by
PSNR >= 50 AND SSIM >= 0.98 AND VMAF >= 96 per sample (user-mandated
2026-08-24).

Run: python3 -m unittest tests.test_crf_select -v
"""
import json
import os
import tempfile
import unittest

from ffcore import crf_select as cs


class SamplePointsTest(unittest.TestCase):
    def test_75s_three_offset_points(self):
        self.assertEqual(cs.sample_points(75.0),
                         [(30.0, 5), (35.0, 5), (40.0, 5)])

    def test_short_episode_loses_start_offset(self):
        # duration < 60 s -> head starts from 0; tail = duration - 35
        self.assertEqual(cs.sample_points(40.0),
                         [(0.0, 5), (5.0, 5), (17.5, 5)])

    def test_very_short_dedups_head_and_tail(self):
        self.assertEqual(cs.sample_points(20.0),
                         [(0.0, 5), (7.5, 5)])

    def test_six_seconds_two_points(self):
        self.assertEqual(cs.sample_points(6.0),
                         [(0.0, 5), (0.5, 5)])

    def test_too_short_empty(self):
        self.assertEqual(cs.sample_points(5.0), [])
        self.assertEqual(cs.sample_points(2.5), [])

    def test_points_stay_inside_file(self):
        for duration in (6.1, 10.0, 59.9, 60.0, 61.0, 300.0):
            for ss, dur in cs.sample_points(duration):
                self.assertGreaterEqual(ss, 0.0, duration)
                self.assertLessEqual(ss + dur, duration, duration)


class SelectModelTest(unittest.TestCase):
    def test_1080p_model(self):
        self.assertEqual(cs.select_model(1920), "vmaf_v0.6.1.json")
        self.assertEqual(cs.select_model(3839), "vmaf_v0.6.1.json")

    def test_4k_model(self):
        self.assertEqual(cs.select_model(3840), "vmaf_4k_v0.6.1.json")
        self.assertEqual(cs.select_model(4096), "vmaf_4k_v0.6.1.json")


class SearchCrfTest(unittest.TestCase):
    def search(self, predicate, lo=cs.CRF_MIN, hi=cs.CRF_MAX):
        calls = []

        def eval_(crf):
            calls.append(crf)
            return predicate(crf)

        return cs.search_crf(eval_, lo=lo, hi=hi), calls

    def test_all_pass_gives_max(self):
        crf, _ = self.search(lambda c: True)
        self.assertEqual(crf, 19)

    def test_all_fail_gives_none(self):
        crf, _ = self.search(lambda c: False)
        self.assertIsNone(crf)

    def test_threshold_15(self):
        crf, _ = self.search(lambda c: c <= 15)
        self.assertEqual(crf, 15)

    def test_only_min_passes(self):
        crf, _ = self.search(lambda c: c == 14)
        self.assertEqual(crf, 14)

    def test_at_most_five_evaluations_no_repeats(self):
        for threshold in (None, 14, 15, 16, 17, 18, 19):
            _, calls = self.search(
                lambda c: threshold is None or c <= threshold)
            self.assertLessEqual(len(calls), 5, threshold)
            self.assertEqual(len(calls), len(set(calls)), calls)

    def test_custom_bounds(self):
        crf, _ = self.search(lambda c: True, lo=14, hi=15)
        self.assertEqual(crf, 15)


class GateFailuresTest(unittest.TestCase):
    def test_all_pass(self):
        self.assertEqual(cs.gate_failures(56.4, 0.9996, 99.3), [])

    def test_single_failure_named(self):
        self.assertEqual(cs.gate_failures(56.4, 0.9996, 95.0),
                         ["VMAF 95.0"])

    def test_multiple_failures(self):
        self.assertEqual(cs.gate_failures(49.0, 0.97, 90.0),
                         ["PSNR 49.0", "SSIM 0.9700", "VMAF 90.0"])

    def test_boundary_values_pass(self):
        self.assertEqual(cs.gate_failures(50.0, 0.98, 96.0), [])


class ParsePsnrLogTest(unittest.TestCase):
    def test_last_line_wins(self):
        text = "n:1 psnr_avg:48.47\nn:2 psnr_avg:42.88\n"
        self.assertEqual(cs.parse_psnr_log(text), 42.88)

    def test_real_log_line(self):
        text = ("n:180 mse_avg:2.33 mse_y:2.31 mse_u:2.72 mse_v:2.05 "
                "psnr_avg:44.45 psnr_y:44.50 psnr_u:43.78 psnr_v:45.02")
        self.assertEqual(cs.parse_psnr_log(text), 44.45)

    def test_empty(self):
        self.assertIsNone(cs.parse_psnr_log(""))


class ParseSsimLogTest(unittest.TestCase):
    def test_last_line_all_column(self):
        text = ("n:1 Y:0.994717 U:0.997264 V:0.998691 All:0.995804 (23.771609)\n"
                "n:2 Y:0.992108 U:0.996280 V:0.998267 All:0.993830 (22.097211)\n")
        self.assertAlmostEqual(cs.parse_ssim_log(text), 0.993830)

    def test_empty(self):
        self.assertIsNone(cs.parse_ssim_log(""))


class ParseVmafJsonTest(unittest.TestCase):
    def test_mean_and_min(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"pooled_metrics":
                           {"vmaf": {"mean": 99.363845, "min": 97.153845}}}, f)
            self.assertEqual(cs.parse_vmaf_json(path),
                             (99.363845, 97.153845))

    def test_broken_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.json")
            open(path, "w").close()
            self.assertIsNone(cs.parse_vmaf_json(path))

    def test_missing_file(self):
        self.assertIsNone(cs.parse_vmaf_json("/nonexistent/v.json"))


class SampleEncodeCommandTest(unittest.TestCase):
    def test_exact_command(self):
        cmd = cs.sample_encode_command(
            "/m/Show S01E01.mp4", 30.0, 5, "/w/enc.mp4",
            ["-c:v", "libx265", "-vtag", "hvc1", "-pix_fmt", "yuv420p"],
            16, "asm=avx512:aq-mode=3:row-mt=1")
        self.assertEqual(cmd, [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", "30", "-t", "5", "-i", "/m/Show S01E01.mp4",
            "-c:v", "libx265", "-vtag", "hvc1", "-pix_fmt", "yuv420p",
            "-preset", "slow", "-crf", "16",
            "-x265-params", "asm=avx512:aq-mode=3:row-mt=1",
            "-an", "-f", "mp4", "/w/enc.mp4", "-y"])

    def test_fractional_ss(self):
        cmd = cs.sample_encode_command("/m/v.mp4", 17.5, 5, "/w/e.mp4",
                                       ["-c:v", "libx265"], 14, "aq-mode=3")
        i = cmd.index("-ss")
        self.assertEqual(cmd[i:i + 2], ["-ss", "17.5"])


class MeasureCommandTest(unittest.TestCase):
    def cmd(self):
        return cs.measure_command("/w/enc.mp4", "/m/v.mp4", 30.0, 5, "/w",
                                  "/repo/vmaf/vmaf_v0.6.1.json")

    def test_splits_and_three_metrics(self):
        cmd = self.cmd()
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("split=3", fc)
        self.assertIn("psnr=stats_file=/w/p.log[n0]", fc)
        self.assertIn("ssim=stats_file=/w/s.log[n1]", fc)
        self.assertIn("libvmaf=model=path=/repo/vmaf/vmaf_v0.6.1.json", fc)
        self.assertIn("log_fmt=json:log_path=/w/v.json", fc)
        # encoded clip (input 0) is taken whole; the reference window is cut
        # from the ORIGINAL (input 1) via -ss/-t placed before the second -i
        self.assertEqual(cmd[:6],
                         ["ffmpeg", "-hide_banner", "-loglevel", "error",
                          "-i", "/w/enc.mp4"])
        self.assertEqual(cmd[6:10], ["-ss", "30", "-t", "5"])
        self.assertEqual(cmd[10:12], ["-i", "/m/v.mp4"])
        self.assertEqual(cmd[-2:], ["null", "-"])
        for label in ("[n0]", "[n1]", "[n2]"):
            self.assertIn(label, cmd)

    def test_fractional_ss(self):
        cmd = cs.measure_command("/w/e.mp4", "/m/v.mp4", 17.5, 5, "/w",
                                 "/m/model.json")
        i = cmd.index("-ss")
        self.assertEqual(cmd[i:i + 2], ["-ss", "17.5"])

    def test_special_chars_in_paths_are_escaped(self):
        # 2026-08-26 user run: episode dir "Mushoku Tensei S03
        # [Дубляжная, AniStar]" — [ ] and , are filtergraph syntax, so the
        # raw path in -filter_complex breaks the parse ("Trailing garbage
        # after a filter"). Paths inside the filtergraph must be escaped;
        # argv inputs (-i) stay raw (verified against real ffmpeg 9.0.1 +
        # libvmaf: escaped -> rc 0 + v.json, unescaped -> parse error).
        w = "/d/Show S03 [Дубляжная, AniStar]/.tmp"
        m = "/d/vmaf/vmaf_v0.6.1.json"
        cmd = cs.measure_command("/e.mp4", "/v.mp4", 30.0, 5, w, m)
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn(
            r"stats_file=/d/Show S03 \[Дубляжная\, AniStar\]/.tmp/p.log[n0]", fc)
        self.assertIn(
            r"log_path=/d/Show S03 \[Дубляжная\, AniStar\]/.tmp/v.json[n2]", fc)
        # raw (unescaped) path must NOT appear inside the filtergraph
        self.assertNotIn("stats_file=/d/Show S03 [", fc)
        # argv inputs are passed to the OS, not the filtergraph parser
        self.assertIn("/e.mp4", cmd)
        self.assertNotIn("\\", cmd[cmd.index("-i") + 1])

    def test_windows_style_path_is_escaped_for_filtergraph(self):
        # Independent review (2026-08-26): the option value passes through
        # TWO av_get_token unescape layers, so the minimal backslash counts
        # differ per char (verified empirically, ffmpeg 7.1 + 9.0.1):
        #   backslash -> 4, colon -> 2, quote -> 3, ,;[] -> 1, rest -> 0.
        # The old scheme (2 for backslash, 0 for colon, 1 for quote) broke
        # every Windows drive-letter path in -filter_complex parsing.
        w = "C:" + chr(92) + "My " + chr(39) + "Shows" + chr(92) + "S01 [Ani, Dub]" + chr(92) + ".tmp"
        m = "C:" + chr(92) + "vmaf" + chr(92) + "vmaf_v0.6.1.json"
        cmd = cs.measure_command("/e.mp4", "/v.mp4", 30.0, 5, w, m)
        fc = cmd[cmd.index("-filter_complex") + 1]
        BS = chr(92)
        # backslash -> 4, colon -> 2, quote -> 3, [ ] , -> 1 each
        self.assertIn(
            "stats_file=" + "C" + BS * 2 + ":" + BS * 4 + "My " + BS * 3 + "'" +
            "Shows" + BS * 4 + "S01 " + BS + "[Ani" + BS + ", Dub" + BS + "]" +
            BS * 4 + ".tmp/p.log[n0]",
            fc)
        self.assertIn(
            "model=path=" + "C" + BS * 2 + ":" + BS * 4 + "vmaf" + BS * 4 +
            "vmaf_v0.6.1.json:log_fmt=json",
            fc)
        # argv inputs are passed to the OS, not the filtergraph parser
        self.assertIn("/e.mp4", cmd)
        self.assertNotIn(BS, cmd[cmd.index("-i") + 1])


if __name__ == "__main__":
    unittest.main()
