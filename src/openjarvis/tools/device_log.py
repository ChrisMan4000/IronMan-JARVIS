"""One-line change logs of the smart-home tools (hue-set-log.txt, tado-set-log.txt).

Each line is a timestamp plus what was asked or sent; never secrets. Logging is a
convenience: a log that cannot be written never stops a device change.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def append_change(path: str, text: str) -> None:
    """Append "<YYYY-mm-dd HH:MM:SS> <text>" to the log file at path."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError as exc:
        logger.debug("change log %s not written: %s", path, exc)
