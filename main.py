import sys

from logger import setup_logging
from workdirs import WorkDirs

if __name__ == "__main__":
    WorkDirs().ensure_all()
    setup_logging()

    if len(sys.argv) > 1:
        from cli import run_cli
        run_cli()
    else:
        from gui.app import run_gui
        run_gui()
