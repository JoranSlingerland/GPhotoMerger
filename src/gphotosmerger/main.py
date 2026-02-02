import argparse
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    validate_args(args)

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
    print("=" * 60)
    print()

    logger.info(
        "Starting gphotosexport with settings",
        extra={
            "source": str(args.source),
            "export_dir": str(args.export_dir),
            "log_file": str(args.log_file),
            "max_workers": args.max_workers,
        },
    )

    args.export_dir.mkdir(parents=True, exist_ok=True)

    stats = process_takeout(
        args.source, args.export_dir, logger, max_workers=args.max_workers
    )

    print()
    print("=" * 60)
    print("Processing Summary")
    print("=" * 60)
    print(f"Total files found:           {stats.total_files}")
    print(f"Photos processed:            {stats.photos_processed}")
    print(f"Unsupported files:           {stats.unsupported_files}")
    print(f"Photos with metadata:        {stats.photos_with_metadata}")
    print(f"Photos failed:               {stats.photos_failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
