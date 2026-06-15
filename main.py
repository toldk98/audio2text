import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from cli import run_cli
        run_cli()
    else:
        from gui.app import run_gui
        run_gui()
