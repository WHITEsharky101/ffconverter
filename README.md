# FFmpeg Converter

A Python CLI tool that automates FFmpeg batch conversion of video files in
anime release folders. It walks the library interactively, discovers episodes
matching `<Name> S<NN>E<NN>` patterns, builds FFmpeg command lines with your
chosen parameters, and encodes h264 → x265 (HEVC) with anime-oriented
defaults.

## Features

- **Interactive two-step workflow** — a config wizard (media, season,
  streams, codec) then a conversion step (episodes, tune, CRF, cut timings);
  the wizard's result is saved to `streams_data.json` and can be reloaded
- **Episode discovery** — `<Name> S<NN>E<NN>` files with optional ` [tags]`
  blocks, per-season and special episodes (`S00`)
- **Stream management** — embedded + external audio/subtitle tracks,
  reordering, language/title metadata, default/forced dispositions
- **Font embedding** — TTF/OTF fonts found next to subtitles, with automatic
  extraction of `fonts*.zip`/`fonts*.rar` archives (MKV: `-attach` +
  `0:t:?` mapping of embedded text streams)
- **CRF encoding with manual selection or automatic selection by metrics**
  (PSNR / SSIM / VMAF, binary search over CRF 14–19)
- **x265 tune presets** — `animation`, `grain`, `film` (blank = none);
  asked *before* the CRF question, so CRF samples are encoded with the same
  tune as the final encode
- **Bit depth** — 8/10/12-bit → `-pix_fmt yuv420p|yuv420p10le|yuv420p12le`
- **FLAC → AAC** — optional `libfdk_aac -vbr 5` conversion when FLAC audio
  is present
- **Cut timings** — keep only a `-ss … -to …` range of each episode
- **Batch logging** — every episode appends a line
  (`Name S<NN>E<NN> [crf][HH:MM:SS]`) to `convertlist.txt` next to the code

## Requirements

- **Python 3.8+** (standard library + `rarfile` — the only external
  dependency, used to extract `.rar` font archives)
- **FFmpeg + FFprobe** with `libx265`, `libfdk_aac` and `libvmaf`
  (e.g. the `jrottenberg/ffmpeg:latest` Docker image, ffmpeg 9.x), available
  in PATH

## Installation

```bash
git clone <repo-url>
cd ffconverter
pip install rarfile
```

## How a Run Works

### Step 1 — Config wizard (`create_ffmpeg_config.py`)

Runs automatically on first start (no `streams_data.json` in the CWD) or when
you answer `n` to “Загрузить данные для …?(y/n)”:

1. **Library root** — the CWD when it contains media folders (a directory is
   “media” if it has a `<Name> S<NN>` subfolder); otherwise you are asked for
   the path to the library root. The entered root is persisted to
   `settings.json` (next to the source code, gitignored) so you are not asked
   again: **empty input** re-uses the saved directory, **entering a path**
   switches to the new directory (which becomes the saved one). A saved root
   that no longer contains media folders (library moved/renamed) is rejected
   with a warning and you are asked again. Relative paths are stored as
   absolute. Corrupt/missing `settings.json` is treated as “no saved root”.
2. **Media name** — fuzzy match against media folders
3. **Season** — numbered list parsed from `<Name> S<NN>` folder names, with
   the `[note]` part of the folder name shown (e.g. `S01 [Anidub, AniLibria]`);
   manual entry when no season folders exist
4. **Season folder** — pick one when several match (`<Name> S01`,
   `<Name> S01 [tags]`)
5. **Embedded streams** — audio/subtitle tracks listed from ffprobe
6. **External streams** — paths to extra audio/subtitle files, one per line
   (empty line ends; `/` means the season folder itself)
7. **Subtitle metadata** — adjust language/title per subtitle track
8. **Stream order** — reorder audio/subtitle tracks if needed
9. **Video codec** — `0: hevc`, `1: h264`, Enter = stream copy
10. **Bit depth** — `8`/`10`/`12`, Enter = same as source
11. **Output format** — Enter = same extension as the source video
12. **FLAC → AAC** — asked only when FLAC audio is present

