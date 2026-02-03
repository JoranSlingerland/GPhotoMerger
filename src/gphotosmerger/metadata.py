"""Metadata types and loader for Google Takeout supplemental JSON files."""

import json
from pathlib import Path
from typing import TypedDict, cast


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


def find_json(photo_path: Path) -> tuple[Path, float, str] | None:
    """Find metadata JSON file using fuzzy matching.

    Returns: (json_path, confidence_score, match_type) or None
    - confidence_score: 1.0 for exact, 0.7-0.99 for fuzzy
    - match_type: "exact", "substring", "fuzzy_prefix", or "fuzzy_ratio"

    This approach is more robust than trying specific suffixes, since Google Takeout
    uses various naming conventions:
    - Standard: photo.jpg.supplemental-metadata.json
    - Truncated: photo.json (stem + .json)
    - Duplicates: photo.a.jpg → photo.json or photo..json
    - Duplicates with suffix: photo(1).jpg → photo(1).json
      or photo.jpg.supplemental-metadata(1).json
    - Edited: photo-edited.jpg → photo.json

    Strategy: Find all .json files in the same directory and match
    based on name similarity. Prioritize files with matching duplicate suffixes.
    """
    import re

    parent_dir = photo_path.parent
    photo_stem = photo_path.stem

    # Extract duplicate suffix if present (e.g., "(1)", "(2)", etc.)
    photo_dup_match = re.search(r"\((\d+)\)$", photo_stem)
    photo_dup_suffix = photo_dup_match.group(0) if photo_dup_match else None

    # Normalize the stem by removing -edited suffix
    if photo_stem.endswith("-edited"):
        photo_stem = photo_stem[:-7]  # Remove "-edited"

    # Remove duplicate suffix for matching
    # e.g., "IMG_1172(1)" → "IMG_1172"
    photo_stem_normalized = re.sub(r"\(\d+\)$", "", photo_stem)

    # Get all JSON files in the same directory
    json_files = list(parent_dir.glob("*.json"))

    if not json_files:
        return None

    best_match: Path | None = None
    best_score: float = 0.0
    best_match_type: str = ""

    for json_file in json_files:
        json_stem = json_file.stem

        # Check if JSON file has a matching duplicate suffix
        json_dup_match = re.search(r"\((\d+)\)$", json_stem)
        json_dup_suffix = json_dup_match.group(0) if json_dup_match else None

        # Bonus for matching duplicate suffix
        dup_match_bonus = (
            0.1 if (photo_dup_suffix and json_dup_suffix == photo_dup_suffix) else 0.0
        )

        # Strategy 1: Exact match of stems
        if photo_stem == json_stem:
            return (json_file, 1.0, "exact")

        # Strategy 1b: Exact match after removing duplicate suffix
        # e.g., "IMG_1172(1)" vs "IMG_1172" (photo stem normalized)
        if photo_stem_normalized == json_stem:
            return (json_file, 1.0 + dup_match_bonus, "exact")

        # Strategy 2: JSON stem is a substring of photo stem (handles standard suffixes)
        # e.g., "photo.jpg" stem vs "photo.jpg.supplemental-metadata" stem
        if json_stem.startswith(photo_stem):
            return (json_file, 1.0 + dup_match_bonus, "substring")

        # Strategy 2b: JSON stem starts with normalized photo stem
        # e.g., "IMG_1172.JPG.supplemental-metadata" vs "IMG_1172(1)"
        if json_stem.startswith(photo_stem_normalized):
            return (json_file, 1.0 + dup_match_bonus, "substring")

        # Strategy 3: Photo stem starts with JSON stem (handles truncated files)
        # e.g., "photo.a" stem vs "photo" stem
        if photo_stem.startswith(json_stem):
            # Score based on how much of the photo name is the json name
            match_ratio = len(json_stem) / len(photo_stem)
            if match_ratio > 0.6:  # At least 60% match
                match_score = match_ratio + dup_match_bonus
                if match_score > best_score:
                    best_match = json_file
                    best_score = match_score
                    best_match_type = "fuzzy_ratio"
                if match_ratio > 0.85:  # Very confident match
                    return (json_file, match_score, "fuzzy_ratio")
            continue

        # Strategy 3b: Same as 3 but with normalized stem
        if photo_stem_normalized.startswith(json_stem):
            match_ratio = len(json_stem) / len(photo_stem_normalized)
            if match_ratio > 0.6:
                match_score = match_ratio + dup_match_bonus
                if match_score > best_score:
                    best_match = json_file
                    best_score = match_score
                    best_match_type = "fuzzy_ratio"
                if match_ratio > 0.85:
                    return (json_file, match_score, "fuzzy_ratio")
            continue

        # Strategy 4: Fuzzy match on common prefix (handles .a, .b duplicates)
        # e.g., "photo.a" stem vs "photo." stem
        # Find the longest common prefix
        common_prefix_len = 0
        for i in range(min(len(photo_stem), len(json_stem))):
            if photo_stem[i] == json_stem[i]:
                common_prefix_len = i + 1
            else:
                break

        if common_prefix_len > 8:  # Min prefix length to be meaningful
            similarity = common_prefix_len / max(len(photo_stem), len(json_stem))
            match_score = similarity + dup_match_bonus
            if match_score > best_score:
                best_match = json_file
                best_score = match_score
                best_match_type = "fuzzy_prefix"

        # Strategy 4b: Same as 4 but with normalized stem
        common_prefix_len = 0
        for i in range(min(len(photo_stem_normalized), len(json_stem))):
            if photo_stem_normalized[i] == json_stem[i]:
                common_prefix_len = i + 1
            else:
                break

        if common_prefix_len > 8:
            similarity = common_prefix_len / max(
                len(photo_stem_normalized), len(json_stem)
            )
            match_score = similarity + dup_match_bonus
            if match_score > best_score:
                best_match = json_file
                best_score = match_score
                best_match_type = "fuzzy_prefix"

    if best_match is not None and best_score > 0.7:
        return (best_match, best_score, best_match_type)

    return None


def load_metadata_from_file(json_path: Path) -> Metadata | None:
    """Load and return metadata as a Metadata TypedDict or None if load fails."""
    try:
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cast(Metadata, data)
    except Exception:
        return None
