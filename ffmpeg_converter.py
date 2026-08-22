import os
import subprocess
import json
import pickle
import time
import glob
import create_ffmpeg_config
import re
from create_ffmpeg_config import AudioSubStream
from create_ffmpeg_config import FFmpegParam

SAVE_FILE = 'streams_data.pkl' 
TUNE_LIST = ['animation', 'grain', 'film']
# Максимальная ширина диапазона эпизодов (включительно). Защита от опечаток
# вроде "1-10000000", которая иначе материализует миллион элементов.
MAX_RANGE_SPAN = 10000
# Файл журнала конвертаций — рядом с исходным кодом
CONVERTLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'convertlist.txt')
 
# Функция для загрузки данных из файла, если он существует
def load_data():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, 'rb') as f:
            data = pickle.load(f)
            while True:
                import_choice = input(f"\nЗагрузить данные для: {data['params'].path} ?(y/n) ").strip().lower()
                if import_choice == "y" or import_choice == 'н':
                    return data['streams'], data['params']
                elif import_choice == "n" or import_choice == 'т':
                    create_ffmpeg_config.main()
                    try:
                        with open(SAVE_FILE, 'rb') as f:
                            data = pickle.load(f)
                    except pickle.UnpicklingError as e:
                        print(f"Ошибка при загрузке данных: {e}")
                    #data = pickle.load(f)
                    break
                else:
                    print("Неверный ввод") 
            return data['streams'], data['params']
    else:
        create_ffmpeg_config.main()
        return load_data()
        
def collect_inputs(audio_sub_streams, params):
    exts = "mkv|mp4|avi|mov"
    pattern = re.compile(
        rf"^{re.escape(params.name)}\s+S(\d+)E(\d+)(?:\s*\[.*?\])?\.(?:{exts})$",
        re.IGNORECASE
    )
    sp_episodes = []
    episodes = []
    print("\nСписок медиа:\n")
    for file_name in sorted(os.listdir(params.path)):
        match = pattern.match(file_name)
        if match:
            print(file_name)
            season = match.group(1)
            episode = match.group(2)
            
            if season == '00':
                sp_episodes.append(episode)
            elif season == params.season:
                episodes.append(episode)
    input_episodes = input("\nВведите эпизоды для конвертации (Пример: 1-5 6 9): ")
    if input_episodes:
        episodes = process_string(input_episodes)
    if sp_episodes:
        input_episodes = input("\nВведите спец эпизоды для конвертации (Пример: 1-5 6 9): ")
        if input_episodes:
            sp_episodes = process_string(input_episodes)
            
    if params.codec:
        crf = int(input("\nВведите начальное значение CRF: ") or 18)
    else:
        crf = None
        
    while True:
        print()
        for i, tune in enumerate(TUNE_LIST):
            print(f"{i}: {tune}")
        tune = input("\nВыберите пресет: ")
        if not tune:
            break
        if int(tune) >= len(TUNE_LIST):
            print("\nНеверный ввод")
        else:    
            tune = TUNE_LIST[int(tune)]
            break
    
    while True:
        cut_time = input("\nВведите тайминги для вырезания (Пример: 0 1:30): ")
        if not cut_time:
            break
        cut_time = format_timings(cut_time)
        if cut_time:
            break
            
    params.sp_episodes = sp_episodes
    params.episodes = episodes     
    params.crf = crf
    params.tune_preset = tune
    params.cut_time = cut_time
    return params
    
    
def process_string(input_string):
    result = []
    if input_string == '-':
        return result
    
    # Удаляем лишние пробелы
    input_string = re.sub(r'\s*-\s*', '-', input_string.strip())
    
    # Разделяем строку на части, используя пробелы
    parts = input_string.split()

    for part in parts:
        if '-' in part:  # Диапазон чисел
            pieces = part.split('-')
            if len(pieces) != 2:
                print(f"Внимание: некорректный диапазон \"{part}\" — пропускаю")
                continue
            try:
                start, end = int(pieces[0]), int(pieces[1])
            except ValueError:
                print(f"Внимание: некорректный диапазон \"{part}\" — пропускаю")
                continue
            if end < start:
                print(f"Внимание: диапазон \"{part}\" задан наоборот — пропускаю")
                continue
            if end - start > MAX_RANGE_SPAN:
                print(f"Внимание: диапазон \"{part}\" слишком широкий — пропускаю")
                continue
            result.extend([f"{i:02}" for i in range(start, end + 1)])
        else:  # Одиночное число
            try:
                result.append(f"{int(part):02}")
            except ValueError:
                print(f"Внимание: некорректное число \"{part}\" — пропускаю")

    return result

