# FFConverter

FFConverter is an automated video/audio conversion tool built on FFmpeg, specifically designed for batch processing of TV series (primarily anime). It provides intelligent stream mapping, subtitle font attachment, and flexible encoding options through an interactive CLI interface in Russian.

## Features

- **Interactive Configuration Wizard**: Step-by-step setup for conversion parameters and stream mappings
- **Media Name Search**: Type a full name or any substring (case-insensitive); a single or exact match proceeds directly, multiple matches show a numbered list, no match asks you to try again
- **Season Selection List**: Season choice shows a numbered list of the available season folders with whatever the folder name has in its brackets (e.g. `1: S01 [Anidub, AniLibria]`, `2: S02 [Sub]`); folders without brackets are shown bare (`3: S03`); if no season folders match, the old free-form season input is kept
- **Intelligent Stream Mapping**: Automatic detection and selection of embedded audio/subtitle tracks
- **External Stream Support**: Ability to add external audio and subtitle files
- **Font Attachment**: Automatically discovers and attaches fonts from ZIP/RAR archives for ASS subtitles; embedded (attached-in-source) fonts are preserved in MKV output
- **Flexible Encoding Options**: Support for HEVC (libx265), H264 (libx264), and copy modes, with 8/10/12-bit depth selection
- **Current Video Codec Display**: The codec selection prompt shows the source's current video codec (e.g. `Текущий видеокодек: hevc`)
- **FLAC Conversion Gate**: The "convert FLAC to AAC?" question is only asked when a FLAC audio track actually exists (embedded `flac` codec or external `.flac` file); otherwise conversion is skipped automatically
- **Batch Processing**: Convert multiple episodes with configurable ranges
- **Special Episode Handling**: Proper handling of season "00" for OVAs and specials
- **Conversion Logging**: Persistent log of all conversions with timing information
- **Cross-Platform**: Works on Windows and Linux (with some path adjustments needed)

## Project Structure

```
ffconverter/
├── create_ffmpeg_config.py    # CLI layer: config wizard (prompts + main())
├── ffmpeg_converter.py        # CLI layer: episode selection, conversion run, logging, main()
├── ffcore/                    # Core package: pure (non-interactive) logic
│   ├── models.py              # AudioSubStream, FFmpegParam (dataclass, pickle identity)
│   ├── storage.py             # streams_data.pkl load/save (+ legacy __main__ compat)
│   ├── media.py               # season / media-folder search (list_seasons, ...)
│   ├── ffprobe.py             # ffprobe wrappers
│   ├── files.py               # extension rules, media_getter, get_media_ext
│   ├── fonts.py               # font archives (zip/rar) + ttf discovery
│   ├── ffmpeg.py              # all generate_ffmpeg_* command builders, codec_tag
│   ├── text.py                # process_string, format_timings, format_time
│   └── prompting.py           # ask_index() — the single shared input() helper
├── convertlist.txt            # Conversion log with episode timings
├── streams_data.pkl           # Pickle file storing configuration cache
├── .idea/                     # IntelliJ IDEA project files
└── project_info/              # Project documentation directory
```

### Two-layer design

- **CLI layer** (`create_ffmpeg_config.py`, `ffmpeg_converter.py`): owns `main()`,
  all interactive `input()` calls and their exact prompts, and re-exports the
  public names (`AudioSubStream`, `FFmpegParam`, `process_string`, …) so the
  existing test contract and pickle file identity are preserved.
- **Core** (`ffcore/`): all pure logic — data model, storage, media search,
  ffprobe wrappers, ffmpeg command construction, and text parsing. Nothing in
  `ffcore` calls `input()` except the single sanctioned helper
  `ffcore.prompting.ask_index`, which both CLIs share.

## Core Components

### 1. create_ffmpeg_config.py (CLI layer)

**Purpose**: Interactive configuration wizard for setting up conversion parameters and stream mappings. Pure logic lives in `ffcore/` (see `ffcore/` module map); this script holds the prompts and `main()`.

**Key Classes** (defined in `ffcore/models.py`, re-exported here):
- `AudioSubStream`: Represents audio or subtitle streams with metadata (stream index, type, path, fonts, language, title, codec)
- `FFmpegParam`: Stores conversion parameters (name, season, paths, extensions, codec settings, etc.)

