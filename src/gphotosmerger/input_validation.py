"""Argument validation for gphotosexport."""
import argparse
import sys
from pathlib import Path


def validate_args(args: argparse.Namespace) -> None:
    """Validate parsed arguments."""
    # Validate source path
    if not args.source.exists():
        print(f"Error: Source path does not exist: {args.source}", file=sys.stderr)
        sys.exit(1)
    if not args.source.is_dir():
        print(f"Error: Source path is not a directory: {args.source}", file=sys.stderr)
        sys.exit(1)

    # Validate export dir parent exists or can be created
    export_parent = args.export_dir.parent
    if not export_parent.exists():
        try:
            export_parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(
                f"Error: Cannot create export directory parent: {export_parent}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate log file directory
    log_parent = args.log_file.parent
    if not log_parent.exists():
        try:
            log_parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(
                f"Error: Cannot create log file directory: {log_parent}: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Validate metadata suffix
    if not args.metadata_suffix or not args.metadata_suffix.startswith("."):
        print(
            f"Error: Metadata suffix must start with a dot: {args.metadata_suffix}",
            file=sys.stderr,
        )
        sys.exit(1)
