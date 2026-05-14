from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR, get_settings


def setup_logging() -> logging.Logger:
    settings = get_settings()
    logger = logging.getLogger("autoblog")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_handler = RotatingFileHandler(
        LOG_DIR / "autoblog.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


logger = setup_logging()
