"""CRF autoselect: pure logic for PSNR/SSIM/VMAF-gated bisection.

2026-08-24 feature. The entry script (ffmpeg_converter.py) runs the real
ffmpeg subprocesses and prompts; everything testable without a
subprocess lives here.

User-mandated parameters (2026-08-24):
  * CRF bounds 14..19
  * gates: PSNR >= 50 AND SSIM >= 0.98 AND VMAF >= 96 (per sample)
  * 3 samples: head (30 s from start, 0 when the episode is short),
    middle, tail (30 s before the end); 5 s each
"""
import json
import re

CRF_MIN = 14
CRF_MAX = 19
GATES = {"psnr": 50.0, "ssim": 0.98, "vmaf": 96.0}
SAMPLE_SECONDS = 5
START_OFFSET = 30.0   # секунд от начала (и до конца)

_MODEL_4K = "vmaf_4k_v0.6.1.json"
_MODEL_1080 = "vmaf_v0.6.1.json"


def _fmt_t(value):
    # 30.0 -> "30", 17.5 -> "17.5"
    return f"{value:g}"


def sample_points(duration):
    """(ss, dur) точки для файла длительностью duration секунд.

    head: +START_OFFSET от начала (0, если duration < 2*START_OFFSET);
    mid : середина (окно SAMPLE_SECONDS);
    tail: START_OFFSET до конца.
    Точки клампятся внутрь файла, дубликаты удаляются, сортировка по ss.
    duration <= SAMPLE_SECONDS -> [].
    """
    if duration <= SAMPLE_SECONDS:
        return []
    head = START_OFFSET if duration >= 2 * START_OFFSET else 0.0
    mid = duration / 2 - SAMPLE_SECONDS / 2
    tail = duration - START_OFFSET - SAMPLE_SECONDS
    limit = duration - SAMPLE_SECONDS
    pts = set()
    for ss in (head, mid, tail):
        ss = min(max(ss, 0.0), limit)
        pts.add(round(ss, 3))
    return [(ss, SAMPLE_SECONDS) for ss in sorted(pts)]


def select_model(width):
    """Имя VMAF-модели по ширине видео (4K — от 3840)."""
    return _MODEL_4K if width and width >= 3840 else _MODEL_1080


def search_crf(evaluate, lo=CRF_MIN, hi=CRF_MAX):
    """Крупнейший CRF в [lo, hi], для которого evaluate(crf) — True.

    Целочисленный бинарный поиск: <= 5 оценок на [14..19], без повторов.
    None, если даже `lo` не проходит.
    """
    if not evaluate(lo):
        return None
    result, low, high = lo, lo + 1, hi
    while low <= high:
        mid = (low + high) // 2
        if evaluate(mid):
            result, low = mid, mid + 1
        else:
            high = mid - 1
    return result


def gate_failures(psnr, ssim, vmaf):
    """Не пройдённые ворота одного сэмпла: ["PSNR 49.0", "VMAF 95.0", ...]."""
    failures = []
    if psnr < GATES["psnr"]:
        failures.append(f"PSNR {psnr:.1f}")
    if ssim < GATES["ssim"]:
        failures.append(f"SSIM {ssim:.4f}")
    if vmaf < GATES["vmaf"]:
        failures.append(f"VMAF {vmaf:.1f}")
    return failures


_PSNR_RE = re.compile(r"psnr_avg:([\d.]+)")
_SSIM_RE = re.compile(r"All:([\d.]+)")


def parse_psnr_log(text):
    """psnr_avg последней строки stats-файла psnr (None, если нет)."""
    last = None
    for line in text.splitlines():
        m = _PSNR_RE.search(line)
        if m:
            last = float(m.group(1))
    return last


def parse_ssim_log(text):
    """Колонка 'All' последней строки stats-файла ssim (None, если нет)."""
    last = None
    for line in text.splitlines():
        m = _SSIM_RE.search(line)
        if m:
            last = float(m.group(1))
    return last


def parse_vmaf_json(path):
    """(mean, min) VMAF из JSON-лога libvmaf; None при ошибке/отсутствии."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        vmaf = data["pooled_metrics"]["vmaf"]
        return float(vmaf["mean"]), float(vmaf["min"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def sample_encode_command(video_path, ss, dur, out_path, video_config_args,
                          crf, x265_params=None):
    """argv ffmpeg: клип dur сек с позиции ss, закодированный при данном CRF.

    video_config_args — видео-часть команды финального энкода (-c:v libx265
    -vtag hvc1 [-pix_fmt …] [-tune …]), поэтому сэмпл повторяет финальный
    энкод по построению. -an: сэмпл без аудио.
    """
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-ss", _fmt_t(ss), "-t", _fmt_t(dur), "-i", video_path,
           *video_config_args, "-preset", "slow", "-crf", str(crf)]
    if x265_params:
        cmd += ["-x265-params", x265_params]
    cmd += ["-an", "-f", "mp4", out_path, "-y"]
    return cmd


def measure_command(enc_path, ref_path, ss, dur, workdir, model_path):
    """argv ffmpeg: PSNR+SSIM+VMAF клипа enc против окна оригинала.

    Окно референса вырезается из оригинала тем же -ss/-t (точный input
    seek) — пиксельно совпадает с сэмплом. Замер всегда в полном
    разрешении (subsample не используется: он экономит секунды замера
    при десятках секунд энкода).
    """
    fc = (
        "[0:v]setpts=PTS-STARTPTS,split=3[d0][d1][d2];"
        "[1:v]setpts=PTS-STARTPTS,split=3[r0][r1][r2];"
        f"[d0][r0]psnr=stats_file={workdir}/p.log[n0];"
        f"[d1][r1]ssim=stats_file={workdir}/s.log[n1];"
        f"[d2][r2]libvmaf=model=path={model_path}:log_fmt=json:"
        f"log_path={workdir}/v.json[n2]"
    )
    return ["ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", enc_path,
            "-ss", _fmt_t(ss), "-t", _fmt_t(dur), "-i", ref_path,
            "-filter_complex", fc,
            "-map", "[n0]", "-map", "[n1]", "-map", "[n2]",
            "-f", "null", "-"]
