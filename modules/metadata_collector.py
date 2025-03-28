import os
import subprocess
import concurrent.futures
from tqdm import tqdm
import datetime
from pathlib import Path
import sqlite3
import mutagen
import csv
import json
import utils  # Assumes this exists with get_audio_files and path_type
import fcntl  # For file-based locking

# Lock file for process coordination
LOCK_FILE = Path("database.lock")

### Locking Functions ###
def acquire_lock(lock_file: Path):
    """Acquire an exclusive lock on a file for process coordination."""
    lock_fd = open(lock_file, 'w')
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd

def release_lock(lock_fd):
    """Release the lock and close the file descriptor."""
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()

### Database Initialization ###
def initialize_database(db_path: Path):
    """Initialize the SQLite database with WAL mode and busy timeout."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_metadata (
            file_path TEXT PRIMARY KEY,
            track_number TEXT,
            disc_number TEXT,
            track_total TEXT,
            disc_total TEXT,
            codec TEXT,
            sample_rate INTEGER,
            bitrate INTEGER,
            bit_depth INTEGER,
            channels INTEGER,
            artist TEXT,
            album TEXT,
            album_artist TEXT,
            title TEXT,
            isrc TEXT,
            upc TEXT,
            date TEXT,
            last_checked TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Database initialized with WAL mode at: {db_path}")

### Codec Detection for .m4a Files ###
def get_m4a_codec(file_path: str) -> str:
    """Get the codec of an .m4a file using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            capture_output=True, text=True, timeout=10
        )
        codec = result.stdout.strip()
        if codec == 'aac':
            return 'AAC'
        elif codec == 'alac':
            return 'ALAC'
        elif codec == 'ec-3':
            return 'E-AC-3 (Dolby Digital Plus)'  # Often indicates Atmos in .m4a
        else:
            return codec
    except Exception:
        return 'Unknown'

### Metadata Extraction ###
def extract_metadata(file_path: str) -> dict:
    """Extract metadata from an audio file using mutagen and ffprobe for .m4a codecs."""
    metadata = {}
    try:
        file = mutagen.File(file_path)
        if file is None:
            metadata['error'] = 'Unsupported file type'
            return metadata

        # Technical metadata
        if isinstance(file, mutagen.mp4.MP4):
            metadata['codec'] = get_m4a_codec(file_path)
        else:
            metadata['codec'] = getattr(file.info, 'codec', 'Unknown')
        metadata['sample_rate'] = getattr(file.info, 'sample_rate', None)
        metadata['bitrate'] = getattr(file.info, 'bitrate', None)
        metadata['bit_depth'] = getattr(file.info, 'bits_per_sample', None)
        metadata['channels'] = getattr(file.info, 'channels', None)

        # Tags based on file type
        if isinstance(file, mutagen.mp3.MP3):
            metadata['track_number'] = str(file.get('TRCK', ''))
            if '/' in metadata['track_number']:
                track, total = metadata['track_number'].split('/')
                metadata['track_number'] = track
                metadata['track_total'] = total
            else:
                metadata['track_total'] = None
            metadata['disc_number'] = str(file.get('TPOS', ''))
            if '/' in metadata['disc_number']:
                disc, total = metadata['disc_number'].split('/')
                metadata['disc_number'] = disc
                metadata['disc_total'] = total
            else:
                metadata['disc_total'] = None
            metadata['artist'] = str(file.get('TPE1', ''))
            metadata['album'] = str(file.get('TALB', ''))
            metadata['album_artist'] = str(file.get('TPE2', ''))
            metadata['title'] = str(file.get('TIT2', ''))
            metadata['isrc'] = str(file.get('TSRC', ''))
            metadata['upc'] = None  # UPC not standard in MP3
            metadata['date'] = str(file.get('TDRC', ''))
        elif isinstance(file, mutagen.flac.FLAC):
            metadata['track_number'] = file.get('tracknumber', [''])[0]
            metadata['track_total'] = file.get('tracktotal', [''])[0]
            metadata['disc_number'] = file.get('discnumber', [''])[0]
            metadata['disc_total'] = file.get('disctotal', [''])[0]
            metadata['artist'] = file.get('artist', [''])[0]
            metadata['album'] = file.get('album', [''])[0]
            metadata['album_artist'] = file.get('albumartist', [''])[0]
            metadata['title'] = file.get('title', [''])[0]
            metadata['isrc'] = file.get('isrc', [''])[0]
            metadata['upc'] = file.get('upc', [''])[0] or None
            metadata['date'] = file.get('date', [''])[0]
        elif isinstance(file, mutagen.mp4.MP4):
            trkn = file.tags.get('trkn', [(None, None)])[0]
            metadata['track_number'] = str(trkn[0]) if trkn[0] else None
            metadata['track_total'] = str(trkn[1]) if trkn[1] else None
            disk = file.tags.get('disk', [(None, None)])[0]
            metadata['disc_number'] = str(disk[0]) if disk[0] else None
            metadata['disc_total'] = str(disk[1]) if disk[1] else None
            metadata['artist'] = file.tags.get('©ART', [''])[0]
            metadata['album'] = file.tags.get('©alb', [''])[0]
            metadata['album_artist'] = file.tags.get('aART', [''])[0]
            metadata['title'] = file.tags.get('©nam', [''])[0]
            metadata['isrc'] = file.tags.get('----:com.apple.iTunes:ISRC', [''])[0]
            metadata['upc'] = file.tags.get('----:com.apple.iTunes:UPC', [''])[0] or None
            metadata['date'] = file.tags.get('©day', [''])[0]
        else:
            metadata['error'] = 'Unsupported file type'
    except Exception as e:
        metadata['error'] = str(e)
    return metadata

