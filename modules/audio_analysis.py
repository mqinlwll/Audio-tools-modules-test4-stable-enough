import subprocess
import json
from pathlib import Path
import concurrent.futures
from tqdm import tqdm
import datetime
import utils  # Import from root directory

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
    """Handle the 'info' command to analyze audio file metadata."""
    if not utils.is_ffprobe_installed():
        print("Error: ffprobe is not installed or not in your PATH.")
        return

    path = args.path
    output = args.output
    verbose = args.verbose
    num_workers = args.workers if args.workers is not None else (os.cpu_count() or 4)

    # Determine files to analyze
    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in utils.AUDIO_EXTENSIONS:
        audio_files = [Path(path)]
    elif os.path.isdir(path):
        audio_files = [file for ext in utils.AUDIO_EXTENSIONS for file in Path(path).rglob(f"*{ext}")]
        if not audio_files:
            print(f"No audio files found in '{path}'.")
            return
    else:
        print(f"'{path}' is not a file or directory.")
        return

    if verbose:
        # Sequential analysis with console output
        for audio_file in audio_files:
            print(analyze_single_file(str(audio_file)))
    else:
        # Parallel analysis with file output
        output_file = f"audio_analysis_{datetime.datetime.now().strftime('%Y%m%d')}.txt" if output == "audio_analysis.txt" else output
        with open(output_file, "w") as f:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(analyze_single_file, str(file)) for file in audio_files]
                for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Analyzing audio"):
                    f.write(future.result())
        print(f"Analysis complete. Results saved to '{output_file}'")

def register_command(subparsers):
    """Register the 'info' command with the subparsers."""
    info_parser = subparsers.add_parser("info", help="Analyze audio file metadata")
    info_parser.add_argument("path", type=utils.path_type, help="File or directory to analyze")
    info_parser.add_argument("-o", "--output", default="audio_analysis.txt", help="Output file for results")
    info_parser.add_argument("--verbose", action="store_true", help="Print results to console (no parallelism)")
    info_parser.set_defaults(func=analyze_audio)
