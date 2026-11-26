"""Logging setup.

Privacy rule: never log raw document text or span surface strings at INFO
level or above. Log identifiers, counts and offsets instead. Even though all
data is synthetic, the deployed demo accepts user input, and the codebase
should model correct practice.
"""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format=_FORMAT, force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
