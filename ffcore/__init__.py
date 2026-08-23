"""Core (non-interactive) logic for ffconverter.

The CLI entry scripts create_ffmpeg_config.py and ffmpeg_converter.py
compose this package. Nothing here calls input() except the single
sanctioned helper ffcore.prompting.ask_index, which both CLIs share.
"""
