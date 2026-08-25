import json
import os

from ffcore.models import AudioSubStream, FFmpegParam      # noqa: F401  (public API)
from ffcore.storage import SAVE_FILE, save_data            # noqa: F401
from ffcore.media import find_media_candidates, list_seasons, _parse_season_note  # noqa: F401
from ffcore.ffprobe import ffprobe_media, get_video_codec, has_flac_audio  # noqa: F401
from ffcore.files import media_getter, get_media_ext       # noqa: F401
from ffcore.fonts import find_ttf_in_fonts                 # noqa: F401
from ffcore.prompting import ask_index

ALLOWED_EXTENSIONS = {
    ".mkv", ".mp4", ".mka", ".ass", ".srt", ".flac", ".mp3", ".ac3", ".aac",
    ".m4a", ".avi", ".wav", ".mov", ".wmv"
}
CODECS = ["hevc", "h264"]

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


# Файл настроек мастера — рядом с исходным кодом (сохранённый корень библиотеки)
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')


def _read_library_root():
    """Сохранённый корень библиотеки или None (нет файла / битый JSON / неверный тип)."""
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    root = data.get('library_root')
    if isinstance(root, str) and root:
        return root
    return None


def _save_library_root(root):
    """Сохранить корень библиотеки в settings.json (перезапись)."""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'library_root': root}, f, ensure_ascii=False, indent=2)


def prompt_library_root():
    """Каталог, в котором искать медиа-папки.

    Классическое поведение — текущий каталог (библиотека лежит там же,
    откуда запущен скрипт). Промпт появляется только тогда, когда в
    текущем каталоге нет ни одной медиа-папки — например, когда исходный
    код перенесён на уровень выше корня библиотеки.

    Введённый корень сохраняется в settings.json, чтобы не вводить его
    каждый раз: пустой ввод — использование сохранённого каталога,
    ввод пути — новый каталог (он становится сохранённым).
    """
    if find_media_candidates("", "."):
        return "."
    saved = _read_library_root()
    while True:
        if saved:
            print(f"\nМедиа-папки в текущем каталоге не найдены.\n"
                  f"Сохранённый корень: {saved}\n")
            root = input(
                "Введите путь к корню библиотеки (Enter — сохранённый каталог): "
            ).strip()
        else:
            root = input(
                "\nМедиа-папки в текущем каталоге не найдены.\n"
                "Введите путь к корню библиотеки (Enter — текущий каталог): "
            ).strip()
        if not root:
            if saved:
                # Пустой ввод = сохранённый каталог; если в нём больше нет
                # медиа-папок (библиотека уехала) — переспрашиваем.
                if find_media_candidates("", saved):
                    return saved
                print(f"В каталоге '{saved}' нет медиа-папок. Попробуйте ещё раз.")
                continue
            return "."
        root = os.path.abspath(root)
        if find_media_candidates("", root):
            _save_library_root(root)
            return root
        print(f"В каталоге '{root}' нет медиа-папок. Попробуйте ещё раз.")


def prompt_user_for_media():
    base = prompt_library_root()
    while True:
        name = input("Введите название медиа: ")
        selected = select_media_name(name, base)
        if selected is None:
            print(f"Ничего не найдено по запросу '{name}'. Попробуйте ещё раз.")
            continue
        if selected != name:
            print(f"Выбрано: {selected}")
        name = selected
        break
    base_path = f"{name}/" if base == "." else os.path.join(base, name) + "/"
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
        streams.append(stream)
        i += 1
    return streams, len(streams)
    

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
            title_suggestion = audio_tags[i]
        else:
            if i == len(audio_streams) - 1:
                title_suggestion = "Original"
            else:
                title_suggestion = ""
        print(f"{i:<{index_width}} {(audio_stream.title or '???'):<{name_width}} {(audio_stream.lang or '???'):<{lang_width}} {path:<{path_width}}   ({title_suggestion})")

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
        stream_with_fonts.append(find_ttf_in_fonts(folder_to_probe, stream))
    additional_subtitle_streams = stream_with_fonts
        
    audio_streams = additional_audio_streams + embedded_audio_streams
    subtitle_streams = additional_subtitle_streams + embedded_subtitle_streams
    
    adjust_sub_properties(subtitle_streams) 
    
    display_streams(audio_streams, subtitle_streams, audio_tags)
    
    audio_sub_streams = change_mapping(audio_streams, subtitle_streams, audio_tags)
    
    video_ext, audio_ext, sub_ext = get_media_ext(folder_to_probe, audio_sub_streams)
    
    current_video_codec = get_video_codec(folder_to_probe)
    print(f"\nТекущий видеокодек: {current_video_codec or 'не определен'}")
    idx = ask_index("\nВыберите кодек (По умолчанию как у оригинала): ", CODECS)
    codec = CODECS[idx] if idx is not None else ""
            
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