**Main Functions**:
- `main()`: Primary interactive configuration flow
- `prompt_user_for_media()`: Collects show name and season number
- `find_media_folder()`: Locates media folder with pattern matching
- `prompt_streams()`: Interactive selection of embedded audio/subtitle tracks
- `collect_additional_streams()`: Collects external audio/subtitle file paths
- `display_streams()`: Shows configured stream order
- `change_mapping()`: Allows reordering of audio/subtitle streams
- `save_data()`: Serializes configuration to `streams_data.pkl` (re-export of `ffcore.storage.save_data`)

**Core helpers re-exported for compatibility** (defined in `ffcore/`): `ffprobe_media`, `get_video_codec`, `has_flac_audio`, `list_seasons`, `find_media_candidates`, `find_ttf_in_fonts`, `get_media_ext`, `media_getter`, `extract_archive`, `find_fonts_in_directory`, `run_ffprobe`.

**Supported Media Types**:
- Video: MKV, MP4, AVI, MOV
- Audio: MKA, FLAC, MP3, AC3, AAC, M4A, WAV, WMV
- Subtitles: SRT, ASS, SUB
- Fonts: TTF, OTF (embedded from ZIP/RAR archives)

### 2. ffmpeg_converter.py (CLI layer)

**Purpose**: Executes FFmpeg conversion commands based on saved configuration. Pure command construction lives in `ffcore/ffmpeg.py`; episode-range/timing parsing in `ffcore/text.py`; this script holds `main()`, `load_data()`, `collect_inputs()`, the conversion loop (`run_episode()`) and `convertlist.txt` logging.

**Main Functions**:
- `main()`: Primary conversion loop
- `load_data()`: Loads configuration from pickle file (with user confirmation)
- `collect_inputs()`: Collects episode numbers and conversion options
- `run_episode()`: Runs one ffmpeg conversion (shared by normal and sp loops)
- `process_string()`: Parses episode range input (e.g., "1-5 7 9") — re-export of `ffcore.text.process_string`
- `format_timings()`: Formats cut/trim timings for FFmpeg — re-export of `ffcore.text.format_timings`
- `generate_ffmpeg_command()`: Assembles complete FFmpeg command (re-export of `ffcore.ffmpeg`)
- `generate_ffmpeg_mapping_and_meta()`: Creates stream mapping and metadata
- `generate_ffmpeg_video_config()`: Configures video codec (copy/hevc/h264/av1)
- `generate_ffmpeg_audio_config()`: Configures audio codec (copy/libfdk_aac)
- `generate_ffmpeg_sub_fonts()`: Attaches fonts to MKV output
- `generate_ffmpeg_input_files()`: Resolves input file paths with pattern matching
- `generate_ffmpeg_output_files()`: Constructs output filename
- `append_to_file()`: Logs conversion results to convertlist.txt

**Video Codec Options**:
- Copy (no re-encode)
- HEVC (libx265 with hvc1 tag)
- H264 (libx264)
- AV1 (libaom-av1) - noted as unavailable

**Bit Depth**: 8/10/12-bit selection maps to `-pix_fmt yuv420p` / `yuv420p10le` / `yuv420p12le`. Empty input keeps the source bit depth. Ignored with a warning when video is copied (`-c:v copy`).

**Audio Handling**:
- Direct copy by default
- Optional FLAC to AAC conversion using libfdk_aac at VBR 5
- Maintains multiple audio tracks with language metadata

**Subtitle Features**:
- Embeds subtitle files with language and title metadata
- Attaches fonts for ASS subtitles (MKV only)
- Supports "forced" flag for on-screen subtitles

**Tune Presets**:
- animation
- grain
- film

**Special Episode Support**:
- Season "00" treated as special episodes (OVA/OVA-like content)

## File Naming Conventions

### Input Pattern
```
{Show Name} S{Season}E{Episode} [optional-tags].{ext}
```
Examples:
- `Uchuu Senkan Yamato 2199 S01E03.mkv`
- `Log Horizon S02E01 [RUS].mkv`
- `Death Note S01E15 [16].mkv`

### Output Pattern
```
{Show Name} S{Season}E{Episode} [{CODEC}]{ext}   # re-encode to HEVC or AV1
{Show Name} S{Season}E{Episode}{ext}             # H264 or codec copy (no brackets)
```
Examples:
- `Uchuu Senkan Yamato 2199 S01E03 [HEVC].mkv`
- `Log Horizon S02E01.mp4` (H264 or copy — no bracket tag)

