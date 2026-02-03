import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple

from tqdm import tqdm

from .exif_writer import write_metadata
from .metadata import find_json, load_metadata_from_file


class ProcessingStats(NamedTuple):
    total_files: int
    photos_processed: int
    photos_with_metadata: int
    photos_failed: int
    unsupported_files: int
    photos_skipped: int
    photos_filtered: int


SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".gif", ".bmp"}


def _process_photo(
    photo_path: Path,
    root_path: Path,
    export_dir: Path,
    logger: logging.Logger,
    move_files: bool,
    dry_run: bool = False,
    skip_existing: bool = False,
    date_from: int | None = None,
    date_to: int | None = None,
) -> tuple[bool, bool, str]:
    """Process a single photo. Returns (success, has_metadata, error_msg)."""
    find_result = find_json(photo_path)

    # export_dir is required; copy photo to export_dir preserving relative path
    try:
        relative_path = photo_path.relative_to(root_path)
    except Exception:
        relative_path = Path(photo_path.name)

    dest_photo = export_dir / relative_path

    # Check if file already exists and skip if requested
    if skip_existing and dest_photo.exists() and not dry_run:
        logger.debug(
            "Skipping existing file",
            extra={"photo_path": str(photo_path), "dest_photo": str(dest_photo)},
        )
        return (True, False, "skipped")

    if dry_run:
        logger.info(
            "DRY RUN: Would copy/move photo",
            extra={
                "photo_path": str(photo_path),
                "dest_photo": str(dest_photo),
                "move_files": move_files,
            },
        )
    else:
        dest_photo.parent.mkdir(parents=True, exist_ok=True)
        if move_files:
            shutil.move(str(photo_path), str(dest_photo))
        else:
            shutil.copy2(photo_path, dest_photo)

    target_photo_path = dest_photo

    if not find_result:
        logger.warning(
            "No metadata file found for photo",
            extra={"photo_path": str(target_photo_path)},
        )
        return (True, False, "")

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
        return (True, False, "")

    # Filter by date if specified
    if date_from is not None or date_to is not None:
        time_section = metadata.get("photoTakenTime")
        if isinstance(time_section, dict):
            ts = time_section.get("timestamp")
            if ts:
                try:
                    photo_timestamp = int(ts)
                    if date_from is not None and photo_timestamp < date_from:
                        logger.debug(
                            "Photo filtered (before date_from)",
                            extra={
                                "photo_path": str(target_photo_path),
                                "photo_timestamp": photo_timestamp,
                                "date_from": date_from,
                            },
                        )
                        return (True, False, "filtered")
                    if date_to is not None and photo_timestamp > date_to:
                        logger.debug(
                            "Photo filtered (after date_to)",
                            extra={
                                "photo_path": str(target_photo_path),
                                "photo_timestamp": photo_timestamp,
                                "date_to": date_to,
                            },
                        )
                        return (True, False, "filtered")
                except (ValueError, TypeError):
                    pass  # If timestamp is invalid, don't filter

    if dry_run:
        logger.info(
            "DRY RUN: Would write metadata",
            extra={
                "photo_path": str(target_photo_path),
                "json_file_path": str(json_file_path),
            },
        )
        return (True, True, "")

    try:
        final_photo_path = write_metadata(target_photo_path, metadata)
        if final_photo_path != target_photo_path:
            logger.info(
                "Photo path changed after processing",
                extra={
                    "photo_path": str(target_photo_path),
                    "final_photo_path": str(final_photo_path),
                },
            )
        return (True, True, "")
    except Exception as e:
        logger.exception(
            "Failed to write metadata",
            extra={
                "photo_path": str(target_photo_path),
                "json_file_path": str(json_file_path),
            },
        )
        return (False, False, str(e))


def process_takeout(
    root_path: Path,
    export_dir: Path,
    logger: logging.Logger,
    supported_ext: set[str] = SUPPORTED_EXT,
    max_workers: int = 4,
    move_files: bool = False,
    dry_run: bool = False,
    skip_existing: bool = False,
    date_from: int | None = None,
    date_to: int | None = None,
) -> ProcessingStats:
    logger.info(
        "Starting processing takeout root",
        extra={
            "root_path": str(root_path),
            "max_workers": max_workers,
            "move_files": move_files,
            "dry_run": dry_run,
            "skip_existing": skip_existing,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
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
    photos_skipped = 0
    photos_filtered = 0

    # Process photos in parallel using thread pool
    if photos:
        # Limit to available photos if fewer than max_workers
        actual_workers = min(max_workers, len(photos))
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = {
                executor.submit(
                    _process_photo,
                    photo_path,
                    root_path,
                    export_dir,
                    logger,
                    move_files,
                    dry_run,
                    skip_existing,
                    date_from,
                    date_to,
                ): photo_path
                for photo_path in photos
            }

            for future in tqdm(
                as_completed(futures),
                total=len(photos),
                desc="Processing photos",
            ):
                success, has_metadata, error_msg = future.result()
                if error_msg == "skipped":
                    photos_skipped += 1
                elif error_msg == "filtered":
                    photos_filtered += 1
                elif success:
                    if has_metadata:
                        photos_with_metadata += 1
                else:
                    photos_failed += 1

    logger.info(
        "Completed processing takeout root",
        extra={
            "root_path": str(root_path),
            "total_files": len(photos) + unsupported_files,
            "photos_processed": len(photos),
            "photos_with_metadata": photos_with_metadata,
            "photos_failed": photos_failed,
            "unsupported_files": unsupported_files,
            "photos_skipped": photos_skipped,
            "photos_filtered": photos_filtered,
        },
    )

    return ProcessingStats(
        total_files=len(photos) + unsupported_files,
        photos_processed=len(photos),
        photos_with_metadata=photos_with_metadata,
        photos_failed=photos_failed,
        unsupported_files=unsupported_files,
        photos_skipped=photos_skipped,
        photos_filtered=photos_filtered,
    )
