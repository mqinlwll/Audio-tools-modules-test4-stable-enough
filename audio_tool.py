import argparse
import importlib
from pathlib import Path

def print_logo():
    """Print ASCII logo for AUDIO TOOL"""
    logo = """
    █████╗ ██╗   ██╗██████╗ ██╗ ██████╗     ████████╗ ██████╗  ██████╗ ██╗
    ██╔══██╗██║   ██║██╔══██╗██║██╔═══██╗    ╚══██╔══╝██╔═══██╗██╔═══██╗██║
    ███████║██║   ██║██║  ██║██║██║   ██║       ██║   ██║   ██║██║   ██║██║
    ██╔══██║██║   ██║██║  ██║██║██║   ██║       ██║   ██║   ██║██║   ██║██║
    ██║  ██║╚██████╔╝██████╔╝██║╚██████╔╝       ██║   ╚██████╔╝╚██████╔╝███████╗
    ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝ ╚═════╝        ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝
    """
    print(logo)

def main():
    """Set up CLI and dynamically register commands from modules."""
    parser = argparse.ArgumentParser(
        description="Tool for managing audio files",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Dynamically import and register modules from the 'modules' directory
    modules_dir = Path(__file__).parent / 'modules'
    for py_file in modules_dir.glob('*.py'):
        if py_file.name != '__init__.py':
            module_name = f"modules.{py_file.stem}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, 'register_command'):
                    module.register_command(subparsers)
                else:
                    print(f"Warning: Module {module_name} does not have a 'register_command' function.")
            except ImportError as e:
                print(f"Error importing module {module_name}: {e}")

    # Check if no arguments were provided
    if len(sys.argv) == 1:
        print_logo()
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # If command is provided but no func is set (shouldn't happen with required=True)
    if not hasattr(args, 'func'):
        print_logo()
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == "__main__":
    try:
        import sys  # Added missing import
        main()
    except KeyboardInterrupt:
        print("Quitting job...")
