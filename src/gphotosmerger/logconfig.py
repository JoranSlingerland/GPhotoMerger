"""Structured JSON logging configuration for gphotosmerger."""

import datetime
import json as _json
import logging
from logging import LogRecord
from pathlib import Path


class JSONFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        payload = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                continue
            try:
                _json.dumps(value)
                payload[key] = value
            except Exception:
                payload[key] = repr(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return _json.dumps(payload, ensure_ascii=False)


def configure_file_logger(
    log_path: Path | str = Path.cwd() / "gphotosmerger.log",
    console_output: bool = False,
    log_level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger("gphotosmerger")
    if not logger.handlers:
        logger.setLevel(log_level)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(JSONFormatter())
            logger.addHandler(console_handler)
    return logger
