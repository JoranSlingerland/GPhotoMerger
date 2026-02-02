import logging
import shutil
from pathlib import Path
from typing import NamedTuple

from tqdm import tqdm

from .exif_writer import write_metadata as exif_write
from .metadata import find_json, load_metadata_from_file


class ProcessingStats(NamedTuple):
    total_files: int
    photos_processed: int
    photos_with_metadata: int
    photos_failed: int
    unsupported_files: int


SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".gif", ".bmp"}


def process_takeout(
    root_path: Path,
    export_dir: Path,
    logger: logging.Logger,
    supported_ext: set[str] = SUPPORTED_EXT,
) -> ProcessingStats:
    logger.info("Starting processing takeout root", extra={"root_path": str(root_path)})
    all_files = list(root_path.rglob("*"))
    photos: list[Path] = []
    unsupported_files = 0
    for photo_path in all_files:
        if photo_path.is_dir():
            continue
        if photo_path.suffix.lower() == ".json":
            continue
        if photo_path.suffix.lower() in supported_ext:
            photos.append(photo_path)
        else:
            unsupported_files += 1
            logger.warning(
                "Skipping unsupported file type",
                extra={
                    "file_path": str(photo_path),
                    "extension": photo_path.suffix.lower(),
                },
            )

    logger.info("Found photos to process", extra={"count": len(photos)})

    photos_with_metadata = 0
    photos_failed = 0

    for photo_path in tqdm(photos, desc="Processing photos"):
        find_result = find_json(photo_path)

        # export_dir is required; copy photo to export_dir preserving relative path
        try:
            relative_path = photo_path.relative_to(root_path)
        except Exception:
            relative_path = Path(photo_path.name)

        dest_photo = export_dir / relative_path
        dest_photo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(photo_path, dest_photo)

        target_photo_path = dest_photo

        if not find_result:
            logger.warning(
                "No metadata file found for photo",
                extra={"photo_path": str(target_photo_path)},
            )
            continue

        json_file_path, confidence, match_type = find_result

        # Log the match with confidence level
        if match_type in ("exact", "substring"):
            logger.debug(
                "Matched JSON file (exact match)",
                extra={
                    "photo_path": str(target_photo_path),
                    "json_file": json_file_path.name,
                    "match_type": match_type,
                },
            )
        else:
            logger.info(
                "Matched JSON file (fuzzy match)",
                extra={
                    "photo_path": str(target_photo_path),
                    "json_file": json_file_path.name,
                    "match_type": match_type,
                    "confidence": f"{confidence:.2%}",
                },
            )

        metadata = load_metadata_from_file(json_file_path)
        if metadata is None:
            logger.warning(
                "Failed to load metadata JSON",
                extra={"json_file_path": str(json_file_path)},
            )
            continue

        try:
            exif_write(target_photo_path, metadata)
            photos_with_metadata += 1
        except Exception:
            photos_failed += 1
            logger.exception(
                "Failed to write metadata",
                extra={
                    "photo_path": str(target_photo_path),
                    "json_file_path": str(json_file_path),
                },
            )

    logger.info(
        "Completed processing takeout root",
        extra={
            "root_path": str(root_path),
            "total_files": len(photos) + unsupported_files,
            "photos_processed": len(photos),
            "photos_with_metadata": photos_with_metadata,
            "photos_failed": photos_failed,
            "unsupported_files": unsupported_files,
        },
    )

    return ProcessingStats(
        total_files=len(photos) + unsupported_files,
        photos_processed=len(photos),
        photos_with_metadata=photos_with_metadata,
        photos_failed=photos_failed,
        unsupported_files=unsupported_files,
    )
