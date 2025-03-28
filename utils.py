import os
import shutil
import json
from pathlib import Path
import argparse

# Supported audio file extensions
AUDIO_EXTENSIONS = ['.flac', '.wav', '.m4a', '.mp3', '.ogg', '.opus', '.ape', '.wv', '.wma']

# Configuration file path
CONFIG_FILE = Path("audio-script-config.json")

def load_config():
    """Load configuration from JSON file or create a default one if it doesn't exist."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    else:
        default_config = {"log_folder": "Logs"}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)
        return default_config

def get_audio_files(directory: str) -> list:
    """Recursively find audio files in a directory."""
    audio_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in AUDIO_EXTENSIONS:
                audio_files.append(os.path.join(root, file))
    return audio_files

def is_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and available in PATH."""
    return shutil.which('ffmpeg') is not None

def is_ffprobe_installed() -> bool:
    """Check if ffprobe is installed and available in PATH."""
    return shutil.which('ffprobe') is not None

def directory_path(path: str) -> str:
    """Custom argparse type to validate directory paths."""
    if os.path.isdir(path):
        return path
    raise argparse.ArgumentTypeError(f"'{path}' is not a directory")

def path_type(path: str) -> str:
    """Custom argparse type to validate existing paths (file or directory)."""
    if os.path.exists(path):
        return path
    raise argparse.ArgumentTypeError(f"'{path}' does not exist")
