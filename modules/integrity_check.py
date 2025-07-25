import os
import shutil
import subprocess
import concurrent.futures
from tqdm import tqdm
import datetime
from pathlib import Path
import sqlite3
import threading
import utils  # Import from root directory
import fcntl  # For file-based locking

# Lock file for process coordination
LOCK_FILE = Path("database.lock")

def acquire_lock(lock_file: Path):
    """Acquire an exclusive lock on a file for process coordination."""
    lock_fd = open(lock_file, 'w')
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd

def release_lock(lock_fd):
    """Release the lock and close the file descriptor."""
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    lock_fd.close()

def backup_database(db_path: Path):
    """Create a backup of the database before writing operations."""
    if db_path.exists():
        backup_path = db_path.with_suffix('.db.bak')
        shutil.copy2(db_path, backup_path)
        print(f"Created database backup at: {backup_path}")

def initialize_database(db_path: Path):
    """Initialize the SQLite database with WAL mode and busy timeout.
    
    Creates tables with file_path, mtime, status, and last_checked columns if they don't exist,
    using mtime for caching decisions. Preserves existing tables and their data.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create backup if database exists
    backup_database(db_path)
    
    conn = sqlite3.connect(db_path, timeout=5)  # 5-second busy timeout
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrency
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Create tables if they don't exist, preserving any existing data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS passed_files (
            file_path TEXT PRIMARY KEY,
            mtime REAL,
            status TEXT,
            last_checked TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS failed_files (
            file_path TEXT PRIMARY KEY,
            mtime REAL,
            status TEXT,
            last_checked TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Database initialized with WAL mode at: {db_path}")

def determine_action(db_path: Path, file_path: str, force_recheck: bool = False) -> tuple:
    """Determine the action for a file with process-safe database access.
    
    Uses only mtime to determine whether to use cached results or run a new check.
    Returns a tuple of (action, stored_status, current_mtime).
    """
    if force_recheck:
        try:
            current_mtime = os.path.getmtime(file_path)
            return 'RUN_FFMPEG', None, current_mtime
        except FileNotFoundError:
            return 'FILE_NOT_FOUND', None, None

    try:
        current_mtime = os.path.getmtime(file_path)
    except FileNotFoundError:
        return 'FILE_NOT_FOUND', None, None

    # Use file-based locking for database access
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        for table in ['passed_files', 'failed_files']:
            cursor.execute(f"SELECT status, mtime FROM {table} WHERE file_path = ?", (file_path,))
            result = cursor.fetchone()
            if result:
                stored_status, stored_mtime = result
                if stored_mtime == current_mtime:
                    conn.close()
                    return 'USE_CACHED', stored_status, current_mtime
                else:
                    conn.close()
                    return 'RUN_FFMPEG', None, current_mtime
        conn.close()
        return 'RUN_FFMPEG', None, current_mtime
    finally:
        release_lock(lock_fd)

def check_single_file(file_path: str) -> tuple:
    """Check the integrity of a single audio file using FFmpeg with timeout."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-v', 'error', '-i', file_path, '-f', 'null', '-'],
            capture_output=True, text=True, timeout=30  # 30-second timeout
        )
        status = "PASSED" if not result.stderr else "FAILED"
        message = "" if not result.stderr else result.stderr.strip()
        return status, message, file_path
    except subprocess.TimeoutExpired:
        return "FAILED", "FFmpeg timed out", file_path
    except Exception as e:
        return "FAILED", str(e), file_path

def process_file(db_path: Path, file_path: str, force_recheck: bool = False) -> tuple:
    """Process a file with coordinated database access.
    
    Uses mtime-based caching to determine whether to run FFmpeg check.
    """
    action, stored_status, current_mtime = determine_action(db_path, file_path, force_recheck)
    if action == 'USE_CACHED':
        return ('USE_CACHED', stored_status, "Cached result", file_path, None)
    elif action == 'RUN_FFMPEG':
        status, message, _ = check_single_file(file_path)
        update_info = (file_path, current_mtime, status)
        return ('RUN_FFMPEG', status, message, file_path, update_info)
    else:
        return ('ERROR', "Unknown action", file_path, None)

