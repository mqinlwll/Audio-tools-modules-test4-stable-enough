import os
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import utils  # Import from root directory
from mutagen import File as MutagenFile
import shutil

# Base cover art filenames
BASE_COVER_NAMES = ['cover.jpg', 'cover.jpeg', 'cover.png', 'folder.jpg', 'folder.jpeg', 'folder.png']

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
    # Determine action based on args
    hide = args.hide if hasattr(args, 'hide') else False
    show = args.show if hasattr(args, 'show') else False
    
    if not (hide or show):
        print("Please specify either --hide or --show option.")
        return
        
    # Set hide flag for get_files_to_rename
    hide_files = hide and not show
    
    num_workers = args.workers if args.workers is not None else (os.cpu_count() or 4)
    files_to_rename = get_files_to_rename(path, hide_files)
    if not files_to_rename:
        print(f"No cover art files to {'hide' if hide_files else 'show'} in '{path}'.")
        return
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(rename_file, src, dst) for src, dst in files_to_rename]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing cover art"):
            try:
                future.result()
            except Exception as e:
                print(f"Error renaming file: {e}")
    print(f"Cover art {'hidden' if hide_files else 'shown'} successfully.")

def register_command(subparsers, config):
    """Register the 'cover-art' command with the subparsers."""
    parser = subparsers.add_parser("cover-art", help="Extract or embed cover art")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--extract", action="store_true", help="Extract cover art")
    action_group.add_argument("--embed", type=utils.path_type, help="Embed cover art from specified file")
    action_group.add_argument("--hide", action="store_true", help="Hide cover art files by adding dot prefix")
    action_group.add_argument("--show", action="store_true", help="Show hidden cover art files by removing dot prefix")
    
    parser.add_argument("--output", type=utils.path_type, help="Output directory for extracted cover art")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=handle_cover_art, config=config)

def handle_cover_art(args):
    """Handle the 'cover-art' command."""
    path = args.path
    extract = args.extract
    embed = args.embed
    hide = args.hide
    show = args.show
    output = args.output
    config = args.config
    
    # Use config values with fallbacks
    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    
    # Handle hide/show operations
    if hide or show:
        args.workers = num_workers
        process_cover_art(args)
        return
    
    if not extract and not embed:
        print("Please specify one of --extract, --embed, --hide, or --show options.")
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

def extract_cover(audio_file: str, output_dir: str) -> str:
    """Extract cover art from audio file to the specified output directory.
    
    Returns the audio file path if successful, None otherwise.
    """
    try:
        audio = MutagenFile(audio_file)
        if not audio:
            return None
            
        # File name for the extracted cover art
        base_name = os.path.splitext(os.path.basename(audio_file))[0]
        cover_path = os.path.join(output_dir, f"{base_name}_cover.jpg")
        
        # Extract cover art based on file format
        if hasattr(audio, 'pictures') and audio.pictures:  # FLAC, OGG, etc.
            with open(cover_path, 'wb') as f:
                f.write(audio.pictures[0].data)
            return audio_file
        elif audio.tags and 'APIC:' in audio.tags:  # MP3
            with open(cover_path, 'wb') as f:
                f.write(audio.tags['APIC:'].data)
            return audio_file
        elif audio.tags and 'covr' in audio.tags:  # M4A
            with open(cover_path, 'wb') as f:
                f.write(audio.tags['covr'][0])
            return audio_file
    except Exception as e:
        print(f"Error extracting cover art from {audio_file}: {e}")
    
    return None

def embed_cover(audio_file: str, cover_file: str) -> str:
    """Embed cover art into the audio file.
    
    Returns the audio file path if successful, None otherwise.
    """
    try:
        # Create backup
        backup_file = audio_file + ".bak"
        shutil.copy2(audio_file, backup_file)
        
        audio = MutagenFile(audio_file)
        if not audio:
            return None
            
        with open(cover_file, 'rb') as f:
            cover_data = f.read()
            
        # Determine mime type based on cover file extension
        mime_type = "image/jpeg"  # Default
        if cover_file.lower().endswith('.png'):
            mime_type = "image/png"
            
        # Embed cover art based on file format
        if hasattr(audio, 'add_picture'):  # FLAC
            from mutagen.flac import Picture
            pic = Picture()
            pic.data = cover_data
            pic.type = 3  # Cover (front)
            pic.mime = mime_type
            pic.desc = "Cover"
            audio.add_picture(pic)
            audio.save()
            return audio_file
        elif audio.tags and hasattr(audio.tags, 'add'):  # MP3
            from mutagen.id3 import APIC
            audio.tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime=mime_type,
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=cover_data
                )
            )
            audio.save()
            return audio_file
        elif hasattr(audio.tags, 'setdefault'):  # M4A
            audio.tags.setdefault('covr', [])
            audio.tags['covr'] = [cover_data]
            audio.save()
            return audio_file
            
        # Restore backup if we get here (didn't update the cover)
        shutil.move(backup_file, audio_file)
    except Exception as e:
        print(f"Error embedding cover art in {audio_file}: {e}")
        # Restore backup if an exception occurs
        if os.path.exists(backup_file):
            shutil.move(backup_file, audio_file)
    
    return None
