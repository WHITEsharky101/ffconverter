import os
import re
import subprocess
import zipfile
import rarfile
import json
import pickle

ALLOWED_EXTENSIONS = {
    ".mkv", ".mp4", ".mka", ".ass", ".srt", ".flac", ".mp3", ".ac3", ".aac",
    ".m4a", ".avi", ".wav", ".mov", ".wmv"
}
CODECS = ["hevc", "h264"]
SAVE_FILE = "streams_data.pkl"
#rarfile.UNRAR_TOOL = r"/"

class AudioSubStream:
    def __init__(self, stream, index, type, path, fonts, lang, title, codec):
        self.stream = stream
        self.index = index
        self.type = type
        self.path = path
        self.fonts = fonts
        self.lang = lang
        self.title = title
        self.codec = codec
        
class FFmpegParam:
    def __init__(self, name, season, path, episodes, sp_episodes, video_ext, audio_ext, sub_ext, output_ext, flac_convert, codec, bit, tune_preset, cut_time):
        self.name = name
        self.season = season
        self.path = path
        self.episodes = episodes
        self.sp_episodes = sp_episodes
        self.video_ext = video_ext
        self.audio_ext = audio_ext
        self.sub_ext = sub_ext
        self.output_ext = output_ext
        self.flac_convert = flac_convert
        self.codec = codec
        self.bit = bit
        self.tune_preset = tune_preset
        self.cut_time = cut_time

# Функция для поиска папки
def find_media_folder(base_path, name, season):
    search_prefix = f"{name} S{season}"
    candidates = []
    try:
        for folder in os.listdir(base_path):
            if folder.startswith(search_prefix):
                candidates.append(folder)

        if not candidates:
            print(f"Сезон S{season} не найден.\n")    
            return None, []

        if len(candidates) == 1:
            folder = candidates[0]
        else:
            print(f"\nНайдено несколько папок для {search_prefix}:")
            for i, folder in enumerate(candidates, 1):
                print(f"{i}: {folder}")
            while True:
                try:
                    choice = int(input("Выберите папку: "))
                    if 1 <= choice <= len(candidates):
                        folder = candidates[choice - 1]
                        break
                except ValueError:
                    pass
                print("Неверный ввод, попробуйте снова.")

        # Проверяем наличие тегов в имени выбранной папки
        audio_tags = []
        if "[" in folder and "]" in folder:
            start = folder.index("[") + 1
            end = folder.index("]")
            tags = folder[start:end]
            audio_tags = [
                tag.strip() for tag in tags.split(",") if tag.strip() not in {"Sub", "Vid"}
            ]

        return folder, audio_tags

    except FileNotFoundError:
        print(f"Директория {base_path} не найдена.\n")
        return None, []
    
def count_files_by_extension(files):
    return sum(1 for file in files if os.path.splitext(file)[1] in ALLOWED_EXTENSIONS)

def list_folders(path):
    final_folders = []
    root_files = 0
    
    for root, dirs, files in os.walk(path):
        files_count = count_files_by_extension(files)
        if root == path:
            root_files = files_count
        elif not dirs:  # Проверяем, что папка конечная
            relative_path = os.path.relpath(root, path)
            final_folders.append((relative_path, files_count))

    print(f"\n{os.path.normpath(path).split(os.sep)[1]} [{root_files}]")
    for folder, file_count in final_folders:
        print(f"       └─ {folder} [{file_count}]")