def cleanup_database(db_path: Path):
    """Remove database entries for files that no longer exist with locking."""
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        for table in ['passed_files', 'failed_files']:
            cursor.execute(f"SELECT file_path FROM {table}")
            for (file_path,) in cursor.fetchall():
                if not os.path.exists(file_path):
                    cursor.execute(f"DELETE FROM {table} WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()
    finally:
        release_lock(lock_fd)

def check_file_integrity(file_path: str) -> dict:
    """Check the integrity of a single audio file and return a dictionary with the results."""
    try:
        status, message, _ = check_single_file(file_path)
        return {
            'file_path': file_path,
            'ok': status == "PASSED",
            'error': message if status == "FAILED" else ""
        }
    except Exception as e:
        return {
            'file_path': file_path,
            'ok': False,
            'error': str(e)
        }

def register_command(subparsers, config):
    """Register the 'check' command with the subparsers."""
    parser = subparsers.add_parser("check", help="Check audio file integrity")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed information")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=check_integrity, config=config)

def check_integrity(args):
    """Handle the 'check' command.
    
    Uses mtime-based caching to determine whether to run FFmpeg checks,
    creating a single database backup before any updates.
    """
    path = args.path
    verbose = args.verbose
    config = args.config
    
    # Use config values with fallbacks
    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    db_path = Path(config['database']['path'])

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

    # Initialize database
    initialize_database(db_path)

    # Process files with parallel execution
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(process_file, db_path, file) for file in audio_files]
        with tqdm(total=len(futures), desc="Checking integrity") as pbar:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    action, status, message, file_path, update_info = result
                    if action == 'USE_CACHED':
                        results.append({
                            'file_path': file_path,
                            'ok': status == "PASSED",
                            'error': ""
                        })
                    elif action == 'RUN_FFMPEG':
                        results.append({
                            'file_path': file_path,
                            'ok': status == "PASSED",
                            'error': message if status == "FAILED" else ""
                        })
                    pbar.update(1)

    # Update database with results - single backup for all updates
    lock_fd = acquire_lock(LOCK_FILE)
    try:
        backup_database(db_path)  # Create single backup before batch update
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().isoformat()
        
        for result in results:
            file_path = result['file_path']
            status = "PASSED" if result['ok'] else "FAILED"
            mtime = os.path.getmtime(file_path)
            
            # Remove from both tables first
            cursor.execute("DELETE FROM passed_files WHERE file_path = ?", (file_path,))
            cursor.execute("DELETE FROM failed_files WHERE file_path = ?", (file_path,))
            
            # Insert into appropriate table
            table = "passed_files" if result['ok'] else "failed_files"
            cursor.execute(f"""
                INSERT INTO {table} (file_path, mtime, status, last_checked)
                VALUES (?, ?, ?, ?)
            """, (file_path, mtime, status, timestamp))
        
        conn.commit()
        conn.close()
    finally:
        release_lock(lock_fd)

    # Print results
    if verbose:
        print("\nDetailed Integrity Check:")
        for result in results:
            print(f"\nFile: {result['file_path']}")
            print(f"Status: {'OK' if result['ok'] else 'ERROR'}")
            if not result['ok']:
                print(f"Error: {result['error']}")
    else:
        print("\nIntegrity Check Summary:")
        ok_count = sum(1 for r in results if r['ok'])
        error_count = len(results) - ok_count
        print(f"Total Files: {len(results)}")
        print(f"OK: {ok_count}")
        print(f"Errors: {error_count}")
        if error_count > 0:
            print("\nFiles with errors:")
            for result in results:
                if not result['ok']:
                    print(f"  {result['file_path']}: {result['error']}")
