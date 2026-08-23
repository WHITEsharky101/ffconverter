"""Season / media-folder search (used by the config wizard)."""
import os
import re

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