### Special Episodes
Season "00" indicates special episodes (OVAs, movies, etc.):
- Input: `Show Name S00E01.mkv`
- Output: `Show Name S00E01 [HEVC].mkv`

## Installation

1. Ensure you have Python 3.x installed
2. Install FFmpeg/FFprobe and make sure they're in your system PATH
3. Clone or copy this repository to your local machine
4. (Optional) Install required Python packages:
   ```bash
   pip install rarfile
   ```
   Note: `rarfile` is optional but needed for RAR font extraction

## Usage

### First Time Setup
```bash
python create_ffmpeg_config.py
# Follow interactive prompts to configure streams
```

### Run Conversion
```bash
python ffmpeg_converter.py
# Loads saved config, selects episodes, converts
```

### Resuming After Configuration
```bash
python ffmpeg_converter.py
# Automatically loads existing streams_data.pkl
# Prompts: "Загрузить данные для: {path} ?(y/n)"
```

## Configuration Examples

### Typical Anime Conversion
```
Show: "Uchuu Senkan Yamato 2199"
Season: "1"
Embedded audio: Select Japanese and Russian tracks
External audio: Add "RUS/" folder for Russian dub
External subs: Add "Subs/" folder for subtitles
Codec: HEVC
CRF: 18
Tune: animation
Output: .mkv (preserves fonts)
```

### TV Series with Trimming
```
Show: "Death Note"
Season: "1"
Trim: -ss 00:00:00 -to 01:30:00 (first 90 minutes)
Codec: H264 (compatibility)
Output: .mp4
```

## Conversion Log Format

The `convertlist.txt` tracks:
- Series name and episode
- CRF quality setting used
- Conversion duration (HH:MM:SS)
- Separator lines between series

Format:
```
{Show Name} S{Season}E{Episode} [{CRF}][{HH:MM:SS}]
===============================
```

Example:
```
Uchuu Senkan Yamato 2199 S01E03 [18][01:29:21]
```

## Technical Architecture

### Dependencies
- **Python 3.x**
- **FFmpeg/FFprobe** (system-level)
- **Python Libraries**:
  - `os`, `subprocess`, `json`, `pickle`, `time`, `re` (standard)
  - `rarfile` (optional, for RAR font extraction)
  - `zipfile` (standard, for ZIP font extraction)

### Data Persistence
- Configuration stored in `streams_data.pkl` using Python pickle
- Contains `AudioSubStream` objects list and `FFmpegParam` object
- Allows resuming conversion sessions without reconfiguration
- **Legacy pickle compatibility**: pre-refactor pickles recorded the model classes under `__main__` (the scripts ran as `__main__`). `ffcore/storage.py` registers the `ffcore.models` classes under both module names at import time, so old `streams_data.pkl` files keep loading without migration.

### Stream Mapping Logic
- Video: Always mapped from stream 0
- Embedded fonts (t streams): Mapped via `-map 0:t:?` in MKV output only (MP4 cannot store font attachments); `count_embedded_text_streams()` probes the video input so attached fonts get non-colliding t indices
- Audio: Sequential mapping with first track as default
- Subtitles: Language metadata + forced flag for "Надписи" (signs)
- Fonts: Attached as binary streams with MIME type metadata (MKV only)

### Error Handling
- Missing files: Warning printed, conversion continues
- FFmpeg errors: Return code checked, time logged as "ERROR!!!"
- Pickle corruption: User prompted to reconfigure
- Invalid input: Re-prompts until valid

## Known Issues & TODOs

