import os
import subprocess
import time
import json
import re
import shutil
import create_ffmpeg_config
from create_ffmpeg_config import AudioSubStream          # noqa: F401  (public API)
from create_ffmpeg_config import FFmpegParam            # noqa: F401

from ffcore import crf_select
from ffcore.storage import SAVE_FILE, load_config  # noqa: F401  (SAVE_FILE re-exported)
from ffcore.text import process_string, format_timings, format_time  # noqa: F401  (process_string re-export for tests)
from ffcore.ffmpeg import (TUNE_LIST, X265_PARAMS, codec_tag,  # noqa: F401  (test-contract re-exports)
                           generate_ffmpeg_command, generate_ffmpeg_output_files,
                           generate_ffmpeg_tune_config, generate_ffmpeg_video_config,
                           find_episode_files, choose_candidate)
from ffcore.prompting import ask_index                  # noqa: F401

# Файл журнала конвертаций — рядом с исходным кодом
CONVERTLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'convertlist.txt')
# VMAF-модели (vmaf/*.json) лежат рядом с кодом — без env-переменных
VMAF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vmaf')

# Функция для загрузки данных из файла, если он существует
def load_data():
    while True:
        if not os.path.exists(SAVE_FILE):
            create_ffmpeg_config.main()
            continue
        try:
            streams, params = load_config(SAVE_FILE)
        except (ValueError, TypeError, KeyError) as e:
            # Битый streams_data.json — не крашимся, перезапускаем мастер:
            # он пересохранит файл, и на следующей итерации загрузим его.
            print(f"Ошибка при загрузке данных: {e}. Перезапуск мастера настройки.")
            create_ffmpeg_config.main()
            continue
        choice = input(f"\nЗагрузить данные для: {params.path} ?(y/n) ").strip().lower()
        if choice in ("y", "н"):
            return streams, params
        if choice in ("n", "т"):
            create_ffmpeg_config.main()
            try:
                return load_config(SAVE_FILE)
            except (ValueError, TypeError, KeyError) as e:
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
    # Автоподбор CRF (ниже) читает params.episodes/sp_episodes —
    # публикуем введённые списки ДО блока CRF (мастер сохраняет их пустыми).
    params.episodes = episodes
    params.sp_episodes = sp_episodes

    # Пресет спрашивается ДО CRF: автоподбор кодирует сэмплы с тем же
    # -tune, что и финальный энкод (иначе выбранный CRF смещается).
    tune_idx = ask_index("\nВыберите пресет: ", TUNE_LIST)
    tune = TUNE_LIST[tune_idx] if tune_idx is not None else ""
    params.tune_preset = tune

    if params.codec:
        mode = ask_index("\nВыберите способ задания CRF: ",
                         ["Ручной", "Подбор по метрикам (PSNR/SSIM/VMAF)"])
        if mode in (None, 0):
            crf = int(input("\nВведите начальное значение CRF: ") or 18)
        else:
            crf = run_autoselect_crf(params)
            if crf is None:
                crf = int(input("Подбор CRF не дал результата. Введите CRF вручную: ") or 18)
    else:
        crf = None

    while True:
        cut_time = input("\nВведите тайминги для вырезания (Пример: 0 1:30): ")
        if not cut_time:
            break
        cut_time = format_timings(cut_time)
        if cut_time:
            break

    params.crf = crf
    params.cut_time = cut_time
    return params


class _AutoselectError(Exception):
    """Ошибка внутри автоподбора CRF (энкод/замер) — сообщение пользователю."""


def _run_cmd(cmd):
    """ffmpeg-команда автоподбора: stderr стримится в консоль построчно.

    Возвращает (returncode, stderr_text). Живой вывод нужен, чтобы
    пользователь сразу видел реальную ошибку (например, падение init
    libvmaf), а не шаблонное сообщение постфактум. Команды уже с
    -loglevel error, поэтому при успехе выводится ничего.
    """
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8")
    except (OSError, FileNotFoundError) as e:
        raise _AutoselectError(str(e))
    lines = []
    for line in (proc.stderr or []):
        lines.append(line)
        print(line, end="")
    proc.wait()
    return proc.returncode, "".join(lines)


def _ffmpeg_has_vmaf():
    """Есть ли в ffmpeg фильтр libvmaf (по выводу -filters).

    Флаг --enable-libvmaf в configure не гарантирует фильтр, а
    `ffmpeg -h filter=libvmaf` возвращает 0 даже без фильтра —
    единственный надёжный признак: имя libvmaf в списке фильтров
    (vmafmotion не засчитывается).
    """
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8")
    except (OSError, FileNotFoundError):
        return False
    if result.returncode != 0:
        return False
    names = set()
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        # строка списка: флаги(«..») имя входа->выхода описание…
        if len(parts) >= 3 and re.fullmatch(r"[A-Za-z0-9_.]+", parts[1]):
            names.add(parts[1])
    return "libvmaf" in names


def _last_error_line(stderr):
    """Последняя непустая строка stderr (для цитирования в ошибке)."""
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    return lines[-1] if lines else "ffmpeg не выдал текст ошибки"


