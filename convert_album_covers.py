"""
Rockbox on ipod 5th gen doesn't much like interlaced jpeg for album art.
This script simply recursively changes embedded album art to get around this.
I run it on "acquired" music before I merge it into my library.
It will also format jpg/png within the directory but I don't store album art that way,
png will be converted to jpg.
"""

import logging
import os
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, PictureType, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from pathlib import Path
from datetime import datetime
from wand.image import Image
from itertools import count


IGNORE_DIRECTORY_NAMES = set() # Optional

found_albums = set()
converted_images_count = count()

def format_image_to_jpg_no_interlacing(
    image_path: Path | None = None,
    image_bytes: bytes | None = None,
    delete_old_png = True
) -> bytes:
    """
    Either takes a `image_path` of an image to remove interlacing of or `image_bytes`
    of the image. Returns the formatted image bytes. If the path is given then it will
    be written to file. The converted png is deleted.
    """

    if (image_path is None and image_bytes is None) or (image_path and image_bytes):
        raise RuntimeError("Pass a `image_path` or `image_bytes` not both")
    
    if image_path and image_path.suffix not in (".jpg", ".png"):
        raise RuntimeError(f"Unexpected image file format `{image_path.suffix}`")
    
    wand_image = Image(filename=image_path) if image_path else Image(blob=image_bytes)
    wand_image.interlace_scheme = "no"
    wand_image.format = "jpg"
    
    next(converted_images_count)

    if image_path:
        jpg_image_path = image_path.parent / (f"{image_path.stem}.jpg")
        wand_image.save(filename=jpg_image_path)
        if delete_old_png and image_path != jpg_image_path:
            os.remove(image_path)
    
    return wand_image.make_blob()
    

def format_mp3(image_path: Path):
    try:
        tag = ID3(image_path)
    except ID3NoHeaderError:
        return
    if len(tag.getall("APIC")) == 0:
        return
    new_image_bytes = format_image_to_jpg_no_interlacing(
        image_bytes=tag.getall("APIC")[0].data
    )
    tag.delall("APIC")
    tag.add(APIC(3, 'image/jpeg', 3, u'cover', data=new_image_bytes))
    tag.save()

def format_flac(image_path: Path):
    tag = FLAC(image_path)
    pictures = tag.pictures
    for picture in pictures:
        if picture.type != 3:
            continue

        new_image_bytes = format_image_to_jpg_no_interlacing(
            image_bytes=picture.data
        )
        tag.clear_pictures()
        new_picture = Picture()
        new_picture.type = PictureType.COVER_FRONT
        new_picture.mime = 'image/jpeg'
        new_picture.data = new_image_bytes
        tag.add_picture(new_picture)
        tag.save(deleteid3=True)

def format_m4a(image_path: Path):
    tag = MP4(image_path)
    # For some reason this is a list. I guess most mp4s can have multiple thumbnails.
    # For an m4a I'm not sure but lets err on the safe side.
    new_covr = []
    for image_bytes in tag["covr"]:
        new_image_bytes = format_image_to_jpg_no_interlacing(
            image_bytes=image_bytes
        )
        new_covr.append(
            MP4Cover(new_image_bytes, imageformat=MP4Cover.FORMAT_JPEG)
        )
    tag["covr"] = new_covr
    tag.save()

SUFFIX_FORMATTERS = {
    ".jpg": lambda path: format_image_to_jpg_no_interlacing(image_path=path),
    ".png": lambda path: format_image_to_jpg_no_interlacing(image_path=path),
    ".flac": format_flac,
    ".mp3": format_mp3,
    ".m4a": format_m4a
}

def format_art(path: Path):
    if path.is_file() and path.suffix in SUFFIX_FORMATTERS:
        if path.parent not in found_albums:
            logging.debug(f"FORMATTING IN: {path.parent.absolute()}")
            found_albums.add(path.parent)

        logging.debug(f"    {str(path.name)}")
        SUFFIX_FORMATTERS[path.suffix](path)

    elif path.is_dir():
        for child in path.iterdir():
                if child.name not in IGNORE_DIRECTORY_NAMES:
                    format_art(child)

def main(root_path: Path):
    if not root_path.exists():
        raise RuntimeError(f"Could not find file/directory {root_path.absolute()}")
    start = datetime.now()
    format_art(root_path)

    number_of_images_converted = next(converted_images_count)
    if number_of_images_converted > 0:
        finished_text = (
            f"{number_of_images_converted} files processed in "
            f"{len(found_albums)} directories in "
            f"{(datetime.now() - start).seconds} seconds."
        )
    else:
        finished_text = "Didn't find any images to convert."
    logging.debug(f"FINISHED: {finished_text}")