The result is saved to `streams_data.json` in the CWD.

### Step 2 — Conversion (`ffmpeg_converter.py`)

1. **Episodes** — the episode files are listed, then you enter the episodes
   to convert (`1-5 6 9`; blank = all found), and special episodes (`S00`)
   separately
2. **Tune preset** — `0: animation`, `1: grain`, `2: film`, Enter = none
   (x265 only)
3. **CRF** (only when a video codec is selected) — `0: Ручной` (blank = 18)
   or `1: Подбор по метрикам (PSNR/SSIM/VMAF)`
4. **Cut timings** — optional, e.g. `0 1:30` keeps `00:00:00–00:01:30` of
   each episode

Special episodes are converted first, then the regular ones. Each episode
prints its full FFmpeg command and live ffmpeg output, then a log line is
appended to `convertlist.txt`; a `===============================` line
separates runs.

## CRF Auto-Select (by Metrics)

Choosing `1` at the CRF question starts the metric-based selection:

- Three **5-second samples** of the first selected episode (first
  `S00` episode when only special ones are selected): `+30 s` from the
  start (0 when the episode is shorter than 60 s), the middle, and `30 s`
  before the end.
- An integer **binary search over CRF 14–19** (at most 5 sample encodes)
  finds the **largest** CRF for which **all** samples pass **all** gates:

  | Metric | Gate |
  |--------|------|
  | PSNR   | ≥ 50 dB |
  | SSIM   | ≥ 0.98 |
  | VMAF   | ≥ 96    |

- Each round prints a per-sample table, e.g.
  `CRF 17: PSNR 52.8/52.2/52.6 | SSIM 0.9991/0.9988/0.9990 | VMAF 98.1/97.9/98.0 → ПРОХОДИТ`.
- Samples are encoded with the **same tune and x265 params** as the final
  encode (`-x265-params asm=avx512:aq-mode=3:row-mt=1`), so the result is
  representative.
- The VMAF model is auto-selected by width: `vmaf_v0.6.1.json` (1080p) or
  `vmaf_4k_v0.6.1.json` (≥ 3840 px). Models ship in the repo under `vmaf/`.
- Working files live in a hidden `.crf_select/` folder inside the season
  folder and are removed afterwards (in a `finally`, even on error).
- If even CRF 14 fails all gates, you are asked whether to continue with
  CRF 14.
- Any failure (no libvmaf in your ffmpeg, episode too short, missing model,
  parse error) falls back to manual CRF entry and the conversion continues.

VMAF is trained on live-action content: for anime it is a **monotonic
indicator** (compare CRF values against each other), not an absolute quality
score. Metric hierarchy: VMAF is primary, SSIM secondary, PSNR informational.

## Generated FFmpeg Command

Per episode the tool builds (list form, no shell):

```
ffmpeg -analyzeduration 100M -probesize 100M -i "<video>" [-i "<ext audio/subs>"]…
  -map 0:v [-map 0:t:? (MKV only)] [-ss … -to … (cut timings)]
  [-map per stream]
  -c:v libx265 -vtag hvc1 [-pix_fmt yuv420p10le|12le]
  [-c:a copy | per-track -c:a:<i> libfdk_aac -vbr 5 (FLAC conversion)]
  [-attach <font> -metadata:s:t:<n> mimetype=… (MKV only)]
  -c:s copy -max_interleave_delta 0
  [-disposition / -metadata per stream]
  [-tune animation|grain|film] -crf <crf>
  -preset slow -threads 0
  [-x265-params asm=avx512:aq-mode=3:row-mt=1 (hevc only)]
  "<Name> S<NN>E<NN> [HEVC]<ext>" -y
```

Notes:

- x265-only options go **only** through `-x265-params` — top-level
  `-aq-mode`/`-row-mt` are silently ignored by ffmpeg. For h264/copy the
  flag is dropped entirely (an orphan `-x265-params` would swallow the
  output path as its value).
- Output name: brackets `[HEVC]`/`[AV1]` are added only for those codecs;
  h264 and stream copy produce a bare name.
- `aq-mode=3` is the anime AQ setting (banding in dark scenes); `row-mt=1`
  is a no-op in some x265 builds and harmless.

