from pathlib import Path
import ffmpeg

TO_CONVERT_FORMATS = {".flac", ".m4a"}


def convert_to_mp3(input_path: Path, output_path: Path):
    """
    Convert a FLAC/M4A file to MP3 with a bitrate of 320kbps using ffmpeg-python.

    Args:
        input_path (Path): The path to the input FLAC/M4A file.
        output_path (Path): The path to save the output MP3 file.
    """
    if input_path.suffix.lower() not in TO_CONVERT_FORMATS:
        raise ValueError("Input file must be a FLAC or M4A file")

    ffmpeg.input(str(input_path)).output(
        str(output_path), audio_bitrate="320k"
    ).global_args("-loglevel", "quiet", "-nostats").run()
