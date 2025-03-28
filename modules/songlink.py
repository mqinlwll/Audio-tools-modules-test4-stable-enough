import requests
import json
from colorama import Fore, Style, init
import utils  # Assuming a utils module exists in the project root
import os
import concurrent.futures
from tqdm import tqdm

# Initialize colorama for colored output
init(autoreset=True)

def normalize_service_names(links):
    """Normalize service names to lowercase with underscores."""
    return {service.lower().replace(" ", "_"): info for service, info in links.items()}

def fetch_links(url, country=None, song_if_single=False):
    """Fetch song links from the Odesli API."""
    base_url = "https://api.song.link/v1-alpha.1/links"
    params = {'url': url}
    if country:
        params['userCountry'] = country
    if song_if_single:
        params['songIfSingle'] = 'true'

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        if 'linksByPlatform' not in data:
            return None
        return normalize_service_names(data['linksByPlatform'])
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        print(f"{Fore.RED}Error fetching links for {url}: {str(e)}")
        return None

def print_links(url, links, selected_services=None):
    """Print the fetched links to the console with formatting."""
    print(Style.BRIGHT + f"\nResults for URL: {url}")
    print(Style.BRIGHT + "Available Links:")
    print("-" * 40)

    filtered_links = links
    if selected_services:
        filtered_links = {k: v for k, v in links.items() if k in selected_services}

    for service, info in filtered_links.items():
        normalized_service = normalize_service_name(service)
        print(f"{normalized_service}: {info['url']}")

    print("-" * 40)
    return filtered_links

def normalize_service_name(service):
    """Apply color and formatting to service names."""
    service_colors = {
        "spotify": Fore.GREEN,
        "itunes": Fore.CYAN,
        "apple_music": Fore.RED,
        "youtube": Fore.YELLOW,
        "youtube_music": Fore.YELLOW + Style.BRIGHT,
        "google": Fore.BLUE,
        "google_store": Fore.BLUE,
        "pandora": Fore.MAGENTA,
        "deezer": Fore.BLUE,
        "tidal": Fore.MAGENTA,
        "amazon_store": Fore.YELLOW,
        "amazon_music": Fore.YELLOW,
        "soundcloud": Fore.CYAN,
        "napster": Fore.YELLOW,
        "yandex": Fore.LIGHTYELLOW_EX,
        "spinrilla": Fore.GREEN,
        "audius": Fore.LIGHTCYAN_EX,
        "anghami": Fore.LIGHTYELLOW_EX,
        "boomplay": Fore.GREEN,
        "audiomack": Fore.GREEN,
    }
    color = service_colors.get(service, Fore.WHITE)
    return color + service.replace("_", " ").title() + Style.RESET_ALL

def register_command(subparsers, config):
    """Register the 'songlink' command with the subparsers."""
    parser = subparsers.add_parser("songlink", help="Generate song links")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    parser.add_argument("--output", type=utils.path_type, help="Output directory for song links")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=handle_songlink, config=config)

def handle_songlink(args):
    """Handle the 'songlink' command."""
    path = args.path
    output = args.output
    config = args.config
    
    # Use config values with fallbacks
    num_workers = args.workers if args.workers is not None else config['processing']['max_workers']
    
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

    if not output:
        output = os.path.join(os.path.dirname(path), "song_links")
    os.makedirs(output, exist_ok=True)
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(create_songlink, file, output) for file in audio_files]
        with tqdm(total=len(futures), desc="Creating song links") as pbar:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    print(f"Created song link for {result}")
                pbar.update(1)
