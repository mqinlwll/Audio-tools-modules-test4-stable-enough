AUDIO TOOL Documentation
Project Overview
AUDIO TOOL is a command-line interface (CLI) application designed to help users manage, analyze, and process audio files efficiently. Built in Python, it offers a modular structure with various commands to perform tasks like counting albums, analyzing audio metadata, checking file integrity, managing cover art, fetching song links, inspecting a database of file checks, and tracking file states. It leverages multi-processing for speed and includes a SQLite database for caching results, making it ideal for audiophiles, music collectors, or anyone managing large audio libraries.
The project is structured as follows:
.
├── audio_tool.py         # Main script to run the CLI
├── modules               # Directory containing command modules
│   ├── __init__.py       # Makes 'modules' a Python package
│   ├── album_counter.py  # Counts albums, songs, or sizes by codec
│   ├── audio_analysis.py # Analyzes audio file metadata
│   ├── cover_art.py      # Hides or shows cover art files
│   ├── database_check.py # Inspects the integrity database
│   ├── file_tracker.py   # Tracks audio file states
│   ├── integrity_check.py# Verifies audio file integrity
│   └── songlink.py       # Fetches song links from the Odesli API
├── README.md             # Project overview (to be created/updated)
└── utils.py              # Shared utility functions


Setup Instructions
Prerequisites
Before setting up AUDIO TOOL, ensure you have the following:

Python 3.8+: The project uses modern Python features.
FFmpeg: Required for audio analysis and integrity checks (install instructions below).
ffprobe: Part of FFmpeg, used for metadata extraction.
Operating System: Windows, macOS, or Linux.

Dependencies
Install the required Python packages using pip. The project relies on:

mutagen: For reading audio metadata.
tqdm: For progress bars.
colorama: For colored console output (songlink module).
requests: For API calls (songlink module).
pathlib: For cross-platform path handling (built-in).
sqlite3: For database operations (built-in).
concurrent.futures: For parallel processing (built-in).
fcntl: For file-based locking (built-in, Unix-like systems only).

Install them with:
pip install mutagen tqdm colorama requests

Platform-Specific Setup
Windows

Install Python:

Download from python.org.
During installation, check "Add Python to PATH".
Verify: python --version or py --version.


Install FFmpeg:

Download from FFmpeg official site or use a package manager like Chocolatey:choco install ffmpeg


Add FFmpeg to PATH:
Search "Edit the system environment variables" in Windows.
Click "Environment Variables".
Edit "Path" under "System variables", add the FFmpeg bin folder (e.g., C:\Program Files\FFmpeg\bin).


Verify: ffmpeg -version and ffprobe -version.


Setup Project:

Clone or download the project folder.
Open Command Prompt, navigate to the folder:cd path\to\audio_tool


Install dependencies:pip install mutagen tqdm colorama requests





macOS

Install Python:

Use Homebrew: brew install python.
Verify: python3 --version.


Install FFmpeg:

Use Homebrew: brew install ffmpeg.
Verify: ffmpeg -version and ffprobe -version.


Setup Project:

Clone or download the project folder.
Open Terminal, navigate to the folder:cd /path/to/audio_tool


Install dependencies:pip install mutagen tqdm colorama requests





Linux (Ubuntu/Debian)

Install Python:

Update package list: sudo apt update.
Install: sudo apt install python3 python3-pip.
Verify: python3 --version.


Install FFmpeg:

Install: sudo apt install ffmpeg.
Verify: ffmpeg -version and ffprobe -version.


Setup Project:

Clone or download the project folder.
Open Terminal, navigate to the folder:cd /path/to/audio_tool


Install dependencies:pip3 install -r requirements.txt





Python Virtual Environment (Optional but Recommended)
To keep dependencies isolated:

Create a virtual environment:
Windows: python -m venv venv
macOS/Linux: python3 -m venv venv


Activate it:
Windows: venv\Scripts\activate
macOS/Linux: source venv/bin/activate


Install dependencies within the environment:pip install mutagen tqdm colorama requests


Deactivate when done: deactivate

Running the Tool
Once set up, run the tool from the project directory:
python audio_tool.py --help

This displays the ASCII logo and available commands.

Module Descriptions and Usage
Each module provides a specific command for the CLI. Below is an in-depth yet simple explanation of what each does, its options, and how to use it.
1. album_counter.py - Count Albums, Songs, or Sizes
What it does: Scans audio files in directories and counts unique albums, total songs, or their sizes, grouped by codec (e.g., MP3, FLAC).
How it works: It reads metadata (album, artist, codec) using mutagen and ffprobe, then processes files in parallel for speed.
Options:

option: Choose what to count:
album: Counts unique albums (based on artist + album name).
song: Counts total songs.
size: Calculates total file size in MB or GB.


directories: One or more folders to scan.
--workers: Number of parallel processes (default: CPU count).

Usage Examples:

Count albums:python audio_tool.py count album "C:/Music" "D:/MoreMusic"

