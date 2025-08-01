import os
import sys
import mutagen
import subprocess
from mutagen.mp4 import MP4
from tqdm import tqdm
import concurrent.futures
import utils  # Import from root directory

def get_codec(file_path: str) -> str:
    """Determine the codec of an audio file using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        codec_name = result.stdout.strip()
        return codec_name if codec_name else "Unknown"
    except Exception as e:
        print(f"Error determining codec for {file_path}: {e}", file=sys.stderr)
        return "Unknown"

def get_album_metadata(file_path: str) -> tuple:
    """Extract album, artist, and codec metadata from an audio file."""
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            return None, None, None

        album = audio.get("album", [None])[0]
        artist = audio.get("albumartist", audio.get("artist", [None]))[0]
        codec = get_codec(file_path) if isinstance(audio, MP4) else type(audio).__name__
        return album, artist, codec
    except Exception as e:
        print(f"Error reading metadata from {file_path}: {e}", file=sys.stderr)
        return None, None, None

def count_albums(directories: list, num_workers: int) -> None:
    """Count unique albums per codec across the provided directories."""
    album_dict = {}
    all_files = []
    for directory in directories:
        all_files.extend(utils.get_audio_files(directory))

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(get_album_metadata, file) for file in all_files]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(all_files), desc="Processing albums"):
            album, artist, codec = future.result()
            if album and codec:
                album_dict.setdefault(codec, set()).add((artist, album))

    total_albums = 0
    for codec, albums in album_dict.items():
        count = len(albums)
        total_albums += count
        print(f"{codec}: {count} Albums")
    print(f"Total: {total_albums} Albums")

def count_songs(directories: list, num_workers: int) -> None:
    """Count individual songs per codec across the provided directories."""
    song_dict = {}
    all_files = []
    for directory in directories:
        all_files.extend(utils.get_audio_files(directory))

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(get_album_metadata, file) for file in all_files]
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(all_files), desc="Processing songs"):
            _, _, codec = future.result()
            if codec:
                song_dict[codec] = song_dict.get(codec, 0) + 1

    total_songs = sum(song_dict.values())
    for codec, count in song_dict.items():
        print(f"{codec}: {count} Songs")
    print(f"Total: {total_songs} Songs")

def calculate_size(directories: list, num_workers: int) -> None:
    """Calculate the total size of audio files per codec across the provided directories."""
    size_dict = {}
    all_files = []
    for directory in directories:
        all_files.extend(utils.get_audio_files(directory))

    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(get_album_metadata, file): file for file in all_files}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(all_files), desc="Processing sizes"):
            file = futures[future]
            _, _, codec = future.result()
            if codec:
                file_size = os.path.getsize(file)
                size_dict[codec] = size_dict.get(codec, 0) + file_size

    total_size = sum(size_dict.values())
    for codec, size in size_dict.items():
        size_mb = size / (1024 * 1024)
        if size_mb > 1024:
            print(f"{codec}: {size_mb / 1024:.2f} GB")
        else:
            print(f"{codec}: {size_mb:.2f} MB")
    total_size_mb = total_size / (1024 * 1024)
    if total_size_mb > 1024:
        print(f"Total: {total_size_mb / 1024:.2f} GB")
    else:
        print(f"Total: {total_size_mb:.2f} MB")

def count_command(args):
    """Handle the 'count' command to count albums, songs, or calculate sizes."""
    if not utils.is_ffprobe_installed():
        print("Error: ffprobe is not installed or not in your PATH.")
        return

    directories = args.directories
    num_workers = args.workers if args.workers is not None else (os.cpu_count() or 4)

    if args.option == "album":
        count_albums(directories, num_workers)
    elif args.option == "song":
        count_songs(directories, num_workers)
    elif args.option == "size":
        calculate_size(directories, num_workers)
    else:
        print("Invalid option. Use 'album', 'song', or 'size'.")

def register_command(subparsers, config):
    """Register the 'count' command with the subparsers."""
    parser = subparsers.add_parser("count", help="Count albums in a directory")
    parser.add_argument("path", type=utils.path_type, help="Directory to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed information")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=count_albums, config=config)

def count_albums(args):
    """Handle the 'album-counter' command."""
    path = args.path
    verbose = args.verbose
    config = args.config
    
    # Use config values with fallbacks
    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    
    if not os.path.isdir(path):
        print(f"'{path}' is not a directory.")
        return

    # Get all audio files
    audio_files = utils.get_audio_files(path)
    if not audio_files:
        print(f"No audio files found in '{path}'.")
        return

    # Process files
    albums = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(process_file, file) for file in audio_files]
        with tqdm(total=len(futures), desc="Processing files") as pbar:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    album_key = (result['artist'], result['album'])
                    if album_key not in albums:
                        albums[album_key] = {
                            'artist': result['artist'],
                            'album': result['album'],
                            'tracks': 0,
                            'files': []
                        }
                    albums[album_key]['tracks'] += 1
                    albums[album_key]['files'].append(result['file_path'])
                pbar.update(1)

    # Print results
    if verbose:
        print("\nDetailed Album Information:")
        for album in albums.values():
            print(f"\nArtist: {album['artist']}")
            print(f"Album: {album['album']}")
            print(f"Track Count: {album['tracks']}")
            print("Files:")
            for file in album['files']:
                print(f"  {file}")
    else:
        print("\nAlbum Summary:")
        for album in albums.values():
            print(f"{album['artist']} - {album['album']}: {album['tracks']} tracks")

    print(f"\nTotal Albums: {len(albums)}")