### Action Determination ###
def determine_action(db_path: Path, file_path: str, force_recheck: bool = False) -> tuple:
    """Determine if metadata needs to be extracted based on file mtime."""
    try:
        current_mtime = os.path.getmtime(file_path)
    except FileNotFoundError:
        return 'FILE_NOT_FOUND', None

    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT last_checked FROM audio_metadata WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        if result and not force_recheck:
            last_checked = datetime.datetime.fromisoformat(result[0])
            if last_checked >= datetime.datetime.fromtimestamp(current_mtime):
                conn.close()
                return 'USE_CACHED', None
        conn.close()
        return 'EXTRACT_METADATA', current_mtime
    finally:
        release_lock(lock_fd)

### File Processing ###
def process_file(db_path: Path, file_path: str, force_recheck: bool = False) -> tuple:
    """Process a file to extract and store metadata."""
    action, current_mtime = determine_action(db_path, file_path, force_recheck)
    if action == 'USE_CACHED':
        return 'USE_CACHED', None
    elif action == 'EXTRACT_METADATA':
        metadata = extract_metadata(file_path)
        if 'error' in metadata:
            return 'ERROR', metadata['error']
        data = (
            file_path,
            metadata.get('track_number'),
            metadata.get('disc_number'),
            metadata.get('track_total'),
            metadata.get('disc_total'),
            metadata.get('codec'),
            metadata.get('sample_rate'),
            metadata.get('bitrate'),
            metadata.get('bit_depth'),
            metadata.get('channels'),
            metadata.get('artist'),
            metadata.get('album'),
            metadata.get('album_artist'),
            metadata.get('title'),
            metadata.get('isrc'),
            metadata.get('upc'),
            metadata.get('date'),
            datetime.datetime.now().isoformat()
        )
        return 'EXTRACTED', data
    return 'ERROR', 'Unknown action'

