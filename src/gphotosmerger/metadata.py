"""Metadata types and loader for Google Takeout supplemental JSON files."""

import json
from pathlib import Path
from typing import Optional, TypedDict, cast


class TimeDict(TypedDict, total=False):
    timestamp: str
    formatted: str


class GeoData(TypedDict, total=False):
    latitude: float
    longitude: float
    altitude: float
    latitudeSpan: float
    longitudeSpan: float


class MobileUpload(TypedDict, total=False):
    deviceType: str


class GooglePhotosOrigin(TypedDict, total=False):
    mobileUpload: MobileUpload


class Metadata(TypedDict, total=False):
    title: str
    description: str
    imageViews: str
    creationTime: TimeDict
    photoTakenTime: TimeDict
    geoData: GeoData
    url: str
    googlePhotosOrigin: GooglePhotosOrigin


def find_json(photo_path: Path, metadata_suffixes: list[str]) -> Optional[Path]:
    """Try to find metadata JSON file with multiple possible suffixes.

    Also handles -edited suffix: if photo is named 'photo-edited.jpg',
    tries both 'photo-edited.jpg' and 'photo.jpg' as base names.
    """
    # First try with the original filename
    for suffix in metadata_suffixes:
        json_path = photo_path.with_suffix(photo_path.suffix + suffix)
        if json_path.exists():
            return json_path

    # If photo has -edited suffix, try without it
    stem = photo_path.stem
    if stem.endswith("-edited"):
        base_stem = stem[:-7]  # Remove "-edited"
        base_photo = photo_path.with_stem(base_stem)
        for suffix in metadata_suffixes:
            json_path = base_photo.with_suffix(base_photo.suffix + suffix)
            if json_path.exists():
                return json_path

    return None


def load_metadata_from_file(json_path: Path) -> Optional[Metadata]:
    """Load and return metadata as a Metadata TypedDict or None if load fails."""
    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cast(Metadata, data)
    except Exception:
        return None