## Docker Usage

The base `jrottenberg/ffmpeg:latest` image ships **no Python**, so the
converter itself must run in an environment that has both Python and
ffmpeg/ffprobe. Two common setups:

1. **Host install** — install FFmpeg (with libx265 + libvmaf) on the host
   and run `python3 ffmpeg_converter.py` there.
2. **Custom image** — derive from the official image and add Python:

   ```dockerfile
   FROM jrottenberg/ffmpeg:latest
   RUN apt-get update && apt-get install -y --no-install-recommends python3
   ```

   ```bash
   docker run --rm -it -v $(pwd):/work -w /work my-ffconverter python3 ffmpeg_converter.py
   ```

Notes for running FFmpeg directly in the official image:

- The image entrypoint is `ffmpeg` itself. To run an arbitrary command use
  `--entrypoint bash` and pass it via `-c`:
  `docker run --rm --entrypoint bash jrottenberg/ffmpeg:latest -c "ffmpeg ..."`
  (without the entrypoint override, `docker run … bash -c '…'` fails with
  `Error opening output file bash`).
- In ffmpeg 9.x the libvmaf model option is `model=path=<file>` (not
  `model_path=`).
- VMAF models are not in the image — mount the repo's `vmaf/` directory
  (e.g. `-v ./vmaf:/models:ro`) and point the filter at
  `model=path=/models/vmaf_v0.6.1.json`.

## Project Structure

```
ffconverter/
├── ffmpeg_converter.py       # Conversion step: episodes, tune, CRF (manual /
│                             #   auto-select driver), per-episode ffmpeg runs
├── create_ffmpeg_config.py   # Config wizard + FFmpegParam re-exports
├── ffcore/
│   ├── ffmpeg.py             # Pure command builders, episode file discovery,
│   │                         #   X265_PARAMS / TUNE_LIST constants
│   ├── crf_select.py         # CRF auto-select pure logic: sample points,
│   │                         #   bisection, metric parsers, gates
│   ├── ffprobe.py            # ffprobe wrappers (streams, codecs, FLAC check)
│   ├── fonts.py              # TTF/OTF discovery, zip/rar font extraction
│   ├── media.py              # Media-folder / season-folder search
│   ├── files.py              # Media file lookup by extension
│   ├── models.py             # FFmpegParam / AudioSubStream dataclasses
│   ├── prompting.py          # ask_index (numbered menus)
│   ├── storage.py            # streams_data.json save/load (JSON)
│   └── text.py               # Episode-range parsing, cut-timing formatting
├── vmaf/
│   ├── vmaf_v0.6.1.json      # VMAF model (1080p)
│   └── vmaf_4k_v0.6.1.json   # VMAF model (4K, width ≥ 3840)
└── tests/                    # unittest suite (stdlib only)
```

## Tests

Standard-library `unittest` only (no pytest dependency):

```bash
python3 -m unittest discover -s tests
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ffmpeg: command not found` | Put FFmpeg/FFprobe (libx265 + libvmaf builds) in PATH, or run in a custom Docker image |
| `libvmaf not found` / VMAF parse error | Use an ffmpeg build with `--enable-libvmaf`; auto-select falls back to manual CRF |
| No VMAF model in the Docker image | Mount `vmaf/` from the repo and use `model=path=/models/vmaf_v0.6.1.json` |
| `Unknown option "aq-mode"` | x265-only options must go in `-x265-params`, not top-level — already handled |
| `Error opening output file bash` in Docker | The image entrypoint is `ffmpeg`; use `docker run --entrypoint bash <image> -c "ffmpeg ..."` |
| `ModuleNotFoundError: rarfile` | `pip install rarfile` |
| Episode not found | Files must match `<Name> S<NN>E<NN>.<ext>` (tags in brackets allowed) |
| `Ошибка при загрузке данных` (ValueError/TypeError/KeyError) | Corrupt `streams_data.json` — the wizard re-runs automatically and re-saves a fresh file |
| Slow conversion | Use a higher CRF or fewer episodes per run |

## License

MIT
