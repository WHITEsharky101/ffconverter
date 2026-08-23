import os
import subprocess
import time
import pickle
import re
import create_ffmpeg_config
from create_ffmpeg_config import AudioSubStream          # noqa: F401  (public API + pickle identity)
from create_ffmpeg_config import FFmpegParam            # noqa: F401

from ffcore.storage import save_data, load_config       # noqa: F401  (save_data re-export for symmetry)
from ffcore.text import process_string, format_timings, format_time  # noqa: F401  (process_string re-export for tests)
from ffcore.ffmpeg import TUNE_LIST, codec_tag, generate_ffmpeg_command, generate_ffmpeg_input_files, generate_ffmpeg_output_files, generate_ffmpeg_tune_config, generate_ffmpeg_video_config, generate_ffmpeg_audio_config, generate_ffmpeg_mapping_and_meta, generate_ffmpeg_sub_fonts, count_embedded_text_streams, find_episode_files, choose_candidate  # noqa: F401
from ffcore.prompting import ask_index                  # noqa: F401

SAVE_FILE = 'streams_data.pkl'
# Файл журнала конвертаций — рядом с исходным кодом
CONVERTLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'convertlist.txt')

# Функция для загрузки данных из файла, если он существует
def load_data():
    while True:
        if not os.path.exists(SAVE_FILE):
            create_ffmpeg_config.main()
            continue
        streams, params = load_config(SAVE_FILE)
        choice = input(f"\nЗагрузить данные для: {params.path} ?(y/n) ").strip().lower()
        if choice in ("y", "н"):
            return streams, params
        if choice in ("n", "т"):
            create_ffmpeg_config.main()
            try:
                return load_config(SAVE_FILE)
            except pickle.UnpicklingError as e:
                print(f"Ошибка при загрузке данных: {e}")
                return streams, params
        print("Неверный ввод")

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

    tune_idx = ask_index("\nВыберите пресет: ", TUNE_LIST)
    tune = TUNE_LIST[tune_idx] if tune_idx is not None else ""

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

def run_episode(audio_sub_streams, params, episode, sp):
    """Run one ffmpeg conversion, stream its output, log the timing line."""
    ffmpeg_command = generate_ffmpeg_command(audio_sub_streams, params, episode, sp)
    print(ffmpeg_command)
    start_time = time.time()
    process = subprocess.Popen(
        ffmpeg_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    if process.returncode != 0:
        print("Произошла ошибка при выполнении команды ffmpeg")
        formatted_time = "ERROR!!!"
    else:
        formatted_time = format_time(time.time() - start_time)
    season = "00" if sp else params.season
    append_to_file(episode_log_line(params, season, episode, formatted_time))

def append_to_file(text):
    file_path = CONVERTLIST_PATH
    try:
        with open(file_path, 'a', encoding='utf-8') as file:
            file.write(text + '\n')
    except Exception as e:
        print(f'Ошибка при добавлении текста в файл: {e}')

def episode_log_line(params, season, episode, formatted_time):
    """One convertlist.txt line. Shared by the normal and sp (S00) loops."""
    return f"{params.name} S{season}E{episode} [{params.crf}][{formatted_time}]"

def main():
    audio_sub_streams, params = load_data()
    params = collect_inputs(audio_sub_streams, params)
    for episode in params.sp_episodes:
        run_episode(audio_sub_streams, params, episode, True)
    for episode in params.episodes:
        run_episode(audio_sub_streams, params, episode, False)
    append_to_file("===============================")

if __name__ == "__main__":
    main()
