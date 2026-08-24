"""ffmpeg command construction (pure — no input(), no process execution)."""
import os
import re

from ffcore.ffprobe import run_ffprobe

TUNE_LIST = ['animation', 'grain', 'film']

PIX_FMT_BY_BIT = {
    8: "yuv420p",
    10: "yuv420p10le",
    12: "yuv420p12le",
}


def generate_ffmpeg_video_config(codec, bit):
    # Бит-глубина 8/10/12 → -pix_fmt; пусто/None → как у оригинала
    pix_fmt_args = ""
    if bit not in (None, ""):
        pix_fmt = PIX_FMT_BY_BIT.get(int(bit))
        if pix_fmt:
            pix_fmt_args = f" -pix_fmt {pix_fmt}"
    if not codec:
        if pix_fmt_args:
            print("Внимание: бит-глубина игнорируется при копировании видео (-c:v copy)")
        return "-c:v copy"
    if codec == "hevc":
        return f"-c:v libx265 -vtag hvc1{pix_fmt_args}"
    if codec == "av1(Его нет)":
        return f"-c:v libaom-av1{pix_fmt_args}"
    if codec == "h264":
        return f"-c:v libx264{pix_fmt_args}"
    return "-c:v copy"


def generate_ffmpeg_tune_config(crf, tune):
    tune_config = []
    if not crf:
        return tune_config
    else:
        if tune:
            # Пустой tune (пресет пропущен) не должен давать сиротский
            # -tune: после фильтрации пустых аргументов он съедает значение
            # -crf, и ffmpeg ломается ("Error opening output file 18").
            tune_config.append('-tune')
            tune_config.append(f'{tune}')
        tune_config.append('-crf')
        tune_config.append(f'{crf}')
    return tune_config


def generate_ffmpeg_audio_config(audio_sub_streams, flac_convert):
    audio_config = []
    if flac_convert == True:
        for i, stream in enumerate(audio_sub_streams):
            if stream.type == 'a':
                if stream.codec in ('aac', 'aac_latm', 'mp4a'):
                    audio_config.append(f"-c:a:{i}")
                    audio_config.append("copy")
                else:
                    audio_config.append(f"-c:a:{i}")
                    audio_config.append("libfdk_aac")
                    audio_config.append("-vbr")
                    audio_config.append("5")
    else:
        audio_config.append("-c:a")
        audio_config.append("copy")
    return audio_config


def generate_ffmpeg_mapping_and_meta(audio_sub_streams, map_text=False):
    mapping = []
    meta = []
    audio_count = 0
    mapping.append("-map")
    mapping.append("0:v")
    if map_text:
        # Сохраняем встроенные в видео шрифты (t-стримы), чтобы сабы
        # находили свои шрифты в выходном файле. Только MKV — mp4
        # вложения не поддерживает.
        mapping.append("-map")
        mapping.append("0:t:?")
    for i, stream in enumerate(audio_sub_streams):
        if stream.type == "a":
            if i == 0:
                meta.append("-disposition:a:0")
                meta.append("default")
            else:
                meta.append(f"-disposition:a:{i}")
                meta.append("0")
            audio_count += 1
            index = i
        else:
            index = i - audio_count
            if stream.title == "Надписи":
                if i - audio_count == 0:
                    meta.append("-disposition:s:0")
                    meta.append("default+forced")
                else:
                    meta.append(f"-disposition:s:{index}")
                    meta.append("forced")
            else:
                meta.append(f"-disposition:s:{index}")
                meta.append("0")
        mapping.append("-map")
        mapping.append(f"{stream.stream}:{stream.type}:{stream.index}")
        meta.append(f"-metadata:s:{stream.type}:{index}")
        meta.append(f"language={stream.lang}")
        meta.append(f"-metadata:s:{stream.type}:{index}")
        meta.append(f'title={stream.title}')
    return mapping, meta