Output: e.g., mp3: 50 Albums, flac: 20 Albums, Total: 70 Albums.
Count songs:python audio_tool.py count song "C:/Music"


Calculate size:python audio_tool.py count size "C:/Music" --workers 8



For Non-Coders: Think of this as a librarian counting books (albums), pages (songs), or shelf space (size) in your music library, sorted by format.

2. audio_analysis.py - Analyze Audio Metadata
What it does: Examines audio files to show details like bitrate, sample rate, channels, bit depth, and codec.
How it works: Uses ffprobe to extract metadata and flags potential issues (e.g., low quality).
Options:

path: File or directory to analyze.
-o/--output: Output file name (default: audio_analysis.txt).
--verbose: Print results to console instead of a file.
--workers: Number of parallel processes (ignored with --verbose).

Usage Examples:

Analyze a directory and save to file:python audio_tool.py info "C:/Music" -o analysis.txt


Analyze one file with console output:python audio_tool.py info "song.mp3" --verbose

Output: e.g., Bitrate: 320000 bps, Sample Rate: 44100 Hz, Channels: Stereo.

For Non-Coders: It’s like getting a detailed report card for each song, telling you its quality and format.

3. cover_art.py - Hide or Show Cover Art
What it does: Renames cover art files (e.g., cover.jpg) to hide them with a dot (.cover.jpg) or show them by removing it.
How it works: Scans directories for common cover art names and renames them in parallel.
Options:

--hide: Hide cover art (adds dot).
--show: Show hidden cover art (removes dot).
path: Directory to process.
--workers: Number of parallel processes.

Usage Examples:

Hide cover art:python audio_tool.py cover-art --hide "C:/Music"


Show hidden cover art:python audio_tool.py cover-art --show "C:/Music"



For Non-Coders: Imagine putting a “do not disturb” sign on album covers (hide) or taking it off (show).

4. database_check.py - Inspect Integrity Database
What it does: Checks a SQLite database (integrity_check.db) that tracks audio file integrity results.
How it works: Reads the database, optionally verifies files, and can export data.
Options:

--verbose: List all entries.
--verify: Check if files still exist and match their hashes.
--csv: Export to CSV file.
--json: Export to JSON file.
--filter: Show only all, passed, or failed entries.
--update: Add missing database columns (e.g., mtime).

Usage Examples:

Basic check:python audio_tool.py dbcheck


Detailed check with export:python audio_tool.py dbcheck --verbose --verify --csv --filter failed



For Non-Coders: It’s like checking a logbook of past audio file tests to see what’s changed or gone missing.

5. file_tracker.py - Track Audio File States
What it does: Tracks the state of audio files by storing their modification times in a SQLite database, detecting changes or missing files.
How it works: Records each file’s modification time (mtime) and updates the database if changes are detected, using file-based locking for process safety.
Options:

paths: One or more files or directories to track.
--verbose: Print detailed tracking information.
--workers: Number of parallel processes (default: CPU count).

Usage Examples:

Track files in a directory:python audio_tool.py track "C:/Music"

Output: e.g., Total Files: 100, Added: 50, Updated: 30, Unchanged: 20, Errors: 0.
Track a single file with verbose output:python audio_tool.py track "song.mp3" --verbose



For Non-Coders: It’s like keeping a diary of when your music files were last changed, alerting you if they’re missing or modified.

6. integrity_check.py - Verify Audio File Integrity
What it does: Tests audio files with FFmpeg to ensure they play without errors, caching results in a database.
How it works: Runs FFmpeg silently, logs passed/failed files, and uses hashes and modification times to skip unchanged files.
Options:

path: File or directory to check.
--verbose: Show detailed results.
--summary: Show only progress and summary.
--save-log: Save results to log files.
--recheck: Force recheck all files.
--workers: Number of parallel processes.

Usage Examples:

Check a directory:python audio_tool.py check "C:/Music"


Verbose check on one file:python audio_tool.py check "song.mp3" --verbose



For Non-Coders: It’s like a doctor checking if your songs are healthy, keeping a record to avoid retesting.

7. songlink.py - Fetch Song Links
What it does: Gets streaming links (e.g., Spotify, Apple Music) for a song URL using the Odesli API.
How it works: Queries the API and displays or saves links with colored output.
Options:

--url: Single song URL.
--file: Text file with URLs.
--country: Country code (e.g., US).
--songIfSingle: Treat singles as songs.
-s/--select: Specific services (e.g., spotify tidal).
-o/--output: Save links to a file.

Usage Examples:

Fetch links for one song:python audio_tool.py songlink --url "https://youtu.be/example"


Save specific links:python audio_tool.py songlink --url "https://youtu.be/example" -s spotify apple_music -o links.txt



For Non-Coders: It’s like asking a friend to find all the places you can listen to a song online.

Additional Notes

Configuration: Some modules use audio-script-config.yaml for settings like log folders. Edit this file to customize paths.
Logs and Cache: Results may be saved in Logs or cache log folders, created automatically.
Performance: Use --workers to adjust speed based on your CPU.
