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
                record.created, tz=datetime.UTC
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


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for console output."""

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: LogRecord) -> str:
        # Color the level name
        level_color = self.LEVEL_COLORS.get(record.levelname, "")
        colored_level = f"{level_color}{record.levelname:8s}{self.RESET}"

        # Format the message
        msg = record.getMessage()

        # Add extra fields if present
        extra_parts: list[str] = []
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
                "taskName",
            ):
                continue
            extra_parts.append(f"{key}={value}")

        # Build the final message
        if extra_parts:
            result = f"{colored_level} | {msg} | {' | '.join(extra_parts)}"
        else:
            result = f"{colored_level} | {msg}"

        # Add exception if present
        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)

        return result


def configure_file_logger(
    log_path: Path | str | None = None,
    console_output: bool = False,
    log_level: int = logging.INFO,
) -> logging.Logger:
    if log_path is None:
        log_path = Path.cwd() / "gphotosmerger.log"
    logger = logging.getLogger("gphotosmerger")
    if not logger.handlers:
        logger.setLevel(log_level)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ConsoleFormatter())
            logger.addHandler(console_handler)
    return logger
