"""Media file lookup: extension rules + first-file resolution."""
import os

# The exact extension sets the legacy code inlined in ffprobe_media,
# get_media_ext and get_video_codec. (ALLOWED_EXTENSIONS in the config
# entry is display-only for count_files_by_extension and stays there.)
VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov")
AUDIO_EXTENSIONS = (".mka", ".flac", ".mp3", ".ac3", ".aac", ".m4a", ".wav",
                    ".wmv", ".mkv", ".mp4")
SUBTITLE_EXTENSIONS = (".srt", ".ass", "sub")


def media_getter(path, exts):
    if not os.path.isdir(path):
        return ""
    for f in os.listdir(path):
        if f.endswith(exts):
            return f
    return ""


def get_media_ext(video_path, audio_sub_streams):
    video_ext = ""
    audio_ext = []
    sub_ext = []
    if video_path:
        media_file = media_getter(video_path, VIDEO_EXTENSIONS)
        if media_file:
            video_ext = os.path.splitext(media_file)[1]
        else:
            print(f"Внимание: видеофайл не найден в {video_path}")
    for i, stream in enumerate(audio_sub_streams):
        if stream.path == "/":
            path = video_path
        else:
            path = os.path.join(video_path, stream.path)

        if stream.type == "a" and stream.path:
            media_file = media_getter(path, AUDIO_EXTENSIONS)
            if media_file:
                audio_ext.append(os.path.splitext(media_file)[1])
            else:
                print(f"Внимание: аудиофайл не найден в {path}")
                audio_ext.append("")
        if stream.type == "s" and stream.path:
            media_file = media_getter(path, SUBTITLE_EXTENSIONS)
            if media_file:
                sub_ext.append(os.path.splitext(media_file)[1])
            else:
                print(f"Внимание: субтитры не найдены в {path}")
                sub_ext.append("")
    return video_ext, audio_ext, sub_ext
