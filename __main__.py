import argparse
import logging
from pathlib import Path
from convert_album_covers import main

logging.basicConfig(format="%(message)s", level=logging.DEBUG)

parser = argparse.ArgumentParser(
    description="Convert embedded album art to not use interlacing."
)
parser.add_argument(
    "path", 
    default=".",
    type=str,
    help="Either a directory to recursively change songs in, or a song/image itself."
)

args = parser.parse_args()
main(Path(args.path))