1. ~~**Bit depth selection**: Code exists but not fully integrated~~ — **Fixed (2026-08-20)**: the config loop now uses `bit_input` correctly, and `generate_ffmpeg_video_config()` maps 8/10/12 to `-pix_fmt yuv420p|yuv420p10le|yuv420p12le` instead of string-concatenating the raw input; bit depth is ignored with a warning for `-c:v copy`.
2. ~~**Font attachment bug**~~ — **Fixed (2026-08-20)**: embedded fonts are now preserved via `-map 0:t:?` (MKV output only — MP4 does not support font attachments), and the `-metadata:s:t:N` counter for `-attach`-ed fonts is offset by the number of embedded t streams so MIME metadata lands on the right streams.
3. ~~**Hardcoded paths**~~ — **Fixed (2026-08-21)**: `append_to_file()` no longer hardcodes `/data/media/anime/convertlist.txt` — the log file is now `convertlist.txt` next to the source code (`CONVERTLIST_PATH`, resolved from the module's own location), so the script works on any machine without edits.
4. **Cleanup**: `#clean_up` placeholder suggests post-conversion processing not implemented
5. **Archive tool path**: `rarfile.UNRAR_TOOL` commented out (line 14) - may need configuration
6. **AV1 codec**: Listed but marked as unavailable ("Его нет" = "It doesn't exist")
7. ~~**media_getter crash**~~ — **Fixed (2026-08-21)**: `media_getter()` now returns `""` for missing/empty folders instead of raising `UnboundLocalError`/`FileNotFoundError`, `ffprobe_media()` always returns a 2-tuple (the no-media branch previously returned a 3-tuple that would crash the caller's unpack), and `get_media_ext()` warns and preserves list parallelism (appends `""`) when external audio/subtitle files are missing, so positional indexing in the converter stays correct.
8. ~~**Episode input crash on invalid range**~~ — **Fixed (2026-08-21)**: `process_string()` no longer raises on malformed episode input — multi-hyphen tokens (`1-2-3`), non-numeric tokens (`abc`), dangling hyphens (`5-`, `-5`) are skipped with a warning, reversed ranges (`5-1`) are skipped with a warning, and ranges wider than `MAX_RANGE_SPAN` (10000) are skipped to prevent materializing millions of elements from a typo (`1-10000000` → `MemoryError`). Valid tokens in the same input are still returned; a fully invalid input yields `[]`, same as pressing Enter.
9. ~~**Orphaned `-tune` broke encodes with a skipped preset**~~ — **Fixed (2026-08-22)**: `generate_ffmpeg_tune_config()` always emitted `-tune <empty>`; the empty-arg filter in `generate_ffmpeg_command()` then left a dangling `-tune` that consumed the `-crf` value, so ffmpeg failed with `Error opening output file 18` on every encode where the preset question was answered with an empty line. `-tune` is now appended only when a tune value is present.
10. ~~**Output filename brackets for h264/copy**~~ — **Fixed (2026-08-22)**: per user rule, the bracket tag in the output name is the codec tag for hevc/av1 only. `codec_tag()` returns `HEVC`/`AV1`/`''`; `generate_ffmpeg_output_files()` appends ` [TAG]` only when non-empty, so h264 and codec copy produce a bare name (the old code printed `[H264]` for h264 and `[]` for copy).
11. ~~**Special episodes (S00) not logged**~~ — **Fixed (2026-08-22)**: the `append_to_file()` call existed only in the normal episode loop. The line format is now `episode_log_line(params, season, episode, formatted_time)`, shared by both loops — the sp loop logs with season `00`, the normal loop keeps the byte-identical legacy line.
12. ~~**`find_ttf_in_fonts` side effects**~~ — **Fixed (2026-08-22)**: the function created a `fonts/` directory in the media tree even when no font archive existed, crashed on a missing subtitle folder, and (POSIX) walked the filesystem root for a `/` subtitle path because `os.path.join(base, "/") == "/"`. Now: `""`/`/` resolves to the season dir itself, a missing search dir returns the stream untouched with no side effects, and `fonts/` is created only when a font archive is actually found.

## Platform Notes
- Developed on Windows (paths like `M:\anime\`)
- `convertlist.txt` is resolved next to the source code (`CONVERTLIST_PATH`), not hardcoded
- Cross-platform Python code (OS-aware path handling)
- Requires FFmpeg in system PATH

## Future Enhancement Opportunities
1. **Batch mode**: Non-interactive configuration via JSON/YAML
2. **Parallel conversion**: Multiple episodes simultaneously
3. **Better error recovery**: Resume failed conversions
4. **Config validation**: Pre-flight checks for missing files
5. **Plugin architecture**: Support for custom codecs/presets
6. **Web UI**: Browser-based configuration
7. **Database logging**: Replace text log with SQLite
8. **Watch folder**: Automatic conversion on new file detection

## License
Not specified (likely personal/private tool)

---
*Last Updated: 2026-08-23*
*Primary Language: Python 3*