def generate_ffmpeg_sub_fonts(audio_sub_streams, output_ext, t_offset=0):
    sub_fonts = []
    if output_ext == ".mkv":
        # t_offset = количество встроенных шрифтов, мапнутых через 0:t:?
        # Они занимают t-индексы t:0..t:(t_offset-1), поэтому прикреплённые
        # через -attach начинаются с t_offset.
        fonts_count = 0
        for stream in audio_sub_streams:
            if stream.type == "s":
                for font in stream.fonts:
                    sub_fonts.append("-attach")
                    sub_fonts.append(f"{font}")
                    sub_fonts.append(f"-metadata:s:t:{t_offset + fonts_count}")
                    sub_fonts.append(f"mimetype=application/x-{'truetype-font' if font.lower().endswith('.ttf') else 'font-opentype'}")
                    fonts_count += 1
    return sub_fonts


def count_embedded_text_streams(video_path):
    # Количество встроенных t-стримов (шрифтов) в видео-входе. 0, если нет.
    if not video_path or not os.path.exists(video_path):
        return 0
    try:
        return len(run_ffprobe(video_path, "t"))
    except Exception:
        return 0


def _normalize_ext_list(exts):
    # принимает строку '.mkv' или список ['.mkv','.mp4'] и возвращает ['mkv','mp4']
    if not exts:
        return []
    if isinstance(exts, (list, tuple)):
        return [e.lstrip('.').lower() for e in exts]
    return [exts.lstrip('.').lower()]


def find_episode_files(dirpath, base_name, exts):
    """Sorted full paths in dirpath matching:
      ^base_name (optional ' [..]' blocks) . (ext)

    (The converter's file search; renamed from find_media_candidates to
    avoid the name collision with ffcore.media's folder search.)
    """
    exts_norm = _normalize_ext_list(exts)
    if not exts_norm:
        return []
    exts_re = "|".join(re.escape(e) for e in exts_norm)
    pattern = re.compile(rf"^{re.escape(base_name)}(?:\s*\[.*?\])*\.(?:{exts_re})$", re.IGNORECASE)
    candidates = []
    try:
        for fname in sorted(os.listdir(dirpath)):
            if pattern.match(fname):
                candidates.append(os.path.join(dirpath, fname))
    except FileNotFoundError:
        return []
    return candidates


def choose_candidate(candidates, params=None):
    """Выбирает кандидат: если задан params.preferred_codec — отдаём файл, содержащий этот кодек в имени."""
    if not candidates:
        return None
    if params is not None and getattr(params, "preferred_codec", None):
        pref = params.preferred_codec.upper()
        for c in candidates:
            if pref in os.path.basename(c).upper():
                return c
    # иначе — первый по сортировке
    return candidates[0]


def generate_ffmpeg_input_files(audio_sub_streams, params, index, sp):
    input_files = []
    season = "00" if sp else params.season
    base_name = f"{params.name} S{season}E{index}"

    # ------------ видео ------------
    video_dir = params.path
    # params.video_ext может быть строкой или список
    video_candidates = find_episode_files(video_dir, base_name, params.video_ext)
    video_path = choose_candidate(video_candidates, params)
    if not video_path:
        raise FileNotFoundError(f"Не найден видеофайл для {base_name} (разыскивались расширения: {params.video_ext}) в {video_dir}")
    input_files.extend(["-i", video_path])

    # ------------ аудио и сабы ------------
    i = 0
    audio_count = 0
    for stream in audio_sub_streams:
        # определяем папку, где искать этот стрим
        if stream.path == "/":
            search_dir = params.path
        else:
            search_dir = os.path.join(params.path, stream.path)

        # аудио
        if stream.type == 'a':
            audio_count += 1
            if stream.path:
                # params.audio_ext может быть списком и мы берем i-ый элемент
                audio_ext = params.audio_ext[i] if isinstance(params.audio_ext, (list, tuple)) else params.audio_ext
                aud_candidates = find_episode_files(search_dir, base_name, audio_ext)
                aud_path = choose_candidate(aud_candidates, params)
                if aud_path:
                    input_files.extend(["-i", aud_path])
                    i += 1
                else:
                    # если аудио ожидается, но не найдено — можно логировать или выбрасывать, здесь просто продолжаем
                    print(f"Внимание: аудиофайл не найден для {base_name} в {search_dir} (ожидалось расширение {audio_ext})")
        # сабы
        if stream.type == 's' and stream.path:
            # для сабов индекс берётся с учётом уже посчитанных аудио
            sub_idx = i - audio_count if isinstance(params.sub_ext, (list, tuple)) else 0
            sub_ext = params.sub_ext[sub_idx] if isinstance(params.sub_ext, (list, tuple)) else params.sub_ext
            sub_candidates = find_episode_files(search_dir, base_name, sub_ext)
            sub_path = choose_candidate(sub_candidates, params)
            if sub_path:
                input_files.extend(["-i", sub_path])
            else:
                print(f"Внимание: субтитры не найдены для {base_name} в {search_dir} (ожидалось расширение {sub_ext})")

    return input_files


