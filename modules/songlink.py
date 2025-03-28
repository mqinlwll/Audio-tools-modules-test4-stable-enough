import requests
import json
from colorama import Fore, Style, init
import utils  # Assuming a utils module exists in the project root

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

def songlink_command(args):
    """Handle the 'songlink' command to fetch and display song links."""
    selected_services = {s.strip().lower().replace(' ', '_') for s in args.select} if args.select else None
    output_file = open(args.output, 'w') if args.output else None

    try:
        urls = []
        if args.file:
            with open(args.file, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
        else:
            urls = [args.url]

        for url in urls:
            links = fetch_links(url, args.country, args.songIfSingle)
            if not links:
                print(f"{Fore.YELLOW}No links found for {url}")
                continue

            filtered_links = print_links(url, links, selected_services)

            if output_file and filtered_links:
                for info in filtered_links.values():
                    output_file.write(f"{info['url']}\n")

    finally:
        if output_file:
            output_file.close()

def register_command(subparsers):
    """Register the 'songlink' command with the CLI subparsers."""
    songlink_parser = subparsers.add_parser("songlink", help="Fetch song links from Odesli API")
    group = songlink_parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--url', type=str, help="Single song URL")
    group.add_argument('--file', type=str, help="Text file containing URLs")

    songlink_parser.add_argument('--country', type=str, help="User country code")
    songlink_parser.add_argument('--songIfSingle', action='store_true', help="Treat singles as songs")
    songlink_parser.add_argument('--select', '-s', nargs='+', help="Services to save (e.g., tidal)")
    songlink_parser.add_argument('--output', '-o', type=str, help="Output file to save links")
    songlink_parser.set_defaults(func=songlink_command)
