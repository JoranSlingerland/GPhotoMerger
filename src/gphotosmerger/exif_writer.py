"""Write metadata to files using EXIF tools and manage file mtime."""

import datetime
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, cast

import piexif  # type: ignore[import-untyped]
from mutagen.mp4 import MP4  # type: ignore[import-untyped]
from piexif import helper as piexif_helper  # type: ignore[import-untyped]

from .metadata import Metadata

logger = logging.getLogger("gphotosmerger")


def ensure_exiftool() -> str:
    exe = shutil.which("exiftool")
    if exe is None:
        raise FileNotFoundError(
            "exiftool not found in PATH; please install exiftool and ensure it's on PATH"
        )
    return exe


def format_timestamp_for_exif(timestamp_str: str) -> Optional[tuple[str, int]]:
    """Convert epoch-seconds string to exif datetime string and epoch int.

    Returns (exif_formatted_str, epoch_seconds) or None on failure.
    """
    try:
        epoch_seconds = int(timestamp_str)
        dt = datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc)
        exif_dt = dt.strftime("%Y:%m:%d %H:%M:%S")
        return exif_dt, epoch_seconds
    except (ValueError, OSError, OverflowError):
        return None


def _empty_exif_dict() -> dict[str, Any]:
    return {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}


def _deg_to_rational(
    deg: float,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    abs_deg = abs(deg)
    degrees = int(abs_deg)
    minutes_float = (abs_deg - degrees) * 60.0
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60.0
    return ((degrees, 1), (minutes, 1), (int(seconds * 10000), 10000))


def _convert_to_png(photo_path: Path, format_name: str) -> Path:
    """Convert image to PNG and return new path. Deletes original."""
    logger.info(
        f"Converting {format_name} to PNG for metadata support",
        extra={"photo_path": str(photo_path)},
    )
    from PIL import Image

    png_path = photo_path.with_suffix(".png")
    img = Image.open(photo_path)
    img.load()  # Load image data into memory
    img.save(png_path, "PNG")
    img.close()  # Explicitly close to release file handle

    # Remove original
    photo_path.unlink()
    return png_path


def _write_metadata_piexif(
    photo_path: Path, metadata: Metadata, preserve_mtime: bool
) -> None:
    original_times = None
    if preserve_mtime:
        st = photo_path.stat()
        original_times = (st.st_atime, st.st_mtime)

    try:
        exif_dict = cast(dict[str, Any], piexif.load(str(photo_path)))  # type: ignore[reportUnknownMemberType]
    except Exception:
        exif_dict = _empty_exif_dict()

    # date/time
    epoch_seconds: Optional[int] = None
    has_time = False
    time_section = metadata.get("photoTakenTime")
    if isinstance(time_section, dict):
        ts = time_section.get("timestamp")
        if ts:
            res = format_timestamp_for_exif(ts)
            if res:
                exif_dt, epoch_seconds = res
                exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_dt
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_dt
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_dt
                has_time = True

    # GPS
    geo_section = metadata.get("geoData")
    has_gps = False
    if isinstance(geo_section, dict):
        lat = geo_section.get("latitude")
        lon = geo_section.get("longitude")
        if lat is not None and lon is not None:
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = "N" if lat >= 0 else "S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = _deg_to_rational(float(lat))
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = "E" if lon >= 0 else "W"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = _deg_to_rational(float(lon))
            has_gps = True

    # description
    desc = metadata.get("description")
    has_desc = False
    if desc:
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = desc
        if piexif_helper is not None:
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = (
                piexif_helper.UserComment.dump(desc, encoding="unicode")
            )
        has_desc = True

    logger.debug(
        "Writing metadata (piexif)",
        extra={
            "photo_path": str(photo_path),
            "has_time": has_time,
            "has_gps": has_gps,
            "has_description": has_desc,
            "preserve_mtime": preserve_mtime,
        },
    )

    try:
        exif_bytes = cast(bytes, piexif.dump(exif_dict))  # type: ignore[reportUnknownMemberType]
        piexif.insert(exif_bytes, str(photo_path))
    except (ValueError, TypeError) as e:
        # piexif can fail with invalid EXIF data types
        # Fall back to exiftool in this case
        logger.debug(
            "piexif failed, falling back to exiftool",
            extra={"photo_path": str(photo_path), "error": str(e)},
        )
        _write_metadata_exiftool(photo_path, metadata, preserve_mtime)
        return

    if preserve_mtime and original_times is not None:
        os.utime(photo_path, original_times)
    elif epoch_seconds is not None:
        os.utime(photo_path, (float(epoch_seconds), float(epoch_seconds)))

    logger.debug(
        "Metadata written (piexif)",
        extra={"photo_path": str(photo_path)},
    )


def _write_metadata_png(
    photo_path: Path, metadata: Metadata, preserve_mtime: bool
) -> None:
    """Write metadata to PNG using PIL (faster than exiftool)."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    original_times = None
    if preserve_mtime:
        st = photo_path.stat()
        original_times = (st.st_atime, st.st_mtime)

    # Build EXIF data using piexif
    exif_dict = _empty_exif_dict()

    # date/time
    epoch_seconds: Optional[int] = None
    has_time = False
    time_section = metadata.get("photoTakenTime")
    if isinstance(time_section, dict):
        ts = time_section.get("timestamp")
        if ts:
            res = format_timestamp_for_exif(ts)
            if res:
                exif_dt, epoch_seconds = res
                exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_dt
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_dt
                exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_dt
                has_time = True

    # GPS
    geo_section = metadata.get("geoData")
    has_gps = False
    if isinstance(geo_section, dict):
        lat = geo_section.get("latitude")
        lon = geo_section.get("longitude")
        if lat is not None and lon is not None:
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = "N" if lat >= 0 else "S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = _deg_to_rational(float(lat))
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = "E" if lon >= 0 else "W"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = _deg_to_rational(float(lon))
            has_gps = True

    # description
    desc = metadata.get("description")
    has_desc = False
    if desc:
        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = desc
        has_desc = True

    logger.debug(
        "Writing metadata (PIL/PNG)",
        extra={
            "photo_path": str(photo_path),
            "has_time": has_time,
            "has_gps": has_gps,
            "has_description": has_desc,
            "preserve_mtime": preserve_mtime,
        },
    )

    try:
        exif_bytes = cast(bytes, piexif.dump(exif_dict))  # type: ignore[reportUnknownMemberType]

        # Open PNG and add EXIF
        img = Image.open(photo_path)
        img.load()

        # Save with EXIF
        pnginfo = PngInfo()
        img.save(photo_path, "PNG", exif=exif_bytes, pnginfo=pnginfo)
        img.close()

    except Exception as e:
        # If PIL fails, fall back to exiftool
        logger.debug(
            "PIL PNG write failed, falling back to exiftool",
            extra={"photo_path": str(photo_path), "error": str(e)},
        )
        _write_metadata_exiftool(photo_path, metadata, preserve_mtime)
        return

    if preserve_mtime and original_times is not None:
        os.utime(photo_path, original_times)
    elif epoch_seconds is not None:
        os.utime(photo_path, (float(epoch_seconds), float(epoch_seconds)))

    logger.debug(
        "Metadata written (PIL/PNG)",
        extra={"photo_path": str(photo_path)},
    )


def _write_metadata_exiftool(
    photo_path: Path, metadata: Metadata, preserve_mtime: bool
) -> None:
    exiftool_exe = ensure_exiftool()
    command_args = [exiftool_exe, "-m", "-overwrite_original"]

    # date/time
    epoch_seconds: Optional[int] = None
    has_time = False
    time_section = metadata.get("photoTakenTime")
    if isinstance(time_section, dict):
        ts = time_section.get("timestamp")
        if ts:
            res = format_timestamp_for_exif(ts)
            if res:
                exif_dt, epoch_seconds = res
                command_args.append(f"-DateTimeOriginal={exif_dt}")
                has_time = True

    # GPS
    geo_section = metadata.get("geoData")
    has_gps = False
    if isinstance(geo_section, dict):
        lat = geo_section.get("latitude")
        lon = geo_section.get("longitude")
        if lat is not None and lon is not None:
            command_args.append(f"-GPSLatitude={lat}")
            command_args.append(f"-GPSLongitude={lon}")
            has_gps = True

    # description
    desc = metadata.get("description")
    has_desc = False
    if desc:
        command_args.append(f"-ImageDescription={desc}")
        command_args.append(f"-XMP-dc:Description={desc}")
        has_desc = True

    # preserve mtime via -P when requested
    if preserve_mtime:
        command_args.insert(1, "-P")

    command_args.append(str(photo_path))

    logger.debug(
        "Writing metadata (exiftool)",
        extra={
            "photo_path": str(photo_path),
            "has_time": has_time,
            "has_gps": has_gps,
            "has_description": has_desc,
            "preserve_mtime": preserve_mtime,
        },
    )

    result = subprocess.run(
        command_args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    stderr = result.stderr.decode(errors="replace") if result.stderr else ""

    # exiftool returns exit code 1 for minor issues but also for real errors
    # Only ignore if we recognize it as a minor/known issue
    if result.returncode != 0:
        # These are minor warnings we can safely ignore
        minor_warnings = [
            "looks more like a",  # Format mismatch warnings
            "IFD0 pointer references",  # Corrupted EXIF
            "[minor]",  # Explicitly marked as minor
        ]

        is_minor_warning = any(warning in stderr for warning in minor_warnings)

        if not is_minor_warning:
            raise RuntimeError(
                f"exiftool failed with exit code {result.returncode}: {stderr}"
            )

    # if we have an epoch timestamp and preserve_mtime is False, set mtime ourselves
    if epoch_seconds is not None and not preserve_mtime:
        try:
            os.utime(photo_path, (float(epoch_seconds), float(epoch_seconds)))
        except Exception as ut_err:
            raise RuntimeError(f"Failed to set file mtime: {ut_err}") from ut_err

    logger.debug(
        "Metadata written (exiftool)",
        extra={"photo_path": str(photo_path)},
    )


def _write_metadata_mutagen(
    photo_path: Path, metadata: Metadata, preserve_mtime: bool
) -> None:
    original_times = None
    if preserve_mtime:
        st = photo_path.stat()
        original_times = (st.st_atime, st.st_mtime)

    mp4 = cast(Any, MP4(str(photo_path)))

    # date/time
    epoch_seconds: Optional[int] = None
    has_time = False
    time_section = metadata.get("photoTakenTime")
    if isinstance(time_section, dict):
        ts = time_section.get("timestamp")
        if ts:
            res = format_timestamp_for_exif(ts)
            if res:
                exif_dt, epoch_seconds = res
                mp4["\xa9day"] = exif_dt
                has_time = True

    # description
    desc = metadata.get("description")
    has_desc = False
    if desc:
        mp4["\xa9cmt"] = desc
        has_desc = True

    logger.debug(
        "Writing metadata (mutagen/MP4)",
        extra={
            "photo_path": str(photo_path),
            "has_time": has_time,
            "has_description": has_desc,
            "preserve_mtime": preserve_mtime,
        },
    )

    mp4.save()

    if preserve_mtime and original_times is not None:
        os.utime(photo_path, original_times)
    elif epoch_seconds is not None:
        os.utime(photo_path, (float(epoch_seconds), float(epoch_seconds)))

    logger.debug(
        "Metadata written (mutagen/MP4)",
        extra={"photo_path": str(photo_path)},
    )


def write_metadata(
    photo_path: Path, metadata: Metadata, preserve_mtime: bool = True
) -> None:
    """Write metadata to file based on type.

    Uses piexif for JPEG, PIL for PNG, mutagen for MP4/MOV, and exiftool for HEIC.
    BMP files are converted to PNG before writing metadata.
    """
    suffix = photo_path.suffix.lower()

    # Convert BMP to PNG for metadata support
    if suffix == ".bmp":
        photo_path = _convert_to_png(photo_path, "BMP")
        suffix = ".png"

    match suffix:
        case ".jpg" | ".jpeg":
            _write_metadata_piexif(photo_path, metadata, preserve_mtime)
        case ".mp4" | ".mov":
            _write_metadata_mutagen(photo_path, metadata, preserve_mtime)
        case ".png":
            _write_metadata_png(photo_path, metadata, preserve_mtime)
        case _:
            _write_metadata_exiftool(photo_path, metadata, preserve_mtime)
