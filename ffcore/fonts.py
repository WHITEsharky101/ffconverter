"""Font discovery and archive extraction (zip/rar)."""
import os
import zipfile
import rarfile


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