### Database Cleanup ###
def cleanup_database(db_path: Path):
    """Remove database entries for files that no longer exist."""
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM audio_metadata")
        for (file_path,) in cursor.fetchall():
            if not os.path.exists(file_path):
                cursor.execute("DELETE FROM audio_metadata WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()
    finally:
        release_lock(lock_fd)

### Export Functionality ###
def export_database(db_path: Path, format: str, output_file: str):
    """Export the database to CSV or JSON."""
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audio_metadata")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        if format == 'csv':
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
        elif format == 'json':
            data = [dict(zip(columns, row)) for row in rows]
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        conn.close()
    finally:
        release_lock(lock_fd)

### Main Command Handler ###
def collect_metadata(args):
    """Handle the 'metadata' command."""
    path = args.path
    verbose = args.verbose
    summary = args.summary
    force_recheck = args.recheck
    export_format = args.export
    num_workers = args.workers if args.workers is not None else (os.cpu_count() or 4)
    config = utils.load_config()

    cache_folder = Path(config.get("cache_folder", "cache log"))
    db_path = cache_folder / "metadata.db"

    initialize_database(db_path)

    # Get audio files
    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in utils.AUDIO_EXTENSIONS:
        audio_files = [path]
    elif os.path.isdir(path):
        audio_files = utils.get_audio_files(path)
        if not audio_files:
            print(f"No audio files found in '{path}'.")
            return
    else:
        print(f"'{path}' is not a file or directory.")
        return

    total_files = len(audio_files)
    extracted_count = 0
    cached_count = 0
    error_count = 0

    if verbose:
        # Sequential processing for verbose output
        for file_path in audio_files:
            action, result = process_file(db_path, file_path, force_recheck)
            if action == 'USE_CACHED':
                cached_count += 1
                print(f"Cached: {file_path}")
            elif action == 'EXTRACTED':
                extracted_count += 1
                data = result
                print(f"Extracted: {file_path}")
                for key, value in zip([desc[0] for desc in sqlite3.connect(db_path).cursor().execute("PRAGMA table_info(audio_metadata)").fetchall()], data):
                    if key != 'file_path' and key != 'last_checked':
                        print(f"  {key}: {value}")
                lock_fd = acquire_lock(LOCK_FILE)
                try:
                    conn = sqlite3.connect(db_path, timeout=5)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO audio_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', data)
                    conn.commit()
                    conn.close()
                finally:
                    release_lock(lock_fd)
            else:
                error_count += 1
                print(f"Error: {file_path} - {result}")
    else:
        # Concurrent processing
        extracted_data = []
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(process_file, db_path, file, force_recheck) for file in audio_files]
            with tqdm(total=len(futures), desc="Processing files") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    action, result = future.result()
                    if action == 'USE_CACHED':
                        cached_count += 1
                    elif action == 'EXTRACTED':
                        extracted_count += 1
                        extracted_data.append(result)
                    else:
                        error_count += 1
                    pbar.update(1)

        # Batch update database
        if extracted_data:
            lock_fd = acquire_lock(LOCK_FILE)
            try:
                conn = sqlite3.connect(db_path, timeout=5)
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT OR REPLACE INTO audio_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', extracted_data)
                conn.commit()
                conn.close()
            finally:
                release_lock(lock_fd)

    # Cleanup and export
    cleanup_database(db_path)
    if export_format:
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        output_file = f"metadata_export_{timestamp}.{export_format}"
        export_database(db_path, export_format, output_file)
        print(f"Metadata exported to {output_file}")

    # Summary
    if summary or not verbose:
        print(f"\nSummary:\nTotal files: {total_files}\nExtracted: {extracted_count}\nCached: {cached_count}\nErrors: {error_count}")

### Command Registration ###
def register_command(subparsers):
    """Register the 'metadata' command with the subparsers."""
    parser = subparsers.add_parser("metadata", help="Collect audio file metadata")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed metadata")
    parser.add_argument("--summary", action="store_true", help="Show summary only")
    parser.add_argument("--recheck", action="store_true", help="Force re-extraction of metadata")
    parser.add_argument("--export", choices=['csv', 'json'], help="Export metadata to CSV or JSON")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=collect_metadata)

if __name__ == "__main__":
    # For testing purposes
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register_command(subparsers)
    args = parser.parse_args()
    args.func(args)
