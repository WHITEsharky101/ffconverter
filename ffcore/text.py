"""Episode-range and timing string parsing (pure)."""
import re

# Максимальная ширина диапазона эпизодов (включительно). Защита от опечаток
# вроде "1-10000000", которая иначе материализует миллион элементов.
MAX_RANGE_SPAN = 10000


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


def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"