def format_timings(input_str):
    timings = input_str.split()
    
    if len(timings) != 2:
        print("Строка должна содержать ровно два тайминга через пробел.")
        return []

    formatted_timings = []

    for timing in timings:
        parts = list(map(int, timing.split(':')))
        if len(parts) > 3:
            print(f"Тайминг '{timing}' содержит слишком много частей.")
            return []

        while len(parts) < 3:
            parts.insert(0, 0)

        hours, minutes, seconds = parts

        if not (0 <= hours <= 99 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            print(f"Тайминг '{timing}' выходит за пределы допустимых значений.")
            return []

        formatted_timings.append(f"{hours:02}:{minutes:02}:{seconds:02}")

    return f"-ss {formatted_timings[0]} -to {formatted_timings[1]}"

def count_embedded_text_streams(video_path):
    # Количество встроенных t-стримов (шрифтов) в видео-входе. 0, если нет.
    if not video_path or not os.path.exists(video_path):
        return 0
    try:
        return len(create_ffmpeg_config.run_ffprobe(video_path, "t"))
    except Exception:
        return 0

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
    command = ["ffmpeg", "-analyzeduration", "100M", "-probesize", "100M", *input_files, params.cut_time, *mapping, *video_config.split(), *audio_config, *sub_fonts, "-c:s", "copy", "-aq-mode", "3", "-max_interleave_delta", "0", *metadata, *tune_config, "-preset", "slow", "-threads", "0", "-row-mt", "1", "-x265-params", "asm=avx512", output_file, "-y"]
    command = [arg for arg in command if arg != '']
    return command
    
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


def _normalize_ext_list(exts):
    # принимает строку '.mkv' или список ['.mkv','.mp4'] и возвращает ['mkv','mp4']
    if not exts:
        return []
    if isinstance(exts, (list, tuple)):
        return [e.lstrip('.').lower() for e in exts]
    return [exts.lstrip('.').lower()]

def find_media_candidates(dirpath, base_name, exts):
    """
    Возвращает отсортированный список полных путей к файлам в dirpath,
    которые соответствуют шаблону:
      ^base_name (опциональные ' [..]' блоки) . (ext)
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
    video_candidates = find_media_candidates(video_dir, base_name, params.video_ext)
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
            # у вас в коде было условие `if stream.path:` — сохраняю логику: добавляем вход, только если stream.path непустой
            if stream.path:
                # params.audio_ext может быть списком и мы берем i-ый элемент
                audio_ext = params.audio_ext[i] if isinstance(params.audio_ext, (list, tuple)) else params.audio_ext
                aud_candidates = find_media_candidates(search_dir, base_name, audio_ext)
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
            sub_candidates = find_media_candidates(search_dir, base_name, sub_ext)
            sub_path = choose_candidate(sub_candidates, params)
            if sub_path:
                input_files.extend(["-i", sub_path])
            else:
                print(f"Внимание: субтитры не найдены для {base_name} в {search_dir} (ожидалось расширение {sub_ext})")

    return input_files


    
def generate_ffmpeg_output_files(params, index, sp):
    if sp == True:
        season = "00"
    else:
        season = params.season
    base_name = f'{params.name} S{season}E{index} [{params.codec.upper()}]{params.output_ext}'
    if params.path.endswith(".tmp"):
        path = os.path.dirname(params.path)
    else:
        path = params.path
    return os.path.join(path, base_name)
    
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" 

def append_to_file(text):
    #file_path = 'M:\\anime\\convertlist.txt'
    file_path = CONVERTLIST_PATH
    try:
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write(text + '\n')
    except Exception as e:
        print(f'Ошибка при добавлении текста в файл: {e}')    
    
def main():
    audio_sub_streams, pre_params = load_data()
    params = collect_inputs(audio_sub_streams, pre_params)

    for episode in params.sp_episodes: 
        ffmpeg_command = generate_ffmpeg_command(audio_sub_streams, params, episode, True)
        print(ffmpeg_command)
        start_time = time.time()
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8"
        )
        for line in process.stdout:
            print(line, end="")  # Вывод строк в режиме реального времени
        process.wait()
        end_time = time.time()  # Конец замера времени
        if process.returncode != 0:
            print("Произошла ошибка при выполнении команды ffmpeg")
            formatted_time = "ERROR!!!"
        else:
            elapsed_time = end_time - start_time
            formatted_time = format_time(elapsed_time)
        #clean_up
    for episode in params.episodes: 
        ffmpeg_command = generate_ffmpeg_command(audio_sub_streams, params, episode, False)
        print(ffmpeg_command)
        start_time = time.time()
        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8"
        )
        for line in process.stdout:
            print(line, end="")  # Вывод строк в режиме реального времени
        process.wait()
        end_time = time.time()  # Конец замера времени
        if process.returncode != 0:
            print("Произошла ошибка при выполнении команды ffmpeg")
            formatted_time = "ERROR!!!"
        else:
            elapsed_time = end_time - start_time
            formatted_time = format_time(elapsed_time)
        #clean_up

        append_to_file(f'{params.name} S{params.season}E{episode} [{params.crf}][{formatted_time}]')
    
    append_to_file("===============================")
    
if __name__ == "__main__":
    main()    