def codec_tag(codec):
    """Bracket tag for the output filename, or '' when no tag is wanted.

    User rule: brackets carry the codec only for hevc ('HEVC') and av1
    ('AV1'); h264 and codec copy produce a bare name.
    """
    if not codec:
        return ""
    if codec.lower() == "hevc":
        return "HEVC"
    if "av1" in codec.lower():
        return "AV1"
    return ""


def generate_ffmpeg_output_files(params, index, sp):
    if sp == True:
        season = "00"
    else:
        season = params.season
    tag = codec_tag(params.codec)
    bracket = f" [{tag}]" if tag else ""
    base_name = f'{params.name} S{season}E{index}{bracket}{params.output_ext}'
    if params.path.endswith(".tmp"):
        path = os.path.dirname(params.path)
    else:
        path = params.path
    return os.path.join(path, base_name)


def generate_ffmpeg_command(audio_sub_streams, params, index, sp):
    input_files = generate_ffmpeg_input_files(audio_sub_streams, params, index, sp)
    video_path = None
    for k in range(len(input_files) - 1):
        if input_files[k] == "-i":
            video_path = input_files[k + 1]
            break
    is_mkv = params.output_ext == ".mkv"
    # Встроенные шрифты (t-стримы) мапятся только в MKV; прикреплённые через
    # -attach получают t-индекс со сдвигом на их количество.
    t_offset = count_embedded_text_streams(video_path) if is_mkv else 0
    mapping, metadata = generate_ffmpeg_mapping_and_meta(audio_sub_streams, map_text=is_mkv)
    video_config = generate_ffmpeg_video_config(params.codec, params.bit)
    audio_config = generate_ffmpeg_audio_config(audio_sub_streams, params.flac_convert)
    sub_fonts = generate_ffmpeg_sub_fonts(audio_sub_streams, params.output_ext, t_offset=t_offset)
    output_file = generate_ffmpeg_output_files(params, index, sp)
    tune_config = generate_ffmpeg_tune_config(params.crf, params.tune_preset)
    # Приватные опции x265 (asm=avx512, aq-mode=3 — AQ для аниме, row-mt=1)
    # передаются ТОЛЬКО через -x265-params: топовые -aq-mode/-row-mt ffmpeg
    # молча игнорирует ("Codec AVOption aq-mode … has not been used"), и
    # энкод уходит без AQ. Для не-x265 кодексов (h264/copy) словарь не
    # нужен — и сам флаг -x265-params тоже (сиротский флаг съел бы путь
    # выходного файла как значение, как это было с -tune в 2026-08-22).
    x265_args = ["-x265-params", "asm=avx512:aq-mode=3:row-mt=1"] if params.codec == "hevc" else []
    command = ["ffmpeg", "-analyzeduration", "100M", "-probesize", "100M", *input_files, params.cut_time, *mapping, *video_config.split(), *audio_config, *sub_fonts, "-c:s", "copy", "-max_interleave_delta", "0", *metadata, *tune_config, "-preset", "slow", "-threads", "0", *x265_args, output_file, "-y"]
    command = [arg for arg in command if arg != '']
    return command
