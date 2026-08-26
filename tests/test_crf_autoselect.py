"""Unit tests for the CRF autoselect driver in ffmpeg_converter.py.

2026-08-24 feature: collect_inputs menu "manual CRF / autotune by
metrics"; autotune = bisection over CRF 14..19 on 3 samples of the first
selected episode, gated PSNR>=50 AND SSIM>=0.98 AND VMAF>=96. Subprocesses
are mocked — only orchestration, cleanup and fallbacks are tested here
(ffcore/crf_select.py unit tests cover the pure logic).

Run: python3 -m unittest tests.test_crf_autoselect -v
"""
import io
import json
import os
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

import ffmpeg_converter
from ffcore.models import FFmpegParam


def make_params(tmp, episodes=("01",)):
    media_dir = os.path.join(tmp, "Show S01")
    os.makedirs(media_dir, exist_ok=True)
    open(os.path.join(media_dir, "Show S01E01.mp4"), "w").close()
    return types.SimpleNamespace(
        name="Show", season="01", path=media_dir,
        video_ext=[".mp4"], audio_ext=[], sub_ext=[],
        flac_convert=False, output_ext=".mp4",
        codec="hevc", bit=8, episodes=list(episodes), sp_episodes=[],
        tune_preset="",
    )


class FakePopen:
    """Popen double for the ffmpeg encode/measure commands.

    .stderr is a line-iterable stream like a real text-mode Popen stderr;
    .wait()/.returncode complete the protocol used by
    ffmpeg_converter._run_cmd.
    """

    def __init__(self, returncode, stderr=""):
        self.returncode = returncode
        self._stderr = stderr

    @property
    def stderr(self):
        return io.StringIO(self._stderr)

    def wait(self):
        return self.returncode


