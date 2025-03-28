import subprocess
import json
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import datetime
import utils  # Import from root directory
import os

def analyze_single_file(file_path: str) -> str:
    """Analyze metadata of a single audio file using ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]
        result = subprocess.check_output(cmd, universal_newlines=True)
        data = json.loads(result)
        stream = data["streams"][0]

        codec = stream.get("codec_name", "N/A")
        sample_rate = stream.get("sample_rate", "N/A")
        channels = stream.get("channels", "N/A")
        bit_depth = stream.get("bits_per_raw_sample", "N/A")
        bit_rate = data["format"].get("bit_rate", "N/A")

        channel_info = "Mono" if channels == 1 else "Stereo" if channels == 2 else f"{channels} channels" if channels != "N/A" else "N/A"
        analysis_text = f"Analyzing: {file_path}\n"
        analysis_text += f"  Bitrate: {bit_rate} bps\n" if bit_rate != "N/A" else "  Bitrate: N/A\n"
        analysis_text += f"  Sample Rate: {sample_rate} Hz\n" if sample_rate != "N/A" else "  Sample Rate: N/A\n"
        analysis_text += f"  Bit Depth: {bit_depth} bits\n" if bit_depth != "N/A" else "  Bit Depth: N/A\n"
        analysis_text += f"  Channels: {channel_info}\n"
        analysis_text += f"  Codec: {codec}\n"

        if Path(file_path).suffix.lower() == ".m4a":
            if "aac" in codec.lower():
                analysis_text += "  [INFO] AAC (lossy) codec detected.\n"
            elif "alac" in codec.lower():
                analysis_text += "  [INFO] ALAC (lossless) codec detected.\n"
            else:
                analysis_text += f"  [WARNING] Unknown codec: {codec}\n"
        elif Path(file_path).suffix.lower() in [".opus", ".mp3"]:
            analysis_text += f"  [INFO] Lossy codec: {codec}\n"
        if bit_depth != "N/A" and int(bit_depth) < 16:
            analysis_text += "  [WARNING] Low bit depth may indicate lossy encoding.\n"
        if sample_rate != "N/A" and int(sample_rate) < 44100:
            analysis_text += "  [WARNING] Low sample rate may indicate lossy encoding.\n"
        analysis_text += "\n"
        return analysis_text
    except Exception as e:
        return f"Analyzing: {file_path}\n  [ERROR] Failed to analyze: {e}\n\n"

def analyze_audio(args):
    """Handle the 'audio-analysis' command."""
    path = args.path
    verbose = args.verbose
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

    # Process files
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(analyze_file, file) for file in audio_files]
        with tqdm(total=len(futures), desc="Analyzing files") as pbar:
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                pbar.update(1)

    # Print results
    if verbose:
        print("\nDetailed Audio Analysis:")
        for result in results:
            print(f"\nFile: {result['file_path']}")
            print(f"Format: {result['format']}")
            print(f"Sample Rate: {result['sample_rate']} Hz")
            print(f"Bit Depth: {result['bit_depth']} bits")
            print(f"Channels: {result['channels']}")
            print(f"Duration: {result['duration']:.2f} seconds")
            print(f"Bitrate: {result['bitrate']/1000:.2f} kbps")
    else:
        print("\nAudio Analysis Summary:")
        print(f"Total Files: {len(results)}")
        formats = {}
        sample_rates = {}
        bit_depths = {}
        channels = {}
        
        for result in results:
            formats[result['format']] = formats.get(result['format'], 0) + 1
            sample_rates[result['sample_rate']] = sample_rates.get(result['sample_rate'], 0) + 1
            bit_depths[result['bit_depth']] = bit_depths.get(result['bit_depth'], 0) + 1
            channels[result['channels']] = channels.get(result['channels'], 0) + 1
        
        print("\nFormats:")
        for fmt, count in formats.items():
            print(f"  {fmt}: {count}")
        print("\nSample Rates:")
        for rate, count in sample_rates.items():
            print(f"  {rate} Hz: {count}")
        print("\nBit Depths:")
        for depth, count in bit_depths.items():
            print(f"  {depth} bits: {count}")
        print("\nChannels:")
        for ch, count in channels.items():
            print(f"  {ch}: {count}")

def register_command(subparsers, config):
    """Register the 'analyze' command with the subparsers."""
    parser = subparsers.add_parser("analyze", help="Analyze audio files")
    parser.add_argument("path", type=utils.path_type, help="File or directory to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed information")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    parser.set_defaults(func=analyze_audio, config=config)
