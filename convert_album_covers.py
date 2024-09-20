"""
Rockbox on ipod 5th gen doesn't much like interlaced jpeg for album art.
This script simply recursively changes embedded album art to get around this.
I run it on "acquired" music before I merge it into my library.

It will also format jpg within the directory but I don't store album art that way,

This should work on whatever major OS so long as you have wand and mutagen.
"""

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, PictureType, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from pathlib import Path
from datetime import datetime
from wand.image import Image
import tempfile


IGNORE_NAMES = set() # Optional
TEMPORARY_JPG_PATH = Path(tempfile.gettempdir()) / "temp.jpg"


number_of_cover_art_converted = 0
found_albums = set()

def format_jpg(file_path: Path):
    # I can't use "a" as my mode here, wand image requires "r" for the buffer annoyingly
    with file_path.open(mode="rb") as image_buffer:
        wand_image = Image(file=image_buffer)
    wand_image.interlace_scheme = "no"
    with file_path.open(mode="wb") as image_buffer:
        wand_image.save(file=image_buffer)

    global number_of_cover_art_converted
    number_of_cover_art_converted += 1

def format_mp3(file_path: Path):
    try:
        tag = ID3(file_path)
    except ID3NoHeaderError:
        return
    if len(tag.getall("APIC")) == 0:
        return
    with TEMPORARY_JPG_PATH.open(mode="wb") as image_buffer:
        image_buffer.write(tag.getall("APIC")[0].data)
    format_jpg(TEMPORARY_JPG_PATH)
    tag.delall("APIC")
    with TEMPORARY_JPG_PATH.open(mode='rb') as image_buffer:
        tag.add(APIC(3, 'image/jpeg', 3, u'cover', data=image_buffer.read()))
    tag.save()

def format_flac(file_path: Path):
    tag = FLAC(file_path)
    pictures = tag.pictures
    for picture in pictures:
        if picture.type != 3:
            continue

        with TEMPORARY_JPG_PATH.open(mode="wb") as image_buffer:
            image_buffer.write(picture.data)
        format_jpg(TEMPORARY_JPG_PATH)
        tag.clear_pictures()
        new_picture = Picture()
        new_picture.type = PictureType.COVER_FRONT
        new_picture.mime = 'image/jpeg'
        with TEMPORARY_JPG_PATH.open(mode='rb') as image_buffer:
            new_picture.data = image_buffer.read()
        tag.add_picture(new_picture)
        tag.save(deleteid3=True)

def format_m4a(file_path: Path):
    tag = MP4(file_path)
    # For some reason this is a list. I guess most mp4s can have multiple thumbnails.
    # For an m4a I'm not sure but lets err on the safe side.
    new_covr = []
    for image in tag["covr"]:
        with TEMPORARY_JPG_PATH.open(mode="wb") as image_buffer:
            image_buffer.write(image)
        format_jpg(TEMPORARY_JPG_PATH)
        with TEMPORARY_JPG_PATH.open(mode='rb') as image_buffer:
            new_covr.append(
                MP4Cover(image_buffer.read(), imageformat=MP4Cover.FORMAT_JPEG)
            )
    tag["covr"] = new_covr
    tag.save()

SUFFIX_FORMATTERS = {
    ".flac": format_flac, ".mp3": format_mp3, ".jpg": format_jpg, ".m4a": format_m4a
}

def format_art(path: Path):
    if path.is_file() and path.suffix in SUFFIX_FORMATTERS:
        if path.parent not in found_albums:
            print(f"FORMATTING IN: {path.parent}")
            found_albums.add(path.parent)

        print(f"    {str(path.name)}")
        SUFFIX_FORMATTERS[path.suffix](path)

    elif path.is_dir():
        for child in path.iterdir():
                if child.name not in IGNORE_NAMES:
                    format_art(child)

def main(root_path: Path):
    if not root_path.exists():
            raise RuntimeError(f"Could not find file/directory {root_path.absolute()}")
    start = datetime.now()
    format_art(root_path)
    print(
        f"FINISHED: {number_of_cover_art_converted} files processed in "
        f"{len(found_albums)} directories in "
        f"{(datetime.now() - start).seconds} seconds."
    )