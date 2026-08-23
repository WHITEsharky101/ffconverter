"""ffprobe wrappers."""
import json
import os
import subprocess

from ffcore.files import VIDEO_EXTENSIONS, media_getter


def run_ffprobe(file_to_probe, stream_type):
    command = [
        "ffprobe", "-v", "error", "-select_streams", stream_type, "-show_entries",
        "stream=index,codec_name:stream_tags=language,title", "-of", "json", file_to_probe
    ]

    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        if result.returncode != 0:
            print(f"Ошибка ffprobe: {result.stderr.strip()}")
            return []
        return json.loads(result.stdout).get("streams", [])
    except json.JSONDecodeError as e:
        print(f"Ошибка обработки JSON: {e}")
        return []


def ffprobe_media(folder_path):
    media_file = media_getter(folder_path, VIDEO_EXTENSIONS)
    if not media_file:
        print("Нет подходящих медиафайлов для анализа.")
        return [], []

    file_to_probe = os.path.join(folder_path, media_file)
    audio_data = run_ffprobe(file_to_probe, "a")
    subtitle_data = run_ffprobe(file_to_probe, "s")
    return audio_data, subtitle_data


def get_video_codec(folder_path):
    """Codec name of the first video stream in the first video file, or ""."""
    media_file = media_getter(folder_path, VIDEO_EXTENSIONS)
    if not media_file:
        return ""
    streams = run_ffprobe(os.path.join(folder_path, media_file), "v")
    if streams:
        return streams[0].get("codec_name") or ""
    return ""


def has_flac_audio(folder_path, audio_streams):
    """True if any audio track is FLAC.

    Embedded tracks (no path) are checked by codec_name from ffprobe;
    external tracks by .flac extension in their folder (same resolution
    rule as get_media_ext).
    """
    for stream in audio_streams:
        if stream.type != "a":
            continue
        if not stream.path:
            if (stream.codec or "").lower() == "flac":
                return True
            continue
        if stream.path == "/":
            path = folder_path
        else:
            path = os.path.join(folder_path, stream.path)
        if not os.path.isdir(path):
            continue
        try:
            for f in os.listdir(path):
                if f.lower().endswith(".flac"):
                    return True
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue
    return False
