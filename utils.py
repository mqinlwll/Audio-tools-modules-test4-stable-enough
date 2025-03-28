import os
import shutil
import yaml
from pathlib import Path
import argparse

# Supported audio file extensions
AUDIO_EXTENSIONS = ['.flac', '.wav', '.m4a', '.mp3', '.ogg', '.opus', '.ape', '.wv', '.wma']

# Configuration file path
CONFIG_FILE = Path("audio-script-config.yaml")

def load_config():
    """Load configuration from YAML file or create a default one if it doesn't exist."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    else:
        default_config = {
            "log_folder": "Logs",
            "cache_folder": "cache log",
            "database": {
                "path": "cache log/metadata.db",
                "timeout": 5
            },
            "export": {
                "default_format": "json",
                "output_dir": "exports"
            },
            "processing": {
                "max_workers": None,  # Will use CPU count if None
                "chunk_size": 1024
            }
        }
        # Create parent directory if it doesn't exist
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
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
