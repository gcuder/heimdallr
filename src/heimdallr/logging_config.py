"""Logging configuration for heimdallr."""

import logging
from pathlib import Path

from .config import LOG_FILE, STATE_DIR

parse_logger = logging.getLogger("heimdallr.parse_errors")


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    parse_logger.setLevel(logging.WARNING)
    if not parse_logger.handlers:
        handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        handler.setLevel(logging.WARNING)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        parse_logger.addHandler(handler)
        parse_logger.propagate = False


def log_parse_error(agent: str, file_path: str | Path, error_type: str, message: str) -> None:
    parse_logger.warning("[%s] %s in %s: %s", agent, error_type, file_path, message)


def get_log_file_path() -> Path:
    return LOG_FILE
