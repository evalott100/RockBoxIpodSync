"""
I wrote this because Strawberry keeps crashing on transfer.

Requires the same naming convention for the collection in both devices
(doesn't look at metadata).

Very messy rn, TODO cleanup.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
from dataclasses import dataclass
import os
from uuid import uuid4
from rockbox_ipod_sync.convert_album_covers import format_art
from rockbox_ipod_sync.transcoder import convert_to_mp3, TO_CONVERT_FORMATS
from tqdm import tqdm
import tempfile

TMP = Path(tempfile.gettempdir())
SONG_FORMATS = {".flac", ".mp3", ".m4a"}
created_directory_cache = set()


@dataclass
class FileToSync:
    file_from: Path
    path_to: Path
    size: float  # In MB
    tmp_file_from: Path | None = None


@dataclass
class DirectoryToSync:
    relative_directory: Path
    to_directory: Path
    size: float
    files_to_sync: list[FileToSync]


class SyncInfo:
    def __init__(
        self, from_root: Path, to_root: Path, transcode_to_mp3: bool, convert_art: bool
    ):
        self.from_root: Path = from_root
        self.to_root: Path = to_root
        self.transcode_to_mp3: bool = transcode_to_mp3
        self.convert_art: bool = convert_art
        self.directories_to_sync: dict[Path:DirectoryToSync] = {}
        self.files_to_copy: int = 0
        self.files_copied: int = 0
        self.total_size: float = 0.0
        self.size_copied: float = 0.0

    def add_file_to_sync(self, from_file: Path, to_directory: Path):
        file_to_sync = FileToSync(
            file_from=from_file,
            path_to=to_directory,
            size=os.path.getsize(from_file),
        )
        if to_directory not in self.directories_to_sync:
            self.directories_to_sync[to_directory] = DirectoryToSync(
                relative_directory=from_file.parent.relative_to(self.from_root),
                to_directory=to_directory,
                size=file_to_sync.size,
                files_to_sync=[],
            )

        self.directories_to_sync[to_directory].files_to_sync.append(file_to_sync)
        self.directories_to_sync[to_directory].size += file_to_sync.size

        self.total_size += file_to_sync.size
        self.files_to_copy += 1

    def calculate_sync(self, from_directory: Path, to_directory: Path):
        for sub_from in from_directory.iterdir():
            if sub_from.is_dir():
                self.calculate_sync(sub_from, to_directory / sub_from.name)
            elif (
                sub_from.suffix in SONG_FORMATS
                and not any(
                    (to_directory / sub_from.name).with_suffix(suffix).exists()
                    for suffix in SONG_FORMATS
                )
            ):
                self.add_file_to_sync(sub_from, to_directory)

    def print_sync_info(self):
        if not self.directories_to_sync:
            print("Nothing to sync.")
        for directory in self.directories_to_sync.values():
            is_new_string = (
                "(NEW SONG in EXISTING)"
                if directory.to_directory.exists()
                else "(NEW DIRECTORY)"
            )
            print(
                f"DIR: {directory.relative_directory} "
                f"SIZE: {round(directory.size // 1024**2, 2)}MB "
                f"{is_new_string}"
            )

            for file in directory.files_to_sync:
                print(
                    f"    FILE: {file.file_from.name} SIZE: {round(file.size // 1024**2, 2)}MB"
                )
        print(
            f"{int(self.total_size // 1024**2)}MB across {self.files_to_copy} songs in {len(self.directories_to_sync)} directories to sync, "
            ""
        )

    def sync(self):
        if self.files_to_copy == 0:
            return

        def convert_worker(file_to_sync: FileToSync):
            assert self.convert_art or self.transcode_to_mp3
            tmp_file_from: Path = TMP / f"{uuid4()}{file_to_sync.file_from.suffix}"
            if (
                self.transcode_to_mp3
                and file_to_sync.file_from.suffix in TO_CONVERT_FORMATS
            ):
                tmp_file_from = tmp_file_from.with_suffix(".mp3")
                convert_to_mp3(file_to_sync.file_from, tmp_file_from)
            elif self.convert_art:
                shutil.copy(file_to_sync.file_from, tmp_file_from)

            if self.convert_art:
                format_art(tmp_file_from)

            file_to_sync.tmp_file_from = tmp_file_from
            file_to_sync.path_to /= (
                f"{file_to_sync.file_from.stem}{tmp_file_from.suffix}"
            )

        def copy_worker(file_from: FileToSync):
            shutil.copy(
                file_from.tmp_file_from or file_from.file_from, file_from.path_to
            )

            if file_from.tmp_file_from:
                os.remove(file_from.tmp_file_from)
            return file_from.size

        pbar = tqdm(
            total=self.total_size,
            unit="B",
            unit_scale=True,
            bar_format="{l_bar}{bar}| {n_fmt}B/{total_fmt}B [{elapsed}]",
            dynamic_ncols=True,
        )

        for to_directory, directory_info in self.directories_to_sync.items():
            if not to_directory.exists():
                to_directory.mkdir(parents=True)

            with ThreadPoolExecutor() as executor:
                if self.convert_art or self.transcode_to_mp3:
                    pbar.set_description_str(
                        f"Transcoding/Art  : {directory_info.relative_directory} "
                    )
                    futures = [
                        executor.submit(convert_worker, file_to_sync)
                        for file_to_sync in directory_info.files_to_sync
                    ]
                    for future in as_completed(futures):
                        future.result() # Ensure all files are converted before copying
                        pbar.update()

                pbar.set_description_str(
                    f"Currently Syncing: {directory_info.relative_directory} "
                )
                futures = [
                    executor.submit(copy_worker, file_to_sync)
                    for file_to_sync in directory_info.files_to_sync
                ]
                for future in as_completed(futures):
                    size = future.result()
                    self.files_copied += 1
                    pbar.update(size)
        pbar.close()


class SyncMusic:
    def __init__(
        self,
        root_from_directory: Path,
        root_to_directory: Path,
        transcode: bool,
        convert_art: bool,
    ):
        if not root_from_directory.exists() or not root_from_directory.is_dir():
            raise RuntimeError(
                f"Can't sync from {root_from_directory}, not a directory."
            )
        if not root_to_directory.exists() or not root_to_directory.is_dir():
            raise RuntimeError(f"Can't sync to {root_to_directory}, not a directory.")

        self.sync_info = SyncInfo(
            root_from_directory, root_to_directory, transcode, convert_art
        )
        self.root_from_directory = root_from_directory
        self.root_to_directory = root_to_directory

    def sync(self):
        self.sync_info.calculate_sync(self.root_from_directory, self.root_to_directory)
        self.sync_info.print_sync_info()

        if self.sync_info.files_to_copy == 0:
            exit()

        # Add confirmation prompt
        confirmation = (
            input("Do you want to proceed with the sync? [Y (Default) / N]: ")
            .strip()
            .lower()
        )
        if confirmation in ("y", "yes", ""):
            self.sync_info.sync()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync songs with device.")
    parser.add_argument("directory_from", type=str, help="Directory to sync from.")
    parser.add_argument("directory_to", type=str, help="Directory to sync to.")
    parser.add_argument(
        "--transcode",
        action="store_true",
        help="Transcode flac/m4a to 320kbs mp3.",
    )
    parser.add_argument(
        "--convert-art",
        action="store_true",
        help="Remove transcoding from embedded album art.",
    )

    args = parser.parse_args()
    syncer = SyncMusic(
        Path(args.directory_from),
        Path(args.directory_to),
        args.transcode,
        args.convert_art,
    )
    syncer.sync()
