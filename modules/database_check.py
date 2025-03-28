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

def check_database(args):
    """Handle the 'dbcheck' command to inspect the database."""
    config = utils.load_config()
    cache_folder = Path(config.get("cache_folder", "cache log"))
    db_path = cache_folder / "integrity_check.db"

    verbose = getattr(args, 'verbose', False)
    verify = getattr(args, 'verify', False)
    export_csv = getattr(args, 'csv', False)
    export_json = getattr(args, 'json', False)
    filter_status = getattr(args, 'filter', 'all')
    update_db = getattr(args, 'update', False)
    watch = getattr(args, 'watch', False)  # New watch flag
    quick_check = getattr(args, 'check', False)  # New check flag

    # Generate export filenames if requested
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    csv_file = f"dbcheck-{filter_status}-{timestamp}.csv" if export_csv else None
    json_file = f"dbcheck-{filter_status}-{timestamp}.json" if export_json else None

    print(f"Checking database at: {db_path}")
    if not check_database_exists(db_path):
        print(f"Error: Database '{db_path}' does not exist.")
        return

    if watch:
        watch_database(db_path)
        return

    if quick_check:
        quick_check_database(db_path)
        return

    if update_db:
        update_database_schema(db_path)

    passed_count, failed_count, error = get_database_summary(db_path)
    if error:
        print(error)
        return

    print(f"Initial summary - Passed: {passed_count}, Failed: {failed_count}")
    list_database_entries(db_path, verbose=verbose, verify=verify, export_csv=csv_file, export_json=json_file, filter_status=filter_status)
    print("Database check complete.")

def register_command(subparsers):
    """Register the 'dbcheck' command with the subparsers."""
    dbcheck_parser = subparsers.add_parser("dbcheck", help="Check the integrity database contents")
    dbcheck_parser.add_argument("--verbose", action="store_true", help="List all database entries")
    dbcheck_parser.add_argument("--verify", action="store_true", help="Verify file existence and hashes")
    dbcheck_parser.add_argument("--csv", action="store_true", help="Export results to a CSV file")
    dbcheck_parser.add_argument("--json", action="store_true", help="Export results to a JSON file")
    dbcheck_parser.add_argument("--filter", choices=['all', 'passed', 'failed'], default='all',
                                help="Filter export: 'all' (default), 'passed', or 'failed'")
    dbcheck_parser.add_argument("--update", action="store_true", help="Update database schema for compatibility")
    dbcheck_parser.add_argument("--watch", action="store_true", help="Watch database for real-time updates")
    dbcheck_parser.add_argument("--check", action="store_true", help="Quick check of database entry counts")
    dbcheck_parser.set_defaults(func=check_database)

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