class FakeFfmpeg:
    """Mocks the subprocess layer of run_autoselect_crf.

    .run   — ffprobe (probe) + `ffmpeg -filters` (vmaf preflight) and the
             encode/measure path for code that still uses subprocess.run.
    .popen — encode/measure for code that uses subprocess.Popen (live
             stderr streaming).
    """

    def __init__(self, duration=75.0, width=1920, vmaf_for=None,
                 measure_rc=0, measure_stderr="", has_vmaf=True,
                 avg_frame_rate="24000/1001"):
        self.duration = duration
        self.width = width
        self.avg_frame_rate = avg_frame_rate
        # crf -> vmaf (callables) or None (default 97.0)
        self.vmaf_for = vmaf_for
        self.measure_rc = measure_rc
        self.measure_stderr = measure_stderr
        self.has_vmaf = has_vmaf
        self.last_crf = None
        self.calls = []

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[0] == "ffprobe":
            return self._result(0, out=json.dumps({"streams": [{
                "duration": str(self.duration), "width": self.width,
                "avg_frame_rate": self.avg_frame_rate}]}))
        if cmd[0] == "ffmpeg":
            if "-filters" in cmd:
                return self._result(0, out=self._filters_out())
            if "-x265-params" in cmd:
                self.last_crf = int(cmd[cmd.index("-crf") + 1])
                return self._result(0)
            if "-filter_complex" in cmd:
                self._write_metrics(cmd)
                return self._result(self.measure_rc, err=self.measure_stderr)
        return self._result(0)

    def popen(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[0] == "ffmpeg":
            if "-x265-params" in cmd:
                self.last_crf = int(cmd[cmd.index("-crf") + 1])
                return FakePopen(0)
            if "-filter_complex" in cmd:
                self._write_metrics(cmd)
                return FakePopen(self.measure_rc, self.measure_stderr)
        return FakePopen(0)

    def _filters_out(self):
        # real -filters line format; vmafmotion is always present as the
        # decoy, the libvmaf token only when the filter is "built in"
        lines = [" ... vmafmotion        V->V       Calculate the VMAF Motion score."]
        if self.has_vmaf:
            lines.append(" .. libvmaf           VV->V      (null)")
        return "\n".join(lines) + "\n"

    def _write_metrics(self, cmd):
        # workdir = directory of p.log inside the filter_complex string
        fc = cmd[cmd.index("-filter_complex") + 1]
        plog = fc.split("psnr=stats_file=")[1].split("[")[0]
        workdir = plog.rsplit("/", 1)[0]
        with open(plog, "w", encoding="utf-8") as f:
            f.write("n:1 psnr_avg:55.00\n")
        slog = fc.split("ssim=stats_file=")[1].split("[")[0]
        with open(slog, "w", encoding="utf-8") as f:
            f.write("n:1 Y:0.999 U:0.999 V:0.999 All:0.990000 (10.0)\n")
        vlog = fc.split("log_path=")[1].split("[")[0]
        vmaf = (self.vmaf_for(self.last_crf)
                if self.vmaf_for else 97.0)
        with open(vlog, "w", encoding="utf-8") as f:
            json.dump({"pooled_metrics":
                       {"vmaf": {"mean": vmaf, "min": vmaf - 1}}}, f)

    @staticmethod
    def _result(rc, out="", err=""):
        return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


class FakeSubprocess:
    """(run, popen) pair for run_autoselect — per-test overrides."""
    def __init__(self, run, popen):
        self.run = run
        self.popen = popen


def run_autoselect(params, fake, answers=()):
    """Drive run_autoselect_crf with subprocess mocked; capture stdout."""
    buf = io.StringIO()
    with mock.patch.object(ffmpeg_converter.subprocess, "run", fake.run), \
            mock.patch.object(ffmpeg_converter.subprocess, "Popen",
                              fake.popen), \
            mock.patch("builtins.input", side_effect=list(answers)), \
            redirect_stdout(buf):
        crf = ffmpeg_converter.run_autoselect_crf(params)
    return crf, buf.getvalue()


class ProbeVideoInfoTest(unittest.TestCase):
    def probe(self, rc=0, out=""):
        fake = mock.Mock(return_value=types.SimpleNamespace(
            returncode=rc, stdout=out, stderr=""))
        with mock.patch.object(ffmpeg_converter.subprocess, "run", fake):
            return ffmpeg_converter.probe_video_info("/v.mp4")

    def test_ok(self):
        out = json.dumps({"streams": [{
            "duration": "75.2", "width": 1920,
            "avg_frame_rate": "24000/1001"}]})
        self.assertEqual(self.probe(out=out), (75.2, 1920, "24000/1001"))

    def test_nonzero_rc(self):
        self.assertIsNone(self.probe(rc=1))

    def test_bad_json(self):
        self.assertIsNone(self.probe(out="not json"))

    def test_missing_duration(self):
        out = json.dumps({"streams": [{"width": 1920}]})
        self.assertIsNone(self.probe(out=out))

    def test_mkv_duration_falls_back_to_format_level(self):
        # MKV/Matroska: ffprobe puts NO "duration" on the stream level —
        # only width; the duration lives in format.duration (2026-08-25
        # user report: S03E01.mkv -> {"streams": [{"width": 1920}]}).
        out = json.dumps({"streams": [{"width": 1920}],
                          "format": {"duration": "1420.053000"}})
        fake = mock.Mock(return_value=types.SimpleNamespace(
            returncode=0, stdout=out, stderr=""))
        with mock.patch.object(ffmpeg_converter.subprocess, "run",
                               fake) as run_mock:
            result = ffmpeg_converter.probe_video_info("/v.mkv")
        self.assertEqual(result, (1420.053, 1920, None))
        # single ffprobe call covering both levels
        command = run_mock.call_args[0][0]
        self.assertIn("stream=duration,width,avg_frame_rate"
                      ":format=duration", command)

    def test_probe_requests_avg_frame_rate(self):
        # fps=<rate> normalization needs the source's avg_frame_rate
        # (2026-08-26 timebase desync fix)
        out = json.dumps({"streams": [{
            "duration": "75.2", "width": 1920,
            "avg_frame_rate": "24000/1001"}]})
        fake = mock.Mock(return_value=types.SimpleNamespace(
            returncode=0, stdout=out, stderr=""))
        with mock.patch.object(ffmpeg_converter.subprocess, "run",
                               fake) as run_mock:
            ffmpeg_converter.probe_video_info("/v.mp4")
        command = run_mock.call_args[0][0]
        self.assertIn("stream=duration,width,avg_frame_rate"
                      ":format=duration", command)

    def test_avg_frame_rate_missing_yields_none_rate(self):
        # stream has no avg_frame_rate -> None (measure_command falls
        # back to the un-normalized filtergraph)
        out = json.dumps({"streams": [{
            "duration": "75.2", "width": 1920}]})
        self.assertEqual(self.probe(out=out), (75.2, 1920, None))

    def test_avg_frame_rate_zero_yields_none_rate(self):
        # avg_frame_rate 0/0 (ffprobe before full parse) -> unusable -> None
        out = json.dumps({"streams": [{
            "duration": "75.2", "width": 1920,
            "avg_frame_rate": "0/0"}]})
        self.assertEqual(self.probe(out=out), (75.2, 1920, None))


class AutoselectDriverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.params = make_params(self.tmp.name)
        self.workdir = os.path.join(self.params.path, ".crf_select")

    def test_all_pass_selects_max_crf(self):
        fake = FakeFfmpeg()
        crf, out = run_autoselect(self.params, fake)
        self.assertEqual(crf, 19)
        self.assertIn("Выбранный CRF: 19", out)
        self.assertFalse(os.path.exists(self.workdir),
                         ".crf_select must be removed after the run")
        # bisection: at most 5 encode rounds
        encodes = [c for c in fake.calls if "-x265-params" in c]
        self.assertLessEqual(len(encodes) // 3, 5)

    def test_vmaf_threshold_selects_15(self):
        fake = FakeFfmpeg(vmaf_for=lambda crf: 99 - (crf - 14) * 2)
        crf, out = run_autoselect(self.params, fake)
        # 99, 97, 95, ... -> largest crf with vmaf >= 96 is 15
        self.assertEqual(crf, 19 - 4)
        self.assertIn("Выбранный CRF: 15", out)

    def test_all_fail_asks_and_accepts_14(self):
        fake = FakeFfmpeg(vmaf_for=lambda crf: 90.0)
        crf, out = run_autoselect(self.params, fake, answers=["y"])
        self.assertEqual(crf, 14)
        self.assertIn("не проходит", out)

    def test_all_fail_declines_to_none(self):
        fake = FakeFfmpeg(vmaf_for=lambda crf: 90.0)
        crf, out = run_autoselect(self.params, fake, answers=["n"])
        self.assertIsNone(crf)

    def test_libvmaf_missing(self):
        # the filter is genuinely absent from -filters (only the
        # vmafmotion decoy) -> honest docker hint before any encode
        fake = FakeFfmpeg(has_vmaf=False)
        crf, out = run_autoselect(self.params, fake)
        self.assertIsNone(crf)
        self.assertIn("jrottenberg/ffmpeg", out)
        self.assertFalse(any("-x265-params" in c for c in fake.calls),
                         "preflight must bail before any encode")

    def test_measure_failure_shows_ffmpeg_error(self):
        # libvmaf present but failing to init (model error) must surface
        # the real ffmpeg line, not the canned "no libvmaf" (the old
        # substring heuristic fired on ANY stderr containing "libvmaf")
        fake = FakeFfmpeg(measure_rc=1, measure_stderr=(
            "[libvmaf @ 0x55f3c8a1b200] Could not open model file "
            "'/home/user/vmaf_v0.6.1.json'"))
        crf, out = run_autoselect(self.params, fake)
        self.assertIsNone(crf)
        self.assertIn("Could not open model file", out)
        self.assertNotIn("нет libvmaf", out)

    def test_output_streamed_during_run(self):
        # a successful run streams ffmpeg stderr live: a note line from
        # the measure command must appear in the console output
        fake = FakeFfmpeg(measure_stderr="[libvmaf @ 0x55] note: vmaf ok\n")
        crf, out = run_autoselect(self.params, fake)
        self.assertEqual(crf, 19)
        self.assertIn("[libvmaf @ 0x55] note: vmaf ok", out)

    def test_no_episodes(self):
        self.params.episodes = []
        crf, out = run_autoselect(self.params, FakeFfmpeg())
        self.assertIsNone(crf)
        self.assertIn("Не выбрано эпизодов", out)

    def test_episode_file_missing(self):
        self.params.episodes = ["07"]
        crf, out = run_autoselect(self.params, FakeFfmpeg())
        self.assertIsNone(crf)
        self.assertIn("Не найден файл эпизода", out)
        self.assertIn("CRF вручную", out)

    def test_probe_failure(self):
        fake = FakeFfmpeg()

        def broken_run(cmd, **kw):
            if cmd[0] == "ffprobe":
                return types.SimpleNamespace(returncode=1, stdout="", stderr="")
            return fake.run(cmd, **kw)

        crf, out = run_autoselect(self.params,
                                  FakeSubprocess(broken_run, fake.popen))
        self.assertIsNone(crf)
        self.assertIn("Не удалось определить длительность видео", out)

    def test_short_episode(self):
        fake = FakeFfmpeg(duration=4.0)
        crf, out = run_autoselect(self.params, fake)
        self.assertIsNone(crf)
        self.assertIn("слишком коротк", out)

    def test_missing_vmaf_model(self):
        model_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: os.rmdir(model_dir))
        with mock.patch.object(ffmpeg_converter, "VMAF_DIR", model_dir):
            crf, out = run_autoselect(self.params, FakeFfmpeg())
        self.assertIsNone(crf)
        self.assertIn("VMAF-модель", out)

    def test_workdir_cleaned_on_error(self):
        fake = FakeFfmpeg()

        def boom_run(cmd, **kw):
            if cmd[0] == "ffmpeg" and "-x265-params" in cmd:
                raise OSError("disk full")
            return fake.run(cmd, **kw)

        def boom_popen(cmd, **kw):
            if "-x265-params" in cmd:
                raise OSError("disk full")
            return fake.popen(cmd, **kw)

        crf, out = run_autoselect(self.params,
                                  FakeSubprocess(boom_run, boom_popen))
        self.assertIsNone(crf)
        self.assertIn("Ошибка автоподбора", out)
        self.assertFalse(os.path.exists(self.workdir))

    def test_measure_command_gets_fps_normalization(self):
        # 2026-08-26: probed avg_frame_rate must reach the measure
        # filtergraph as fps=<rate> on BOTH branches (timebase desync
        # fix, validated in docker: min 32.89 -> 91.57, warning gone).
        fake = FakeFfmpeg(avg_frame_rate="24000/1001")
        crf, _ = run_autoselect(self.params, fake)
        self.assertEqual(crf, 19)
        measures = [c for c in fake.calls
                    if c[0] == "ffmpeg" and "-filter_complex" in c]
        self.assertTrue(measures, "no measure command was run")
        for cmd in measures:
            fc = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("[0:v]setpts=PTS-STARTPTS,fps=24000/1001,"
                          "split=3", fc)
            self.assertIn("[1:v]setpts=PTS-STARTPTS,fps=24000/1001,"
                          "split=3", fc)

    def test_measure_command_without_rate_when_probe_yields_none(self):
        # probe with no avg_frame_rate -> rate None -> the old
        # un-normalized filtergraph, run still succeeds
        fake = FakeFfmpeg(avg_frame_rate=None)
        crf, _ = run_autoselect(self.params, fake)
        self.assertEqual(crf, 19)
        measures = [c for c in fake.calls
                    if c[0] == "ffmpeg" and "-filter_complex" in c]
        for cmd in measures:
            fc = cmd[cmd.index("-filter_complex") + 1]
            self.assertNotIn("fps=", fc)
            self.assertIn("[0:v]setpts=PTS-STARTPTS,split=3", fc)
            self.assertIn("[1:v]setpts=PTS-STARTPTS,split=3", fc)


class CollectInputsTest(unittest.TestCase):
    """Regression: collect_inputs must publish user-entered episode lists
    to params BEFORE the CRF block — autoselect reads params.episodes /
    params.sp_episodes, and the wizard saves them empty to
    streams_data.json (2026-08-25 user report: autoselect always bailed
    out with 'Не выбрано эпизодов')."""

    AUTOSELECT_SENTINEL = 17

    def make_wizard_params(self, media_dir):
        """Mirror the wizard's FFmpegParam: episodes/sp_episodes empty."""
        return FFmpegParam(
            name="Show", season="01", path=media_dir,
            episodes=[], sp_episodes=[],
            video_ext=[".mp4"], audio_ext=[], sub_ext=[],
            output_ext=".mp4", flac_convert=False,
            codec="hevc", bit=8, tune_preset="", cut_time=[], crf=None,
        )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, *filenames):
        for fn in filenames:
            open(os.path.join(self.tmp.name, fn), "w").close()

    def run_collect(self, params, answers):
        """Drive collect_inputs with scripted stdin + autoselect stub.

        The stub SNAPSHOTs the episode lists at call time (they are
        compared by reference later; a late assignment inside
        collect_inputs would otherwise be invisible to the test).
        """
        captured = {}

        def fake_autoselect(p):
            captured["params"] = p
            captured["episodes"] = list(p.episodes)
            captured["sp_episodes"] = list(p.sp_episodes)
            return self.AUTOSELECT_SENTINEL

        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(answers)), \
                mock.patch.object(ffmpeg_converter, "run_autoselect_crf",
                                  fake_autoselect), \
                mock.patch.object(ffmpeg_converter.subprocess, "run",
                                  lambda cmd, **kw: None), \
                redirect_stdout(buf):
            result = ffmpeg_converter.collect_inputs([], params)
        return result, captured, buf.getvalue()


    def test_autoselect_receives_entered_episodes(self):
        media_dir = self.tmp.name
        self._write("Show S01E01.mp4", "Show S01E02.mp4", "Show S01E03.mp4")
        params = self.make_wizard_params(media_dir)
        # stdin: episodes "1-3", tune 0 (animation), CRF mode 1 (autoselect),
        # no cut timings
        result, captured, _ = self.run_collect(params, ["1-3", "0", "1", ""])
        self.assertIn("params", captured,
                      "autoselect must be called in autoselect mode")
        self.assertEqual(captured["episodes"], ["01", "02", "03"])
        self.assertEqual(result.episodes, ["01", "02", "03"])
        self.assertEqual(result.crf, self.AUTOSELECT_SENTINEL)

    def test_autoselect_receives_sp_episodes(self):
        media_dir = self.tmp.name
        self._write("Show S00E01.mp4", "Show S01E02.mp4")
        params = self.make_wizard_params(media_dir)
        # stdin: episodes "2" (S01E02 exists), sp "1" (S00E01), tune 0,
        # CRF mode 1 (autoselect), no cut timings
        result, captured, _ = self.run_collect(
            params, ["2", "1", "0", "1", ""])
        self.assertIn("params", captured)
        self.assertEqual(captured["episodes"], ["02"])
        self.assertEqual(captured["sp_episodes"], ["01"])
        self.assertEqual(result.episodes, ["02"])
        self.assertEqual(result.sp_episodes, ["01"])
        self.assertEqual(result.crf, self.AUTOSELECT_SENTINEL)

    def test_manual_mode_unchanged(self):
        media_dir = self.tmp.name
        self._write("Show S01E01.mp4")
        params = self.make_wizard_params(media_dir)
        # stdin: episodes "1", tune 0, CRF mode 0 (manual), CRF "18", no cut
        result, captured, _ = self.run_collect(
            params, ["1", "0", "0", "18", ""])
        self.assertNotIn("params", captured,
                         "manual mode must not invoke autoselect")
        self.assertEqual(result.episodes, ["01"])
        self.assertEqual(result.crf, 18)


if __name__ == "__main__":
    unittest.main()
