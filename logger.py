import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from workdirs import WorkDirs

_LOG_CONFIGURED = False


class _TerminalHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.terminator = "\n"

    def emit(self, record):
        msg = self.format(record)
        try:
            out = sys.__stdout__
            if out is not None:
                out.write(msg + self.terminator)
                out.flush()
        except Exception:
            self.handleError(record)


def setup_logging():
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    _LOG_CONFIGURED = True

    log_path = WorkDirs().log_path

    logger = logging.getLogger("audio2text")
    logger.setLevel(logging.DEBUG)

    try:
        fh = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(fh)
    except OSError as e:
        print(f"[WARN] Не вдалося створити файловий логер: {e}", file=sys.stderr)

    sh = _TerminalHandler()
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
