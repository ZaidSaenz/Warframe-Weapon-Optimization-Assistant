# modules/logger.py

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_LOGGER_NAME = "warframe_weapon_optimizer"
MAX_LOG_SIZE_BYTES = 2_000_000
BACKUP_COUNT = 5

_logger_lock = Lock()


def configure_logger(
    name: str = DEFAULT_LOGGER_NAME,
    *,
    level: int = logging.INFO,
    console: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    with _logger_lock:
        if logger.handlers:
            return logger

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        logger.setLevel(level)
        logger.propagate = False

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | "
            "%(module)s.%(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            LOGS_DIR / "warframe_weapon_optimizer.log",
            maxBytes=MAX_LOG_SIZE_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    return logger


def get_logger(module_name: str | None = None) -> logging.Logger:
    base_logger = configure_logger()

    if not module_name:
        return base_logger

    clean_name = module_name.removeprefix("modules.")
    return base_logger.getChild(clean_name)


def log_exception(
    logger: logging.Logger,
    message: str,
    error: BaseException,
    **context: object,
) -> None:
    context_text = " | ".join(
        f"{key}={value!r}" for key, value in context.items()
    )

    full_message = message
    if context_text:
        full_message = f"{message} | {context_text}"

    logger.exception("%s | error=%s", full_message, error)