def run_ffprobe(file_to_probe, type):
    command = [
        "ffprobe", "-v", "error", "-select_streams", type, "-show_entries",
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
        
# Функция для выполнения ffprobe
def ffprobe_media(folder_path):
    media_file = media_getter(folder_path, (".mkv", ".mp4", ".avi", ".mov"))
    if not media_file:
        print("Нет подходящих медиафайлов для анализа.")
        return [], []
  
    file_to_probe = os.path.join(folder_path, media_file)
    audio_data = run_ffprobe(file_to_probe, "a")
    subtitle_data = run_ffprobe(file_to_probe, "s")
    return audio_data, subtitle_data

def get_video_codec(folder_path):
    """Codec name of the first video stream in the first video file, or ""."""
    media_file = media_getter(folder_path, (".mkv", ".mp4", ".avi", ".mov"))
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

# Season subfolder looks like "<name> S01", "<name> S01 [tags]".
SEASON_FOLDER_RE = re.compile(r" S\d{1,3}(\s|\[|$)")


def _has_season_folder(path):
    try:
        return any(SEASON_FOLDER_RE.search(d) for d in os.listdir(path))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return False


def find_media_candidates(query, base="."):
    """Return media folder names in base containing query (case-insensitive).

    A directory counts as media only if it has a season subfolder
    ("Name SNN"), so junk dirs are excluded. Unreadable base -> [].
    """
    q = query.lower()
    try:
        entries = os.listdir(base)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    candidates = [
        d
        for d in entries
        if q in d.lower() and os.path.isdir(os.path.join(base, d))
        and _has_season_folder(os.path.join(base, d))
    ]
    return sorted(candidates, key=str.lower)


def select_media_name(query, base="."):
    """Resolve a media name from search results.

    Exact (case-insensitive) or single match -> returned directly.
    Several matches -> numbered list, user picks a number.
    No match -> None.
    """
    candidates = find_media_candidates(query, base)
    if not candidates:
        return None
    for c in candidates:
        if c.lower() == query.lower():
            return c
    if len(candidates) == 1:
        return candidates[0]
    print(f"\nНайдено несколько совпадений для '{query}':")
    for i, folder in enumerate(candidates, 1):
        print(f"{i}: {folder}")
    while True:
        try:
            choice = int(input("Выберите медиа: "))
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
        except ValueError:
            pass
        print("Неверный ввод, попробуйте снова.")


def _parse_season_note(folder):
    """Content of the first [...] pair in a season folder name, verbatim.

    No splitting, no filtering — the bracket content is shown as-is.
    Returns "" when the folder name has no brackets.
    """
    m = re.search(r"\[([^\]]*)\]", folder)
    return m.group(1).strip() if m else ""


def list_seasons(base_path, name):
    """Available season numbers under base_path for a media name.

    Returns [(digits, note), ...] sorted by season number, where note is
    the first [...] content of a matching "<name> SNN" folder name,
    verbatim ("" when the folder has no brackets). Unreadable base -> [].
    """
    pattern = re.compile(re.escape(name) + r"\s+S(\d{1,3})(?=\s|\[|$)")
    seasons = {}
    try:
        entries = os.listdir(base_path)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return []
    for d in sorted(entries):
        if not os.path.isdir(os.path.join(base_path, d)):
            continue
        m = pattern.match(d)
        if not m:
            continue
        digits = m.group(1)
        if digits not in seasons:
            seasons[digits] = _parse_season_note(d)
        elif not seasons[digits]:
            seasons[digits] = _parse_season_note(d)
    return [(digits, seasons[digits]) for digits in sorted(seasons, key=int)]


def prompt_user_for_media():
    while True:
        name = input("Введите название медиа: ")
        selected = select_media_name(name)
        if selected is None:
            print(f"Ничего не найдено по запросу '{name}'. Попробуйте ещё раз.")
            continue
        if selected != name:
            print(f"Выбрано: {selected}")
        name = selected
        break
    base_path = f"{name}/"
    while True:
        formatted_season = None
        seasons = list_seasons(base_path, name)
        if seasons:
            print(f"\nДоступные сезоны:")
            for i, (digits, note) in enumerate(seasons, 1):
                label = f"S{digits}"
                if note:
                    label += f" [{note}]"
                print(f"{i}: {label}")
            while True:
                try:
                    choice = int(input("Выберите сезон: ") or "1")
                    if 1 <= choice <= len(seasons):
                        formatted_season = seasons[choice - 1][0]
                        break
                except ValueError:
                    pass
                print("Неверный ввод, попробуйте снова.")
        else:
            season = input("Введите номер сезона: (по умолчанию 1): ") or "1"
            formatted_season = season.zfill(2)

        media_folder, audio_tags = find_media_folder(base_path, name, formatted_season)
        if media_folder:
            return base_path, media_folder, audio_tags, name, formatted_season

def prompt_streams(streams_data, type):
    streams = []
    if type == "a":
        print("\nВстроенные аудио:")
    else:
        print("\nВстроенные субтитры:")
    for i, track in enumerate(streams_data):
        tags = track.get("tags", {})
        stream = AudioSubStream(
            stream=0,
            index=i,
            type=type,
            path="",
            fonts = [],
            lang=tags.get("language", "???"),
            title=tags.get("title"),
            codec=track.get("codec_name")
        )
        streams.append(stream)
        print(f"№: {i}, Язык: {stream.lang}, Название: {stream.title}")
    return streams
    
def collect_additional_streams(audio_tags):
    audio_streams, audio_count = create_streams("a", 0)
    subtitle_streams, subtitle_count = create_streams("s", audio_count)
    return audio_streams, subtitle_streams
    
def create_streams(type, prev_count):
    streams = []
    if type == "a":
        print("\nВведите путь для дополнительных аудио дорожек (оставьте пустым для завершения):")
        i = 1 
    else:
        print("\nВведите путь для дополнительных субтитров (оставьте пустым для завершения)")
        i = prev_count + 1 
    while True:   
        path = input(f"{i}: ")
        if not path:
            break   
        
        if path == "/" or path == "\\":
            path = "/"
        
        if type == "a":
            title = ""
        else:
            title = "Надписи" if "надписи" in path.lower() else "Полные"
                    
        stream = AudioSubStream(
            stream=i,
            index=0,
            type=type,
            path=path,
            fonts = [],
            lang="rus",
            title=title,
            codec=""
        )
        streams.insert(i - prev_count - 1, stream)
        i += 1  
    return streams, i - prev_count - 1
    

def extract_archive(archive_path, extract_to):
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as archive:
            archive.extractall(extract_to)
    elif rarfile.is_rarfile(archive_path):
        with rarfile.RarFile(archive_path, 'r') as archive:
            archive.extractall(extract_to)

def find_fonts_in_directory(directory):
    fonts = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.ttf', '.otf')):
                fonts.append(os.path.join(root, file))
        if fonts:
            break
    print(fonts)
    return fonts

def find_ttf_in_fonts(path, stream):
    # "" and "/" mean the season directory itself (same rule as
    # get_media_ext / generate_ffmpeg_input_files). os.path.join resets
    # on an absolute second argument, so "/" must NOT be joined blindly —
    # it would point the search at the filesystem root.
    if stream.path in ("", "/"):
        search_dir = path
    else:
        search_dir = os.path.join(path, stream.path)

    # Missing subtitle folder: return the stream untouched, no side effects.
    if not os.path.isdir(search_dir):
        return stream

    fonts_dir = os.path.join(search_dir, 'fonts')

    # Create fonts/ ONLY when a font archive is actually found.
    for file in os.listdir(search_dir):
        file_path = os.path.join(search_dir, file)
        if os.path.isfile(file_path) and file.lower().startswith(('fonts', 'font')) and file.lower().endswith(('.zip', '.rar')):
            os.makedirs(fonts_dir, exist_ok=True)
            extract_archive(file_path, fonts_dir)
            break

    for root, dirs, files in os.walk(search_dir):
        for dir_name in dirs:
            if dir_name.lower() in ('fonts', 'font'):
                target_dir = os.path.join(root, dir_name)

                for sub_root, _, sub_files in os.walk(target_dir):
                    for sub_file in sub_files:
                        sub_file_path = os.path.join(sub_root, sub_file)
                        if sub_file.lower().endswith(('.zip', '.rar')):
                            extract_archive(sub_file_path, sub_root)

                fonts = find_fonts_in_directory(target_dir)
                if fonts:
                    stream.fonts = fonts
                    return stream
    return stream
    
def adjust_sub_properties(streams):
    path_width = max(10, max((len(stream.path or "") for stream in streams), default=0))
    title_width = max(10, max((len(stream.title or "") for stream in streams), default=0))

    print("\nВведите язык и название субтитров (оставьте пустым, чтобы оставить без изменений)")
    for stream in streams:
        path = stream.path if stream.path else "Встроенные"
        sub_tags = input(f"{path:<{path_width}}  {stream.lang} {(stream.title or '???'):<{title_width}}  :   ")
        if sub_tags:
            sub_tags = sub_tags.split(" ", 1)
            stream.lang = sub_tags[0]
            stream.title = sub_tags[1] if len(sub_tags) > 1 else ""
        if not stream.title:
            stream.title = "Полные"    
    
def display_streams(audio_streams, sub_streams, audio_tags):
    index_width = 3
    name_width = max(10, max(len(stream.title or "") for stream in audio_streams + sub_streams) + 3)
    lang_width = max(10, max(len(stream.lang or "") for stream in audio_streams + sub_streams) + 3)
    path_width = max(10, max(len(stream.path or "") for stream in audio_streams + sub_streams) + 3)

    print(f"\n{'№':<{index_width}} {'Название':<{name_width}} {'Язык':<{lang_width}} Путь\n")
    print("Порядок аудио")
    for i, audio_stream in enumerate(audio_streams):
        path = audio_stream.path if audio_stream.path else "Встроенные"
        if i < len(audio_tags):
            title_sugges = audio_tags[i]
        else:
            if i == len(audio_streams) - 1:
                title_sugges = "Original"
            else:
                title_sugges = ""
        print(f"{i:<{index_width}} {(audio_stream.title or '???'):<{name_width}} {(audio_stream.lang or '???'):<{lang_width}} {path:<{path_width}}   ({title_sugges})")

    print("\nПорядок субтитров")
    for i, sub_stream in enumerate(sub_streams):
        path = sub_stream.path if sub_stream.path else "Встроенные"
        print(f"{i:<{index_width}} {sub_stream.title:<{name_width}} {sub_stream.lang:<{lang_width}} {path:<{path_width}}")
        
def change_mapping(audio_streams, sub_streams, audio_tags):
    tmp_audio_streams = audio_streams
    tmp_sub_streams = sub_streams
    
    while True:
        change_mapping = input("\nПоменять порядок или состав потоков?(y/n) ").strip().lower()
        if change_mapping == "y" or change_mapping == "н":
            audio_index_mapping = input("\nВведите порядок аудио (оставьте пустым, чтобы оставить без изменений): ")
            if audio_index_mapping:
                # Преобразуем строку порядка в список индексов
                order = list(map(int, audio_index_mapping.split()))
                
                # Переставляем классы в заданном порядке
                tmp_audio_streams = [audio_streams[i] for i in order]
            sub_index_mapping = input("\nВведите порядок субтитров (оставьте пустым, чтобы оставить без изменений): ")
            if sub_index_mapping:
                # Преобразуем строку порядка в список индексов
                order = list(map(int, sub_index_mapping.split()))

                # Переставляем классы в заданном порядке
                tmp_sub_streams = [sub_streams[i] for i in order]
            break
        elif change_mapping == "n" or change_mapping == "т":
            break
        else:
            print("Неверный ввод")
            
    for i, tag in enumerate(audio_tags):
        tmp_audio_streams[i].lang = "rus"
        tmp_audio_streams[i].title = tag
    
    if len(tmp_audio_streams) == len(audio_tags) + 1:
        index = 0 if len(audio_tags) == 0 else len(tmp_audio_streams) - 1
        tmp_audio_streams[index].lang = "jpn"
        tmp_audio_streams[index].title = "Original" 
        
    return tmp_audio_streams + tmp_sub_streams
    
def get_media_ext(video_path, audio_sub_streams):
    video_ext = ""
    audio_ext = []
    sub_ext = []
    if video_path:
        media_file = media_getter(video_path, (".mkv", ".mp4", ".avi", ".mov"))
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
            media_file = media_getter(path, (".mka", ".flac", ".mp3", ".ac3", ".aac", ".m4a", ".wav", ".wmv", ".mkv", ".mp4"))
            if media_file:
                audio_ext.append(os.path.splitext(media_file)[1])
            else:
                print(f"Внимание: аудиофайл не найден в {path}")
                audio_ext.append("")
        if stream.type == "s" and stream.path:
            media_file = media_getter(path, (".srt", ".ass", "sub"))
            if media_file:
                sub_ext.append(os.path.splitext(media_file)[1])
            else:
                print(f"Внимание: субтитры не найдены в {path}")
                sub_ext.append("")
    return video_ext, audio_ext, sub_ext
    
def media_getter(path, exts):
    if not os.path.isdir(path):
        return ""
    for f in os.listdir(path):
        if f.endswith(exts):
            return f
    return ""

# Функция для сохранения данных в файл
def save_data(data):
    with open(SAVE_FILE, "wb") as f:
        pickle.dump(data, f)      
    
            
def main():
    base_path, media_folder, audio_tags, name, season = prompt_user_for_media()

    tmp_folder = os.path.join(base_path, media_folder, ".tmp")
    folder_to_probe = tmp_folder if os.path.exists(tmp_folder) else os.path.join(base_path, media_folder)
    folder_to_probe = os.path.abspath(folder_to_probe)

    audio_streams_data, subtitle_streams_data = ffprobe_media(folder_to_probe)
    list_folders(folder_to_probe)          

    embedded_audio_streams = prompt_streams(audio_streams_data, "a")
    embedded_subtitle_streams = prompt_streams(subtitle_streams_data, "s")
    
    additional_audio_streams, additional_subtitle_streams = collect_additional_streams(audio_tags)

    stream_with_fonts = []
    for stream in additional_subtitle_streams:
        font_stream = find_ttf_in_fonts(folder_to_probe, stream)
        stream_with_fonts.append(font_stream)
        print(font_stream.fonts)
    additional_subtitle_streams = stream_with_fonts
        
    audio_streams = additional_audio_streams + embedded_audio_streams
    subtitle_streams = additional_subtitle_streams + embedded_subtitle_streams
    
    adjust_sub_properties(subtitle_streams) 
    
    display_streams(audio_streams, subtitle_streams, audio_tags)
    
    audio_sub_streams = change_mapping(audio_streams, subtitle_streams, audio_tags)
    
    video_ext, audio_ext, sub_ext = get_media_ext(folder_to_probe, audio_sub_streams)
    
    current_video_codec = get_video_codec(folder_to_probe)
    print(f"\nТекущий видеокодек: {current_video_codec or 'не определен'}")
    while True:
        print()
        for i, codec in enumerate(CODECS):
            print(f"{i}: {codec}")
        codec = input("\nВыберите кодек (По умолчанию как у оригинала): ")
        if not codec:
            break
        if int(codec) >= len(CODECS):
            print("\nНеверный ввод")
        else:    
            codec = CODECS[int(codec)]
            break
            
    bit = None
    while True:
        bit_input = input("\nВыберите количество бит для кодирования 8/10/12 (По умолчанию как у оригинала): ")
        if not bit_input:
            break
        if bit_input in ["8", "10", "12"]:
            bit = int(bit_input)
            break
        else:
            print("Неверный ввод")
   
    output_ext = input("\nВведите формат выходного файла (По умолчанию как у оригинала): ")
    if has_flac_audio(folder_to_probe, audio_sub_streams):
        while True:
            user_input = input("\nКонвертировать flac в acc?(y/n): ").strip().lower()
            if user_input == "y" or user_input == "н":
                flac_convert = True
                break
            elif user_input == "n" or user_input == "т":
                flac_convert = False
                break
            else:
                print("Неверный ввод")
    else:
        print("FLAC-дорожек не найдено — конвертация в AAC не требуется.")
        flac_convert = False
    
    data = {"streams": [], "params": []} 
    data["streams"] = audio_sub_streams
    data["params"] = FFmpegParam(
        name = name,
        season = season,
        path = folder_to_probe,
        episodes = [],
        sp_episodes = [],
        video_ext = video_ext,
        audio_ext = audio_ext,
        sub_ext = sub_ext,
        output_ext = video_ext if not output_ext else "." + output_ext,
        flac_convert = flac_convert,
        codec = codec,
        bit = bit,
        tune_preset = "",
        cut_time = []
    )
    save_data(data)
    
if __name__ == "__main__":
    main()    