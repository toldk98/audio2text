import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler

import platformdirs

LOG_DIR = os.path.join(platformdirs.user_log_dir("audio2text"), "logs")
_LOG_CONFIGURED = False


class _StdoutHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.terminator = "\n"

    def emit(self, record):
        msg = self.format(record)
        try:
            sys.stdout.write(msg + self.terminator)
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def setup_logging():
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    _LOG_CONFIGURED = True

    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("audio2text")
    logger.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "audio2text.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)

    sh = _StdoutHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(sh)


def get_logger(name: str = None) -> logging.Logger:
    return logging.getLogger(f"audio2text.{name}" if name else "audio2text")


def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
