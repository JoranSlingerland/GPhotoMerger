gphotomerger — Google Photos Takeout EXIF writer
===============================================

Quick usage
-----------

Install dependencies from `pyproject.toml`:

```bash
pip install -e .
```

Run the tool (PowerShell example):

```powershell
$env:PYTHONPATH='src'
python -m gphotosmerger.main --source "E:\\Takeout\\Google Photos" --export-dir "E:\\exports" --log-file ".\\gphotosmerger.log"
```

Options
- `--source` / `-s`: Root path of your Google Takeout photos (required).
- `--export-dir` / `-o`: Directory where photos and supplemental JSON will be copied before processing (required).
- `--log-file` / `-l`: Path to the JSON log file (default `./gphotosmerger.log`).

Notes
- The tool copies supported image files and their `.supplemental-metadata.json` files into the export directory preserving relative paths, then writes EXIF metadata into the copied files using `exiftool`.
- Ensure `exiftool` is installed and available on your PATH.
