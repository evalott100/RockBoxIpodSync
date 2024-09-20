import argparse
from pathlib import Path
from convert_album_covers import main

parser = argparse.ArgumentParser(
    description="Convert embedded album art to not use interlacing."
)
parser.add_argument(
    "path", 
    default=".",
    type=str,
    help="Either a directory to recursively change songs in, or a song/jpg itself."
)

args = parser.parse_args()
main(Path(args.path))