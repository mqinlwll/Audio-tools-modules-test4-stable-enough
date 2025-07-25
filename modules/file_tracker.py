import os
import sqlite3
import datetime
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import utils  # Import from root directory
import fcntl  # For file-based locking

# Lock file for process coordination
LOCK_FILE = Path("database.lock")

def acquire_lock(lock_file: Path):
    """Acquire an exclusive lock on a file for process coordination."""
    lock_fd = open(lock_file, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError as e:
        lock_fd.close()
        raise RuntimeError(f"Failed to acquire lock: {e}")
    return lock_fd

def release_lock(lock_fd):
    """Release the lock and close the file descriptor."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        lock_fd.close()

def initialize_database(db_path: Path, timeout: int):
    """Initialize the SQLite database with WAL mode to store file tracking data."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_tracker (
            file_path TEXT PRIMARY KEY,
            mtime REAL,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(f"File tracker database initialized at: {db_path}")

def get_file_mtime(file_path: str) -> float:
    """Get the modification time of a file."""
    try:
        return os.path.getmtime(file_path)
    except (FileNotFoundError, OSError):
        return None

def track_file(db_path: Path, file_path: str, timeout: int) -> tuple:
    """Track or update a file's state in the database."""
    mtime = get_file_mtime(file_path)
    if mtime is None:
        return 'FILE_NOT_FOUND', f"File not found: {file_path}"

    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        cursor = conn.cursor()
        cursor.execute("SELECT mtime FROM file_tracker WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        
        current_time = datetime.datetime.now().isoformat()
        if result:
            stored_mtime = result[0]
            if stored_mtime == mtime:
                conn.close()
                return 'UNCHANGED', f"File unchanged: {file_path}"
            else:
                cursor.execute('''
                    UPDATE file_tracker 
                    SET mtime = ?, last_updated = ?
                    WHERE file_path = ?
                ''', (mtime, current_time, file_path))
                conn.commit()
                conn.close()
                return 'UPDATED', f"File updated: {file_path}"
        else:
            cursor.execute('''
                INSERT INTO file_tracker (file_path, mtime, last_updated)
                VALUES (?, ?, ?)
            ''', (file_path, mtime, current_time))
            conn.commit()
            conn.close()
            return 'ADDED', f"File added: {file_path}"
    finally:
        release_lock(lock_fd)

def cleanup_database(db_path: Path, timeout: int):
    """Remove entries for files that no longer exist."""
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM file_tracker")
        for (file_path,) in cursor.fetchall():
            if not os.path.exists(file_path):
                cursor.execute("DELETE FROM file_tracker WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()
    finally:
        release_lock(lock_fd)

def list_tracked_files(db_path: Path, verbose: bool, timeout: int):
    """List all tracked files with their status."""
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, mtime, last_updated FROM file_tracker")
        rows = cursor.fetchall()
        conn.close()

        changed_files = []
        for file_path, stored_mtime, last_updated in rows:
            current_mtime = get_file_mtime(file_path)
            status = "MISSING" if current_mtime is None else "CHANGED" if current_mtime != stored_mtime else "UNCHANGED"
            changed_files.append((file_path, status, stored_mtime, last_updated))

        if verbose:
            print("\nDetailed File Tracking Report:")
            for file_path, status, mtime, last_updated in changed_files:
                print(f"File: {file_path}")
                print(f"Status: {status}")
                print(f"Stored mtime: {mtime}")
                print(f"Last Updated: {last_updated}")
                print("-" * 40)

        total_files = len(changed_files)
        unchanged_count = sum(1 for _, status, _, _ in changed_files if status == "UNCHANGED")
        changed_count = sum(1 for _, status, _, _ in changed_files if status == "CHANGED")
        missing_count = sum(1 for _, status, _, _ in changed_files if status == "MISSING")

        print(f"\nFile Tracking Summary:")
        print(f"Total Files: {total_files}")
        print(f"Unchanged: {unchanged_count}")
        print(f"Changed: {changed_count}")
        print(f"Missing: {missing_count}")
    finally:
        release_lock(lock_fd)

def track_files(args):
    """Handle the 'track' command."""
    paths = args.paths  # Changed from 'path' to 'paths' to reflect multiple inputs
    verbose = args.verbose
    config = args.config

    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    db_path = Path(config['database']['path'])
    db_timeout = config['database']['timeout']

    initialize_database(db_path, db_timeout)

    # Collect audio files from all provided paths
    audio_files = []
    for path in paths:
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in utils.AUDIO_EXTENSIONS:
            audio_files.append(path)
        elif os.path.isdir(path):
            audio_files.extend(utils.get_audio_files(path))
        else:
            print(f"'{path}' is not a valid file or directory.")

    if not audio_files:
        print("No audio files found in the provided paths.")
        return

    added_count = 0
    updated_count = 0
    unchanged_count = 0
    error_count = 0

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(track_file, db_path, file, db_timeout) for file in audio_files]
        with tqdm(total=len(futures), desc="Tracking files") as pbar:
            for future in concurrent.futures.as_completed(futures):
                action, message = future.result()
                if action == 'ADDED':
                    added_count += 1
                elif action == 'UPDATED':
                    updated_count += 1
                elif action == 'UNCHANGED':
                    unchanged_count += 1
                else:
                    error_count += 1
                if verbose:
                    print(message)
                pbar.update(1)

    cleanup_database(db_path, db_timeout)

    print(f"\nTracking Summary:")
    print(f"Total Files: {len(audio_files)}")
    print(f"Added: {added_count}")
    print(f"Updated: {updated_count}")
    print(f"Unchanged: {unchanged_count}")
    print(f"Errors: {error_count}")

def register_command(subparsers, config):
    """Register the 'track' command with the subparsers."""
    parser = subparsers.add_parser("track", help="Track audio file states in database")
    parser.add_argument("paths", type=utils.path_type, nargs='+', help="Files or directories to track")
    parser.add_argument("--verbose", action="store_true", help="Print detailed tracking information")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=track_files, config=config)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Track audio file states")
    subparsers = parser.add_subparsers()
    config = utils.load_config()
    register_command(subparsers, config)
    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()