def _read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def probe_video_info(video_path):
    """(duration, width) первого видео-стрима; None при ошибке.

    Длительность берётся со stream-уровня; если его нет (MKV/Matroska
    не кладёт stream-длительность) — с format-уровня.
    """
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=duration,width:format=duration",
               "-of", "json", video_path]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8")
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        width = int(stream.get("width") or 0)
        raw = stream.get("duration")
        if raw in (None, ""):
            raw = data.get("format", {}).get("duration")
        if raw in (None, ""):
            return None
        return float(raw), width
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def run_autoselect_crf(params):
    """Автоподбор CRF по PSNR/SSIM/VMAF (чистая логика — ffcore/crf_select).

    Бинарный поиск CRF [14, 19] на 3 сэмплах (начало+30с / середина /
    конец-30с) первого выбранного эпизода; пороги PSNR≥50 ∧ SSIM≥0.98 ∧
    VMAF≥96 на каждый сэмпл. Возвращает int CRF или None (фолбэк на ручной
    ввод). Сэмплы живут в скрытой .crf_select/ и удаляются в finally.
    """
    episodes = list(params.episodes)
    season = params.season
    if not episodes:
        episodes = list(params.sp_episodes)
        season = "00"
    if not episodes:
        print("Не выбрано эпизодов — введите CRF вручную.")
        return None
    episode = episodes[0]
    base_name = f"{params.name} S{season}E{episode}"
    video_path = choose_candidate(
        find_episode_files(params.path, base_name, params.video_ext))
    if not video_path:
        print(f"Не найден файл эпизода {base_name} — введите CRF вручную.")
        return None
    print(f"Автоподбор CRF по эпизоду {base_name}")
    info = probe_video_info(video_path)
    if info is None:
        print("Не удалось определить длительность видео — введите CRF вручную.")
        return None
    duration, width = info
    points = crf_select.sample_points(duration)
    if not points:
        print("Эпизод слишком короткий для подбора — введите CRF вручную.")
        return None
    model_path = os.path.join(VMAF_DIR, crf_select.select_model(width))
    if not os.path.exists(model_path):
        print(f"VMAF-модель не найдена: {model_path}")
        return None
    if not _ffmpeg_has_vmaf():
        print("В вашем ffmpeg нет фильтра vmaf (libvmaf не собран) — "
              "автоподбор по метрикам невозможен. Используйте docker-образ "
              "jrottenberg/ffmpeg, в котором он собран, "
              "или введите CRF вручную.")
        return None

    workdir = os.path.join(params.path, ".crf_select")
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    video_config = generate_ffmpeg_video_config(params.codec, params.bit)
    if params.tune_preset:
        video_config += f" -tune {params.tune_preset}"
    enc_args = video_config.split()
    try:
        return _autoselect_search(video_path, points, workdir, model_path,
                                  enc_args)
    except _AutoselectError as e:
        print(f"Ошибка автоподбора CRF: {e}")
        return None
    except Exception as e:  # noqa: BLE001 — любой сбой → ручной ввод
        print(f"Ошибка автоподбора CRF: {e}")
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _autoselect_search(video_path, points, workdir, model_path, enc_args):
    """Бинарный поиск + таблица метрик; выбранный CRF или None."""

    def evaluate(crf):
        sample_metrics = []
        for i, (ss, dur) in enumerate(points):
            enc_path = os.path.join(workdir, f"enc_c{crf}_{i}.mp4")
            rc, err = _run_cmd(crf_select.sample_encode_command(
                video_path, ss, dur, enc_path, enc_args, crf, X265_PARAMS))
            if rc != 0:
                raise _AutoselectError(
                    f"энкод сэмпла {i + 1} (CRF {crf}): "
                    f"{_last_error_line(err)}")
            rc, err = _run_cmd(crf_select.measure_command(
                enc_path, video_path, ss, dur, workdir, model_path))
            if rc != 0:
                raise _AutoselectError(
                    f"замер метрик сэмпла {i + 1} (CRF {crf}): "
                    f"{_last_error_line(err)}")
            psnr = crf_select.parse_psnr_log(_read_file(os.path.join(workdir, "p.log")))
            ssim = crf_select.parse_ssim_log(_read_file(os.path.join(workdir, "s.log")))
            vmaf_pair = crf_select.parse_vmaf_json(os.path.join(workdir, "v.json"))
            if psnr is None or ssim is None or vmaf_pair is None:
                raise _AutoselectError(
                    f"не удалось разобрать метрики сэмпла {i + 1} (CRF {crf})")
            failures = crf_select.gate_failures(psnr, ssim, vmaf_pair[0])
            sample_metrics.append((psnr, ssim, vmaf_pair[0], failures))
        table = (
            f"PSNR {'/'.join(f'{m[0]:.1f}' for m in sample_metrics)} | "
            f"SSIM {'/'.join(f'{m[1]:.4f}' for m in sample_metrics)} | "
            f"VMAF {'/'.join(f'{m[2]:.1f}' for m in sample_metrics)}"
        )
        failing = [m[3] for m in sample_metrics if m[3]]
        if failing:
            why = "; ".join(f"{s + 1}: " + ", ".join(f)
                            for s, f in enumerate(failing) if f)
            print(f"CRF {crf}: {table} → НЕ ПРОХОДИТ ({why})")
            return False
        print(f"CRF {crf}: {table} → ПРОХОДИТ")
        return True

    chosen = crf_select.search_crf(evaluate)
    if chosen is None:
        print(f"Даже CRF {crf_select.CRF_MIN} не проходит пороги "
              "(PSNR≥50, SSIM≥0.98, VMAF≥96).")
        answer = input("Продолжить конвертацию с CRF "
                       f"{crf_select.CRF_MIN} (y/n)? ")
        return crf_select.CRF_MIN if answer.strip().lower() in ("y", "д") else None
    print(f"Выбранный CRF: {chosen}")
    return chosen

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
