gphotomerger — Google Photos Takeout EXIF writer
===============================================

This project has been vibecoded together; no guarantees.

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
- `--console-log`: Stream log output to console in addition to log file.
- `--log-level`: Set the logging level (default `INFO`).
- `--max-workers`: Number of parallel workers for processing (default `4`).
- `--move-files`: Move files instead of copying (faster, but removes originals).

Notes

- Supported extensions: `.jpg`, `.jpeg`, `.png`, `.heic`, `.mp4`, `.mov`, `.gif`, `.bmp`.
- JPEG uses `piexif`, PNG uses `Pillow`, MP4/MOV uses `mutagen`, and HEIC uses `exiftool`.
- BMP files are converted to PNG for metadata support; GIF metadata is not supported.
- Ensure `exiftool` is installed and available on your PATH for HEIC and fallback cases.

Development
-----------

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run linting with ruff:

```bash
ruff check src/
ruff format src/
```

