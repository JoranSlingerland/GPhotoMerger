import argparse
import datetime
import json
import logging
from pathlib import Path

from .input_validation import validate_args
from .logconfig import configure_file_logger
from .processor import process_takeout


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process Google Takeout photos and write EXIF metadata."
    )
    parser.add_argument(
        "--source",
        "-s",
        type=Path,
        required=True,
        help="Root path of Google Takeout photos",
    )
    parser.add_argument(
        "--export-dir",
        "-o",
        type=Path,
        required=True,
        help="Directory to copy photos+metadata to before processing",
    )
    parser.add_argument(
        "--log-file",
        "-l",
        type=Path,
        default=Path(".") / "gphotosmerger.log",
        help="Path to JSON log file (default .\\gphotosmerger.log)",
    )
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Stream log output to console in addition to log file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers for processing (default: 4)",
    )
    parser.add_argument(
        "--move-files",
        action="store_true",
        help="Move files instead of copying (faster, but removes originals)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without making any changes",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already exist in export directory",
    )
    parser.add_argument(
        "--stats-file",
        type=Path,
        help="Export statistics to a JSON file",
    )
    parser.add_argument(
        "--date-from",
        type=str,
        help="Filter photos from this date (ISO format: YYYY-MM-DD or epoch timestamp)",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        help="Filter photos to this date (ISO format: YYYY-MM-DD or epoch timestamp)",
    )
    parser.add_argument(
        "--file-types",
        type=str,
        help="Filter by file extensions (comma-separated, e.g., 'jpg,png,mp4')",
    )
    return parser.parse_args()


def _parse_date_filter(date_str: str | None) -> int | None:
    """Parse date string to epoch timestamp or return None."""
    if date_str is None:
        return None

    # Try parsing as epoch timestamp
    try:
        return int(date_str)
    except ValueError:
        pass

    # Try parsing as ISO date (YYYY-MM-DD)
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # Set to start of day UTC
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        pass

    raise ValueError(
        f"Invalid date format: {date_str}. Use ISO format (YYYY-MM-DD) or epoch timestamp."
    )


def main() -> None:
    args = _parse_args()
    validate_args(args)

    # Parse date filters
    date_from = _parse_date_filter(args.date_from)
    date_to = _parse_date_filter(args.date_to)

    # Parse file type filter
    # Normalize extensions: strip whitespace, lowercase, ensure leading dot
    # Examples: "jpg", ".jpg", " JPG " all become ".jpg"
    file_types = None
    if args.file_types:
        file_types = set(
            f".{ext.strip().lower().lstrip('.')}" for ext in args.file_types.split(",")
        )

    log_level = getattr(logging, args.log_level.upper())
    logger = configure_file_logger(
        args.log_file, console_output=args.console_log, log_level=log_level
    )

    print("=" * 60)
    print("Starting gphotosexport")
    print("=" * 60)
    print(f"Source:                      {args.source}")
    print(f"Export directory:            {args.export_dir}")
    print(f"Log file:                    {args.log_file}")
    print(f"Max workers:                 {args.max_workers}")
    print(f"Move files:                  {args.move_files}")
    print(f"Dry run:                     {args.dry_run}")
    print(f"Skip existing:               {args.skip_existing}")
    if date_from:
        print(f"Date from:                   {args.date_from} ({date_from})")
    if date_to:
        print(f"Date to:                     {args.date_to} ({date_to})")
    if file_types:
        print(f"File types:                  {', '.join(sorted(file_types))}")
    print("=" * 60)
    print()

    logger.info(
        "Starting gphotosexport with settings",
        extra={
            "source": str(args.source),
            "export_dir": str(args.export_dir),
            "log_file": str(args.log_file),
            "max_workers": args.max_workers,
            "move_files": args.move_files,
            "dry_run": args.dry_run,
            "skip_existing": args.skip_existing,
            "date_from": date_from,
            "date_to": date_to,
            "file_types": list(file_types) if file_types else None,
        },
    )

    if not args.dry_run:
        args.export_dir.mkdir(parents=True, exist_ok=True)

    stats = process_takeout(
        args.source,
        args.export_dir,
        logger,
        max_workers=args.max_workers,
        move_files=args.move_files,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        date_from=date_from,
        date_to=date_to,
        file_types=file_types,
    )

    print()
    print("=" * 60)
    print("Processing Summary")
    print("=" * 60)
    print(f"Total files found:           {stats.total_files}")
    print(f"Photos processed:            {stats.photos_processed}")
    print(f"Unsupported files:           {stats.unsupported_files}")
    print(f"Photos with metadata:        {stats.photos_with_metadata}")
    print(f"Photos skipped:              {stats.photos_skipped}")
    print(f"Photos filtered:             {stats.photos_filtered}")
    print(f"Photos failed:               {stats.photos_failed}")
    print("=" * 60)

    # Export statistics if requested
    if args.stats_file:
        stats_data = {
            "total_files": stats.total_files,
            "photos_processed": stats.photos_processed,
            "unsupported_files": stats.unsupported_files,
            "photos_with_metadata": stats.photos_with_metadata,
            "photos_skipped": stats.photos_skipped,
            "photos_filtered": stats.photos_filtered,
            "photos_failed": stats.photos_failed,
            "source": str(args.source),
            "export_dir": str(args.export_dir),
            "dry_run": args.dry_run,
            "skip_existing": args.skip_existing,
        }
        with open(args.stats_file, "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2)
        print(f"\nStatistics exported to: {args.stats_file}")


if __name__ == "__main__":
    main()
