import os
from pathlib import Path
import sqlite3
import hashlib
from tqdm import tqdm
import datetime
import csv
import json
import time  # Added for watch functionality
import utils  # Import from root directory

def calculate_file_hash(file_path: str) -> str:
    """Calculate the MD5 hash of a file."""
    md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                md5.update(chunk)
        return md5.hexdigest()
    except (FileNotFoundError, PermissionError):
        return None

def check_database_exists(db_path: Path) -> bool:
    """Check if the database file exists."""
    return db_path.exists()

def get_database_summary(db_path: Path) -> tuple:
    """Get a summary of the database contents."""
    if not check_database_exists(db_path):
        return 0, 0, "Database not found"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM passed_files")
    passed_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM failed_files")
    failed_count = cursor.fetchone()[0]

    conn.close()
    return passed_count, failed_count, None

def update_database_schema(db_path: Path):
    """Update the database schema to include new columns if necessary, with a progress bar."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check and update 'passed_files' table
    cursor.execute("PRAGMA table_info(passed_files)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'mtime' not in columns:
        print("Adding 'mtime' column to passed_files...")
        cursor.execute("ALTER TABLE passed_files ADD COLUMN mtime REAL")
        # Get all file paths to update
        cursor.execute("SELECT file_path FROM passed_files")
        file_paths = [row[0] for row in cursor.fetchall()]
        # Update mtime with progress bar
        with tqdm(total=len(file_paths), desc="Updating mtime in passed_files") as pbar:
            for file_path in file_paths:
                try:
                    mtime = os.path.getmtime(file_path)
                    cursor.execute("UPDATE passed_files SET mtime = ? WHERE file_path = ?", (mtime, file_path))
                except (FileNotFoundError, OSError):
                    pass  # Leave mtime as NULL if file is inaccessible
                pbar.update(1)  # Increment progress bar

    # Check and update 'failed_files' table
    cursor.execute("PRAGMA table_info(failed_files)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'mtime' not in columns:
        print("Adding 'mtime' column to failed_files...")
        cursor.execute("ALTER TABLE failed_files ADD COLUMN mtime REAL")
        # Get all file paths to update
        cursor.execute("SELECT file_path FROM failed_files")
        file_paths = [row[0] for row in cursor.fetchall()]
        # Update mtime with progress bar
        with tqdm(total=len(file_paths), desc="Updating mtime in failed_files") as pbar:
            for file_path in file_paths:
                try:
                    mtime = os.path.getmtime(file_path)
                    cursor.execute("UPDATE failed_files SET mtime = ? WHERE file_path = ?", (mtime, file_path))
                except (FileNotFoundError, OSError):
                    pass  # Leave mtime as NULL if file is inaccessible
                pbar.update(1)  # Increment progress bar

    conn.commit()
    conn.close()
    print("Database schema updated successfully.")

def list_database_entries(db_path: Path, verbose: bool = False, verify: bool = False, export_csv: str = None, export_json: str = None, filter_status: str = "all"):
    """List database entries, optionally verifying files, exporting to CSV/JSON, and filtering by status."""
    if not check_database_exists(db_path):
        print(f"Error: Database '{db_path}' not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = {'passed_files': 'PASSED', 'failed_files': 'FAILED'}
    all_entries = []

    for table, status in tables.items():
        # Include mtime in the query if it exists
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        mtime_col = 'mtime' if 'mtime' in columns else 'NULL AS mtime'
        cursor.execute(f"SELECT file_path, file_hash, last_checked, {mtime_col} FROM {table}")
        rows = cursor.fetchall()
        for file_path, stored_hash, last_checked, mtime in rows:
            entry_status = status
            message = ""
            if verify:
                if not os.path.exists(file_path):
                    entry_status = "MISSING"
                    message = "File no longer exists"
                else:
                    current_hash = calculate_file_hash(file_path)
                    if current_hash != stored_hash:
                        entry_status = "CHANGED"
                        message = "Hash mismatch"
                    elif current_hash is None:
                        entry_status = "ERROR"
                        message = "Unable to read file"
            all_entries.append((entry_status, file_path, stored_hash, last_checked, message, mtime))

    conn.close()

    # Filter entries based on --filter argument
    if filter_status == "passed":
        filtered_entries = [entry for entry in all_entries if entry[0] == "PASSED"]
    elif filter_status == "failed":
        filtered_entries = [entry for entry in all_entries if entry[0] in ["FAILED", "MISSING", "CHANGED", "ERROR"]]
    else:  # "all"
        filtered_entries = all_entries

    # Export to CSV if requested
    if export_csv:
        with open(export_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Status", "File Path", "Hash", "Last Checked", "Message", "Mtime"])
            for status, file_path, stored_hash, last_checked, message, mtime in filtered_entries:
                writer.writerow([status, file_path, stored_hash, last_checked, message, mtime])
        print(f"Exported to CSV: {export_csv}")

    # Export to JSON if requested
    if export_json:
        json_data = [
            {
                "status": status,
                "file_path": file_path,
                "hash": stored_hash,
                "last_checked": last_checked,
                "message": message,
                "mtime": mtime
            }
            for status, file_path, stored_hash, last_checked, message, mtime in filtered_entries
        ]
        with open(export_json, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=4)
        print(f"Exported to JSON: {export_json}")

    # Print verbose output if requested
    if verbose:
        for status, file_path, stored_hash, last_checked, message, mtime in all_entries:
            line = f"{status} {file_path} (Hash: {stored_hash}, Last Checked: {last_checked}, Mtime: {mtime})"
            if message:
                line += f": {message}"
            print(line)

    # Summary based on all entries (not filtered)
    passed_count = sum(1 for e in all_entries if e[0] == "PASSED")
    failed_count = sum(1 for e in all_entries if e[0] == "FAILED")
    missing_count = sum(1 for e in all_entries if e[0] == "MISSING")
    changed_count = sum(1 for e in all_entries if e[0] == "CHANGED")
    error_count = sum(1 for e in all_entries if e[0] == "ERROR")

    print(f"\nDatabase Summary:")
    print(f"Total entries: {len(all_entries)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    if verify:
        print(f"Missing: {missing_count}")
        print(f"Changed: {changed_count}")
        print(f"Errors: {error_count}")

def watch_database(db_path: Path, interval: int = 5):
    """Watch the database for changes in real-time."""
    if not check_database_exists(db_path):
        print(f"Error: Database '{db_path}' not found.")
        return

    print(f"Watching database at: {db_path}")
    print(f"Checking for updates every {interval} seconds (Ctrl+C to stop)")

    last_passed, last_failed, _ = get_database_summary(db_path)
    print(f"Initial count - Passed: {last_passed}, Failed: {last_failed}")

    try:
        while True:
            current_passed, current_failed, error = get_database_summary(db_path)
            if error:
                print(error)
                return

            if current_passed != last_passed or current_failed != last_failed:
                print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Database updated:")
                print(f"Passed: {last_passed} → {current_passed}")
                print(f"Failed: {last_failed} → {current_failed}")
                last_passed, last_failed = current_passed, current_failed

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching database.")
    except Exception as e:
        print(f"Error while watching database: {e}")

def quick_check_database(db_path: Path):
    """Quick check of database entries and their status."""
    if not check_database_exists(db_path):
        print(f"Error: Database '{db_path}' not found.")
        return

    passed_count, failed_count, error = get_database_summary(db_path)
    if error:
        print(error)
        return

    total = passed_count + failed_count
    print(f"Database Quick Check ({db_path}):")
    print(f"Total entries: {total}")
    print(f"Passed: {passed_count} ({(passed_count/total)*100:.1f}% if total > 0 else 0)")
    print(f"Failed: {failed_count} ({(failed_count/total)*100:.1f}% if total > 0 else 0)")

def register_command(subparsers, config):
    """Register the 'dbcheck' command with the subparsers."""
    parser = subparsers.add_parser("dbcheck", help="Check database integrity")
    parser.add_argument("--repair", action="store_true", help="Attempt to repair database issues")
    parser.add_argument("--verbose", action="store_true", help="Print detailed information")
    parser.set_defaults(func=check_database, config=config)

def check_database(args):
    """Handle the 'database-check' command."""
    repair = args.repair
    verbose = args.verbose
    config = args.config
    
    # Get database path from config
    db_path = Path(config['database']['path'])
    db_timeout = config['database']['timeout']
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
    
    # Check database integrity
    issues = []
    try:
        conn = sqlite3.connect(db_path, timeout=db_timeout)
        cursor = conn.cursor()
        
        # Check table structure
        cursor.execute("PRAGMA table_info(audio_metadata)")
        columns = [col[1] for col in cursor.fetchall()]
        expected_columns = [
            'file_path', 'track_number', 'disc_number', 'track_total',
            'disc_total', 'codec', 'sample_rate', 'bitrate', 'bit_depth',
            'channels', 'artist', 'album', 'album_artist', 'title',
            'isrc', 'upc', 'date', 'last_checked'
        ]
        
        if set(columns) != set(expected_columns):
            issues.append("Table structure mismatch")
        
        # Check for missing files
        cursor.execute("SELECT file_path FROM audio_metadata")
        for (file_path,) in cursor.fetchall():
            if not os.path.exists(file_path):
                issues.append(f"Missing file: {file_path}")
        
        # Check for invalid data
        cursor.execute("SELECT file_path, sample_rate, bitrate FROM audio_metadata")
        for file_path, sample_rate, bitrate in cursor.fetchall():
            if sample_rate is not None and (sample_rate <= 0 or sample_rate > 1000000):
                issues.append(f"Invalid sample rate in {file_path}: {sample_rate}")
            if bitrate is not None and (bitrate <= 0 or bitrate > 10000000):
                issues.append(f"Invalid bitrate in {file_path}: {bitrate}")
        
        conn.close()
        
    except sqlite3.Error as e:
        issues.append(f"Database error: {str(e)}")
    
    # Print results
    if verbose:
        print("\nDetailed Database Check:")
        if issues:
            print("\nIssues found:")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("\nNo issues found.")
    else:
        print(f"\nDatabase check complete. Found {len(issues)} issues.")
    
    # Repair if requested
    if repair and issues:
        print("\nAttempting repairs...")
        try:
            conn = sqlite3.connect(db_path, timeout=db_timeout)
            cursor = conn.cursor()
            
            # Remove entries for missing files
            cursor.execute("SELECT file_path FROM audio_metadata")
            for (file_path,) in cursor.fetchall():
                if not os.path.exists(file_path):
                    cursor.execute("DELETE FROM audio_metadata WHERE file_path = ?", (file_path,))
            
            # Fix invalid data
            cursor.execute("UPDATE audio_metadata SET sample_rate = NULL WHERE sample_rate <= 0 OR sample_rate > 1000000")
            cursor.execute("UPDATE audio_metadata SET bitrate = NULL WHERE bitrate <= 0 OR bitrate > 10000000")
            
            conn.commit()
            conn.close()
            print("Repairs completed successfully.")
        except sqlite3.Error as e:
            print(f"Error during repair: {str(e)}")

if __name__ == "__main__":
    # This is just for standalone testing - typically this would be part of a larger script
    import argparse
    parser = argparse.ArgumentParser(description="Database integrity checker")
    subparsers = parser.add_subparsers()
    register_command(subparsers)
    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()
