import logging
import queue
import tkinter as tk

import ttkbootstrap as tb


class _GuiLogHandler(logging.Handler):
    def __init__(self, msg_queue: queue.Queue):
        super().__init__()
        self.queue = msg_queue
        self.setLevel(logging.INFO)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        msg = self.format(record)
        self.queue.put(msg + "\n")


class _ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lbl = tb.Label(tw, text=self.text, background="#333", foreground="#eee",
                       wraplength=350, padding=(6, 3), font=("", 9, ""))
        lbl.pack()

    def _hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
