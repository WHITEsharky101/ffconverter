# FFConverter

FFConverter is an automated video/audio conversion tool built on FFmpeg, specifically designed for batch processing of TV series (primarily anime). It provides intelligent stream mapping, subtitle font attachment, and flexible encoding options through an interactive CLI interface in Russian.

## Features

- **Interactive Configuration Wizard**: Step-by-step setup for conversion parameters and stream mappings
- **Intelligent Stream Mapping**: Automatic detection and selection of embedded audio/subtitle tracks
- **External Stream Support**: Ability to add external audio and subtitle files
- **Font Attachment**: Automatically discovers and attaches fonts from ZIP/RAR archives for ASS subtitles; embedded (attached-in-source) fonts are preserved in MKV output
- **Flexible Encoding Options**: Support for HEVC (libx265), H264 (libx264), and copy modes, with 8/10/12-bit depth selection
- **Batch Processing**: Convert multiple episodes with configurable ranges
- **Special Episode Handling**: Proper handling of season "00" for OVAs and specials
- **Conversion Logging**: Persistent log of all conversions with timing information
- **Cross-Platform**: Works on Windows and Linux (with some path adjustments needed)

## Project Structure

```
ffconverter/
├── create_ffmpeg_config.py    # Configuration and stream mapping module
├── ffmpeg_converter.py        # Main conversion execution module
├── convertlist.txt            # Conversion log with episode timings
├── streams_data.pkl           # Pickle file storing configuration cache
├── .idea/                     # IntelliJ IDEA project files
└── project_info/              # Project documentation directory
```

## Core Components

### 1. create_ffmpeg_config.py

**Purpose**: Interactive configuration wizard for setting up conversion parameters and stream mappings.

**Key Classes**:
- `AudioSubStream`: Represents audio or subtitle streams with metadata (stream index, type, path, fonts, language, title, codec)
- `FFmpegParam`: Stores conversion parameters (name, season, paths, extensions, codec settings, etc.)

**Main Functions**:
- `main()`: Primary interactive configuration flow
- `prompt_user_for_media()`: Collects show name and season number
- `find_media_folder()`: Locates media folder with pattern matching
- `ffprobe_media()`: Analyzes media files using ffprobe to detect embedded streams
- `prompt_streams()`: Interactive selection of embedded audio/subtitle tracks
- `collect_additional_streams()`: Collects external audio/subtitle file paths
- `find_ttf_in_fonts()`: Discovers and extracts font archives (ZIP/RAR) for subtitle attachment
- `display_streams()`: Shows configured stream order
- `change_mapping()`: Allows reordering of audio/subtitle streams
- `save_data()`: Serializes configuration to `streams_data.pkl`

**Supported Media Types**:
- Video: MKV, MP4, AVI, MOV
- Audio: MKA, FLAC, MP3, AC3, AAC, M4A, WAV, WMV
- Subtitles: SRT, ASS, SUB
- Fonts: TTF, OTF (embedded from ZIP/RAR archives)

### 2. ffmpeg_converter.py

**Purpose**: Executes FFmpeg conversion commands based on saved configuration.

**Main Functions**:
- `main()`: Primary conversion loop
- `load_data()`: Loads configuration from pickle file (with user confirmation)
- `collect_inputs()`: Collects episode numbers and conversion options
- `process_string()`: Parses episode range input (e.g., "1-5 7 9")
- `format_timings()`: Formats cut/trim timings for FFmpeg
- `generate_ffmpeg_command()`: Assembles complete FFmpeg command
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
{Show Name} S{Season}E{Episode} [{CODEC}]{ext}
```
Examples:
- `Uchuu Senkan Yamato 2199 S01E03 [HEVC].mkv`
- `Log Horizon S02E01 [H264].mp4`

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
3. **Hardcoded paths**: 
   - `append_to_file()` uses hardcoded `/data/media/anime/convertlist.txt` (line 377)
   - Comment suggests Windows path alternative (line 376)
4. **Cleanup**: `#clean_up` placeholder suggests post-conversion processing not implemented
5. **Archive tool path**: `rarfile.UNRAR_TOOL` commented out (line 14) - may need configuration
6. **AV1 codec**: Listed but marked as unavailable ("Его нет" = "It doesn't exist")
7. ~~**media_getter crash**~~ — **Fixed (2026-08-21)**: `media_getter()` now returns `""` for missing/empty folders instead of raising `UnboundLocalError`/`FileNotFoundError`, `ffprobe_media()` always returns a 2-tuple (the no-media branch previously returned a 3-tuple that would crash the caller's unpack), and `get_media_ext()` warns and preserves list parallelism (appends `""`) when external audio/subtitle files are missing, so positional indexing in the converter stays correct.

## Platform Notes
- Developed on Windows (paths like `M:\anime\`)
- Linux path hardcoded in `append_to_file()`: `/data/media/anime/convertlist.txt`
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
*Last Updated: 2026-08-21*
*Primary Language: Python 3*