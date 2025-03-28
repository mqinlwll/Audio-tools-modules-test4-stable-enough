import os
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import utils  # Import from root directory

# Base cover art filenames
BASE_COVER_NAMES = ['cover.jpg', 'cover.jpeg', 'cover.png', 'folder.jpg', 'folder.png']

def rename_file(src: str, dst: str):
    """Rename a file from src to dst."""
    os.rename(src, dst)

def get_files_to_rename(path: str, hide: bool) -> list:
    """Identify cover art files to rename based on hide/show action."""
    files_to_rename = []
    for root, _, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            if hide:
                if file in BASE_COVER_NAMES:
                    new_name = os.path.join(root, "." + file)
                    if not os.path.exists(new_name):
                        files_to_rename.append((file_path, new_name))
            else:
                if file.startswith(".") and file[1:] in BASE_COVER_NAMES:
                    new_name = os.path.join(root, file[1:])
                    if not os.path.exists(new_name):
                        files_to_rename.append((file_path, new_name))
    return files_to_rename

def process_cover_art(args):
    """Handle the 'cover-art' command to hide or show cover art files."""
    path = args.path
    hide = args.hide
    num_workers = args.workers if args.workers is not None else (os.cpu_count() or 4)
    files_to_rename = get_files_to_rename(path, hide)
    if not files_to_rename:
        print(f"No cover art files to {'hide' if hide else 'show'} in '{path}'.")
        return
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(rename_file, src, dst) for src, dst in files_to_rename]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing cover art"):
            try:
                future.result()
            except Exception as e:
                print(f"Error renaming file: {e}")
    print(f"Cover art {'hidden' if hide else 'shown'} successfully.")

def register_command(subparsers, config):
    """Register the 'cover-art' command with the subparsers."""
    parser = subparsers.add_parser("cover-art", help="Extract or embed cover art")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    parser.add_argument("--extract", action="store_true", help="Extract cover art")
    parser.add_argument("--embed", type=utils.path_type, help="Embed cover art from specified file")
    parser.add_argument("--output", type=utils.path_type, help="Output directory for extracted cover art")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=handle_cover_art, config=config)

def handle_cover_art(args):
    """Handle the 'cover-art' command."""
    path = args.path
    extract = args.extract
    embed = args.embed
    output = args.output
    config = args.config
    
    # Use config values with fallbacks
    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    
    if not extract and not embed:
        print("Please specify either --extract or --embed option.")
        return

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

    if extract:
        if not output:
            output = os.path.join(os.path.dirname(path), "cover_art")
        os.makedirs(output, exist_ok=True)
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(extract_cover, file, output) for file in audio_files]
            with tqdm(total=len(futures), desc="Extracting cover art") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        print(f"Extracted cover art from {result}")
                    pbar.update(1)
    
    if embed:
        if not os.path.isfile(embed):
            print(f"Cover art file '{embed}' not found.")
            return
            
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(embed_cover, file, embed) for file in audio_files]
            with tqdm(total=len(futures), desc="Embedding cover art") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        print(f"Embedded cover art in {result}")
                    pbar.update(1)
