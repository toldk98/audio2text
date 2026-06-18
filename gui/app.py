import io
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from profiles import list_profiles, get_profile, upsert_profile, delete_profile
from registry import AUDIO_DIR, list_external, list_dead, add_external, remove_entry
from gui.token_manager import load_token, save_token, MODES, has_keyring, load_settings, save_settings
from config import cpu_levels
from gui.lang import _, _inst


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


class _LogRedirector(io.TextIOBase):
    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue
        self.original = sys.stdout

    def write(self, message):
        self.original.write(message)
        self.queue.put(message)

    def flush(self):
        self.original.flush()


def _dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _format_size(size: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def _scan_model_cache() -> list[dict]:
    entries = []

    whisper_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    if os.path.isdir(whisper_dir):
        for fname in os.listdir(whisper_dir):
            fpath = os.path.join(whisper_dir, fname)
            if not os.path.isfile(fpath) or not fname.endswith(".pt"):
                continue
            sz = os.path.getsize(fpath)
            mtime = os.path.getmtime(fpath)
            name = fname.removesuffix(".pt")
            entries.append({"name": name, "type": "Whisper", "size": sz,
                            "date": time.strftime("%Y-%m-%d", time.localtime(mtime)),
                            "path": fpath})

    hf_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    if os.path.isdir(hf_dir):
        for entry in sorted(os.listdir(hf_dir)):
            if not entry.startswith("models--"):
                continue
            parts = entry.split("--")
            name = "/".join(parts[1:])
            fpath = os.path.join(hf_dir, entry)
            if not os.path.isdir(fpath):
                continue
            sz = _dir_size(fpath)
            mtime = os.path.getmtime(fpath)
            entries.append({"name": name, "type": "HF Hub", "size": sz,
                            "date": time.strftime("%Y-%m-%d", time.localtime(mtime)),
                            "path": fpath})

    return entries


_MODEL_SIZES = {
    "tiny": "~150 MB", "base": "~300 MB", "small": "~500 MB",
    "medium": "~1.5 GB", "large-v1": "~3 GB", "large-v2": "~3 GB",
    "large-v3": "~3 GB", "large": "~3 GB",
    "distil-large-v2": "~1.5 GB", "distil-large-v3": "~1.5 GB",
    "distil-large-v3.5": "~1.5 GB",
    "large-v3-turbo": "~3 GB", "turbo": "~3 GB",
}


def _model_cache_status(model_size: str) -> str:
    size_str = _MODEL_SIZES.get(model_size, "")
    whisper_pt = os.path.join(os.path.expanduser("~"), ".cache", "whisper", f"{model_size}.pt")
    if os.path.isfile(whisper_pt):
        sz = os.path.getsize(whisper_pt)
        return _format_size(sz)

    hf_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                          f"models--Systran--faster-whisper-{model_size}")
    if os.path.isdir(hf_dir):
        return _format_size(_dir_size(hf_dir))

    hf_dir = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                          f"models--Systran--faster-distil-whisper-{model_size}")
    if os.path.isdir(hf_dir):
        return _format_size(_dir_size(hf_dir))

    return f"⚡ {size_str}" if size_str else "⚡"


def _profile_names() -> list[str]:
    return sorted(name for name, _ in list_profiles())


class Audio2TextApp(tb.Window):
    def __init__(self):
        settings = load_settings()
        theme = settings.get("theme", "darkly")
        super().__init__(title=_("app.title"), themename=theme)
        self.geometry("820x680")
        self.minsize(640, 480)
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event: threading.Event | None = None
        self._log_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_token_state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._drain_log)

    def _build_ui(self):
        self._notebook = tb.Notebook(self)
        self._notebook.pack(fill=BOTH, expand=True, padx=10, pady=(10, 5))

        transcribe = tb.Frame(self._notebook)
        log_tab = tb.Frame(self._notebook)
        settings_tab = tb.Frame(self._notebook)
        self._notebook.add(transcribe, text=_("tab.transcribe"))
        self._notebook.add(log_tab, text=_("tab.log"))
        self._notebook.add(settings_tab, text=_("tab.settings"))

        self._build_transcribe_tab(transcribe)
        self._build_log_tab(log_tab)
        self._build_settings_tab(settings_tab)

    def _build_transcribe_tab(self, parent: tb.Frame):
        parent.columnconfigure(0, weight=1)

        # --- File ---
        frame = tb.LabelFrame(parent, text=_("file.frame"))
        frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)
        frame.columnconfigure(1, weight=1)

        self.file_var = tk.StringVar(value=AUDIO_DIR)
        tb.Entry(frame, textvariable=self.file_var).grid(row=0, column=1, sticky=EW, padx=(5, 5))
        tb.Button(frame, text=_("file.browse"), command=self._browse_file).grid(row=0, column=2)

        self._reg_refresh_var = tk.StringVar()
        tb.Label(frame, text=_("file.registry_label")).grid(row=1, column=0, padx=(0, 5), pady=(5, 0))
        self.reg_cb = tb.Combobox(frame, textvariable=self._reg_refresh_var,
                                  values=[], state="readonly", width=50)
        self.reg_cb.grid(row=1, column=1, sticky=EW, padx=(5, 5), pady=(5, 0))
        self.reg_cb.bind("<<ComboboxSelected>>", self._on_registry_pick)
        tb.Button(frame, text=_("file.add_to_registry"), command=self._add_to_registry,
                  width=14).grid(row=1, column=2, pady=(5, 0))
        self._refresh_registry_list()

        # --- Token ---
        frame = tb.LabelFrame(parent, text=_("token.frame"))
        frame.grid(row=1, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(1, weight=1)

        self.token_var = tk.StringVar()
        self.token_entry = tb.Entry(frame, textvariable=self.token_var, show="*", width=50)
        self.token_entry.grid(row=0, column=1, sticky=EW, padx=(5, 5))

        self.token_mode_var = tk.StringVar()
        self.token_mode_cb = tb.Combobox(frame, textvariable=self.token_mode_var,
                                         values=list(MODES.values()), state="readonly", width=30)
        self.token_mode_cb.grid(row=0, column=2, padx=(0, 5))

        tb.Button(frame, text=_("token.save"), command=self._save_token).grid(row=0, column=3)

        self.token_status_var = tk.StringVar(value="")
        tb.Label(frame, textvariable=self.token_status_var, foreground="gray").grid(
            row=1, column=1, columnspan=3, sticky=W, pady=(3, 0))

        # --- Profile ---
        frame = tb.LabelFrame(parent, text=_("profile.frame"))
        frame.grid(row=2, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(1, weight=1)

        self.profile_var = tk.StringVar()
        names = _profile_names()
        self.profile_cb = tb.Combobox(frame, textvariable=self.profile_var,
                                      values=names, state="readonly", width=40)
        self.profile_cb.grid(row=0, column=1, sticky=W, padx=(5, 0))
        if names:
            self.profile_cb.current(0)

        self.profile_desc_var = tk.StringVar()
        tb.Label(frame, textvariable=self.profile_desc_var, foreground="gray", wraplength=600).grid(
            row=1, column=1, sticky=W, padx=(5, 0), pady=(3, 0))

        # --- CPU Load ---
        cpu_frame = tb.Frame(parent)
        cpu_frame.grid(row=3, column=0, sticky=W, pady=(5, 0), padx=10)
        tb.Label(cpu_frame, text=_("cpu.label"), foreground="gray").pack(side=LEFT, padx=(0, 5))
        self.cpu_var = tk.StringVar(value="high")
        self.cpu_cb = tb.Combobox(cpu_frame, textvariable=self.cpu_var,
                                  values=list(cpu_levels), state="readonly", width=10)
        self.cpu_cb.pack(side=LEFT)
        _ToolTip(self.cpu_cb, _("cpu.tooltip"))
        cpu_hint = tb.Label(cpu_frame, text=_("cpu.override_hint"), foreground="gray")
        cpu_hint.pack(side=LEFT, padx=(8, 0))

        self.profile_cb.bind("<<ComboboxSelected>>", self._update_profile_desc)
        self._update_profile_desc()

        # --- Run ---
        self.run_btn = tb.Button(parent, text=_("run.start"), bootstyle="success",
                                 command=self._run, width=20)
        self.run_btn.grid(row=4, column=0, pady=(10, 5))

    def _build_log_tab(self, parent: tb.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        self.progress = tb.Progressbar(parent, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky=EW, pady=(10, 2), padx=10)

        self.eta_var = tk.StringVar(value="")
        tb.Label(parent, textvariable=self.eta_var, foreground="cyan", anchor="center").grid(
            row=1, column=0, sticky=EW, padx=10, pady=(0, 5))

        self.log_text = tk.Text(parent, height=20, bg="#1e1e1e", fg="#d4d4d4",
                                font=("Consolas", 10), state=tk.DISABLED)
        self.log_text.grid(row=2, column=0, sticky=NSEW, padx=10, pady=(0, 10))

        scroll = tb.Scrollbar(parent, orient=tk.VERTICAL, command=self.log_text.yview)
        scroll.grid(row=2, column=1, sticky=NS, pady=(0, 10))
        self.log_text.configure(yscrollcommand=scroll.set)

    def _build_settings_tab(self, parent: tb.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(5, weight=1)

        # --- Theme ---
        frame = tb.LabelFrame(parent, text=_("settings.theme_frame"))
        frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)
        frame.columnconfigure(1, weight=1)

        self.theme_var = tk.StringVar(value=self.style.theme.name)
        themes = sorted(self.style.theme_names())
        tb.Combobox(frame, textvariable=self.theme_var, values=themes,
                    state="readonly", width=30).grid(row=0, column=1, sticky=W, padx=(5, 5))
        tb.Button(frame, text=_("settings.theme_apply"), command=self._apply_theme).grid(row=0, column=2)

        # --- Models ---
        frame = tb.LabelFrame(parent, text=_("settings.models_frame"))
        frame.grid(row=1, column=0, sticky=EW, pady=5, padx=10)

        self.allow_dl_var = tk.BooleanVar(value=True)
        tb.Checkbutton(frame, text=_("settings.models_auto"),
                       variable=self.allow_dl_var).grid(row=0, column=0, sticky=W, pady=5, padx=5)
        tb.Label(frame, text=_("settings.models_auto_hint"), foreground="gray", wraplength=600).grid(
            row=1, column=0, sticky=W, padx=(15, 5), pady=(0, 5))

        # --- Language ---
        lang_frame = tb.LabelFrame(parent, text=_("settings.lang_frame"))
        lang_frame.grid(row=2, column=0, sticky=EW, pady=5, padx=10)
        lang_frame.columnconfigure(1, weight=1)
        tb.Label(lang_frame, text=_("settings.lang_label")).grid(row=0, column=0, sticky=W, padx=(10, 5), pady=5)
        self.lang_var = tk.StringVar(value=_inst.current)
        lang_cb = tb.Combobox(lang_frame, textvariable=self.lang_var,
                              values=["uk", "en"], state="readonly", width=10)
        lang_cb.grid(row=0, column=1, sticky=W, padx=(0, 10), pady=5)
        lang_cb.bind("<<ComboboxSelected>>", self._on_lang_change)
        tb.Label(lang_frame, text=_("settings.lang_restart_hint"),
                 foreground="gray").grid(row=1, column=0, columnspan=2, sticky=W, padx=(10, 5), pady=(0, 5))

        # --- Profiles ---
        frame = tb.LabelFrame(parent, text=_("profiles.frame"))
        frame.grid(row=3, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(0, weight=1)

        self.profile_tree = ttk.Treeview(frame, columns=("name", "model", "lang", "opts"),
                                         show="headings", height=5, selectmode="browse")
        self.profile_tree.heading("name", text=_("profiles.col_name"))
        self.profile_tree.heading("model", text=_("profiles.col_model"))
        self.profile_tree.heading("lang", text=_("profiles.col_lang"))
        self.profile_tree.heading("opts", text=_("profiles.col_opts"))
        self.profile_tree.column("name", width=160)
        self.profile_tree.column("model", width=140)
        self.profile_tree.column("lang", width=50)
        self.profile_tree.column("opts", width=200)
        self.profile_tree.grid(row=0, column=0, sticky=EW, pady=(5, 5), padx=5)
        self.profile_tree.bind("<Double-1>", lambda e: self._edit_selected_profile())

        btn_row = tb.Frame(frame)
        btn_row.grid(row=1, column=0, sticky=W, padx=5, pady=(0, 5))
        tb.Button(btn_row, text=_("profiles.add"), command=self._add_profile_dialog,
                  width=12).pack(side=LEFT, padx=(0, 3))
        tb.Button(btn_row, text=_("profiles.edit"), command=self._edit_selected_profile,
                  width=14).pack(side=LEFT, padx=(0, 3))
        tb.Button(btn_row, text=_("profiles.delete"), bootstyle="danger",
                  command=self._delete_selected_profile, width=12).pack(side=LEFT)

        # --- Registry ---
        frame = tb.LabelFrame(parent, text=_("registry.frame"))
        frame.grid(row=4, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(0, weight=1)

        self.reg_tree = ttk.Treeview(frame, columns=("name", "path", "status"),
                                     show="headings", height=4, selectmode="browse")
        self.reg_tree.heading("name", text=_("registry.col_name"))
        self.reg_tree.heading("path", text=_("registry.col_path"))
        self.reg_tree.heading("status", text=_("registry.col_status"))
        self.reg_tree.column("name", width=120)
        self.reg_tree.column("path", width=320)
        self.reg_tree.column("status", width=60)
        self.reg_tree.grid(row=0, column=0, sticky=EW, pady=(5, 5), padx=5)

        btn_row = tb.Frame(frame)
        btn_row.grid(row=1, column=0, sticky=W, padx=5, pady=(0, 5))
        tb.Button(btn_row, text=_("registry.refresh"), command=self._refresh_registry_tree,
                  width=4).pack(side=LEFT, padx=(0, 3))
        tb.Button(btn_row, text=_("registry.delete"), bootstyle="danger",
                  command=self._delete_selected_registry, width=14).pack(side=LEFT, padx=(0, 3))
        tb.Button(btn_row, text=_("registry.clean_dead"), command=self._clean_dead_registry,
                  width=14).pack(side=LEFT)
        self._refresh_registry_tree()

        # --- Cache ---
        frame = tb.LabelFrame(parent, text=_("cache.frame"))
        frame.grid(row=5, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(0, weight=1)

        btn_row = tb.Frame(frame)
        btn_row.grid(row=0, column=0, sticky=W, pady=(5, 0), padx=5)
        tb.Button(btn_row, text=_("cache.refresh"), command=self._refresh_cache_list,
                  width=14).pack(side=LEFT, padx=(0, 5))
        tb.Button(btn_row, text=_("cache.delete_selected"), bootstyle="danger",
                  command=self._delete_selected_cache).pack(side=LEFT)

        columns = ("name", "type", "size", "date")
        self.cache_tree = ttk.Treeview(frame, columns=columns, show="headings",
                                       height=6, selectmode="extended")
        self.cache_tree.heading("name", text=_("cache.col_name"))
        self.cache_tree.heading("type", text=_("cache.col_type"))
        self.cache_tree.heading("size", text=_("cache.col_size"))
        self.cache_tree.heading("date", text=_("cache.col_date"))
        self.cache_tree.column("name", width=320)
        self.cache_tree.column("type", width=80)
        self.cache_tree.column("size", width=90, anchor="e")
        self.cache_tree.column("date", width=90)
        self.cache_tree.grid(row=1, column=0, sticky=EW, pady=5, padx=5)

        self.cache_total_var = tk.StringVar(value="")
        tb.Label(frame, textvariable=self.cache_total_var, foreground="gray").grid(
            row=2, column=0, sticky=E, padx=10, pady=(0, 5))

        self._cache_entries: list[dict] = []
        self._refresh_cache_list()
        self._refresh_profile_list()

    def _apply_theme(self):
        name = self.theme_var.get()
        if name:
            self.style.theme_use(name)
            save_settings({"theme": name})

    def _on_lang_change(self, event=None):
        lang = self.lang_var.get()
        if lang != _inst.current:
            _inst.switch_to(lang)

    # ---------- cache ----------
    def _refresh_cache_list(self):
        for item in self.cache_tree.get_children():
            self.cache_tree.delete(item)
        self._cache_entries = _scan_model_cache()
        total = 0
        for e in self._cache_entries:
            self.cache_tree.insert("", tk.END, values=(
                e["name"], e["type"], _format_size(e["size"]), e["date"]))
            total += e["size"]
        self.cache_total_var.set(_("cache.total", size=_format_size(total)))

    def _delete_selected_cache(self):
        sel = self.cache_tree.selection()
        if not sel:
            messagebox.showinfo(_("cache.frame"), _("cache.info_nothing_selected"))
            return
        names = [self.cache_tree.item(i, "values")[0] for i in sel]
        msg = _("cache.confirm_delete", n=len(sel), details="\n".join(names))
        if not messagebox.askyesno(_("common.confirm"), msg, icon="warning"):
            return
        indices = [self.cache_tree.index(i) for i in sel]
        for idx in sorted(indices, reverse=True):
            e = self._cache_entries.pop(idx)
            path = e["path"]
            try:
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
            except Exception as ex:
                messagebox.showerror(_("common.error"), _("cache.err_delete", name=e["name"], err=ex))
        self._refresh_cache_list()

    # ---------- registry ----------
    def _refresh_registry_tree(self):
        import registry as reg
        for item in self.reg_tree.get_children():
            self.reg_tree.delete(item)
        entries = reg.load_registry()
        if not entries:
            self.reg_tree.insert("", tk.END, values=(_("registry.empty_placeholder"), "", ""))
        for e in entries:
            status = _("registry.status_ok") if e["status"] == "ok" else _("registry.status_dead")
            self.reg_tree.insert("", tk.END, values=(e["name"], e["path"], status))

    def _delete_selected_registry(self):
        sel = self.reg_tree.selection()
        if not sel:
            return
        name = self.reg_tree.item(sel[0], "values")[0]
        if not name or name == _("registry.empty_placeholder"):
            return
        if messagebox.askyesno(_("registry.frame"), _("registry.confirm_delete", name=name), icon="warning"):
            remove_entry(name)
            self._refresh_registry_tree()

    def _clean_dead_registry(self):
        dead = list_dead()
        if not dead:
            messagebox.showinfo(_("registry.frame"), _("registry.info_no_dead"))
            return
        msg = _("registry.confirm_clean", entries="\n".join(e["name"] + " — " + e["path"] for e in dead))
        if messagebox.askyesno(_("registry.frame"), msg, icon="warning"):
            for e in dead:
                remove_entry(e["name"])
            self._refresh_registry_tree()

    # ---------- profiles ----------
    def _refresh_profile_list(self):
        for item in self.profile_tree.get_children():
            self.profile_tree.delete(item)
        for name, cfg in sorted(list_profiles(), key=lambda x: x[0]):
            model = cfg.get("model", "-")
            lang = cfg.get("language", "-")
            opts = []
            if cfg.get("align"):
                opts.append("align")
            if cfg.get("diarize"):
                opts.append("diar")
            if cfg.get("chunk_minutes", 0) > 0:
                opts.append(f"chunk{cfg['chunk_minutes']}")
            cpu = cfg.get("cpu_profile", "high")
            if cpu != "high":
                opts.append(f"cpu:{cpu}")
            opts_str = ", ".join(opts) if opts else "-"
            self.profile_tree.insert("", tk.END, values=(name, model, lang, opts_str))
        self._refresh_transcribe_profiles()

    def _refresh_transcribe_profiles(self):
        names = _profile_names()
        self.profile_cb.configure(values=names)
        if names and self.profile_var.get() not in names:
            self.profile_cb.current(0)
        self._update_profile_desc()

    def _open_profile_dialog(self, title: str, initial: dict | None = None) -> dict | None:
        dialog = tb.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("520x520")
        dialog.minsize(480, 480)
        dialog.columnconfigure(1, weight=1)

        result: dict = {}

        row = 0
        tb.Label(dialog, text=_("profiles.dialog_name")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=(10, 2))
        name_var = tk.StringVar(value=(initial or {}).get("_name", ""))
        tb.Entry(dialog, textvariable=name_var, width=40).grid(row=row, column=1, sticky=EW, padx=(0, 10), pady=(10, 2))

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_mode")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        mode_var = tk.StringVar(value=(initial or {}).get("mode", "file"))
        mode_cb = tb.Combobox(dialog, textvariable=mode_var, values=["file", "realtime"],
                              state="readonly", width=20)
        mode_cb.grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_model")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        MODELS = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3",
                  "large", "distil-large-v2", "distil-large-v3", "distil-large-v3.5",
                  "large-v3-turbo", "turbo"]
        model_var = tk.StringVar(value=(initial or {}).get("model", "base"))
        model_frame = tb.Frame(dialog)
        model_frame.grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)
        model_cb = tb.Combobox(model_frame, textvariable=model_var, values=MODELS,
                               state="readonly", width=20)
        model_cb.pack(side=LEFT)
        model_status_var = tk.StringVar()
        model_status_lbl = tb.Label(model_frame, textvariable=model_status_var, font=("", 9, ""))
        model_status_lbl.pack(side=LEFT, padx=(8, 0))
        def _update_model_status(*_):
            s = _model_cache_status(model_var.get())
            model_status_var.set(s)
            model_status_lbl.configure(foreground="orange" if s.startswith("⚡") else "green")
        model_var.trace_add("write", _update_model_status)
        _update_model_status()

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_desc")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        desc_var = tk.StringVar(value=(initial or {}).get("description", ""))
        tb.Entry(dialog, textvariable=desc_var, width=50).grid(row=row, column=1, sticky=EW, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_lang_code")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        lang_var = tk.StringVar(value=(initial or {}).get("language", "uk"))
        tb.Entry(dialog, textvariable=lang_var, width=10).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        align_var = tk.BooleanVar(value=(initial or {}).get("align", False))
        tb.Checkbutton(dialog, text=_("profiles.dialog_align"), variable=align_var).grid(
            row=row, column=0, columnspan=2, sticky=W, padx=(10, 5), pady=2)

        row += 1
        diarize_var = tk.BooleanVar(value=(initial or {}).get("diarize", False))
        tb.Checkbutton(dialog, text=_("profiles.dialog_diarize"), variable=diarize_var).grid(
            row=row, column=0, columnspan=2, sticky=W, padx=(10, 5), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_chunk")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        chunk_var = tk.IntVar(value=(initial or {}).get("chunk_minutes", 0))
        tb.Spinbox(dialog, from_=0, to=60, textvariable=chunk_var, width=8).grid(
            row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_workers")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        workers_var = tk.IntVar(value=(initial or {}).get("max_workers", 2))
        tb.Spinbox(dialog, from_=1, to=8, textvariable=workers_var, width=8).grid(
            row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        filter_lbl = tb.Label(dialog, text=_("profiles.dialog_filter"))
        filter_lbl.grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        _ToolTip(filter_lbl, _("profiles.dialog_filter_tooltip"))
        filter_var = tk.StringVar(value=(initial or {}).get("clean_filter", "full"))
        tb.Combobox(dialog, textvariable=filter_var, values=["full", "light", "off"],
                    state="readonly", width=10).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        cpu_lbl = tb.Label(dialog, text=_("profiles.dialog_cpu"))
        cpu_lbl.grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        _ToolTip(cpu_lbl, _("profiles.dialog_cpu_tooltip"))
        cpu_profile_var = tk.StringVar(value=(initial or {}).get("cpu_profile", "high"))
        tb.Combobox(dialog, textvariable=cpu_profile_var, values=list(cpu_levels),
                    state="readonly", width=10).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning(_("common.error"), _("profiles.dialog_err_name_required"), parent=dialog)
                return
            cfg = {
                "description": desc_var.get().strip(),
                "language": lang_var.get().strip(),
                "align": align_var.get(),
                "diarize": diarize_var.get(),
                "chunk_minutes": chunk_var.get(),
                "max_workers": workers_var.get(),
                "clean_filter": filter_var.get(),
                "cpu_profile": cpu_profile_var.get(),
                "mode": mode_var.get(),
                "model": model_var.get(),
            }
            upsert_profile(name, cfg)
            result["_name"] = name
            result["_saved"] = True
            dialog.destroy()

        row += 1
        btn_frame = tb.Frame(dialog)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(15, 10))
        tb.Button(btn_frame, text=_("profiles.dialog_save"), bootstyle="success",
                  command=on_save, width=16).pack(side=LEFT, padx=(0, 10))
        tb.Button(btn_frame, text=_("profiles.dialog_cancel"), command=dialog.destroy,
                  width=12).pack(side=LEFT)

        self.wait_window(dialog)
        return result if result.get("_saved") else None

    def _add_profile_dialog(self):
        result = self._open_profile_dialog(_("profiles.dialog_add_title"))
        if result:
            self._refresh_profile_list()

    def _edit_selected_profile(self):
        sel = self.profile_tree.selection()
        if not sel:
            messagebox.showinfo(_("profiles.frame"), _("profiles.err_select_for_edit"))
            return
        name = self.profile_tree.item(sel[0], "values")[0]
        cfg = get_profile(name)
        if not cfg:
            return
        cfg["_name"] = name
        result = self._open_profile_dialog(_("profiles.dialog_edit_title", name=name), initial=cfg)
        if result:
            self._refresh_profile_list()

    def _delete_selected_profile(self):
        sel = self.profile_tree.selection()
        if not sel:
            messagebox.showinfo(_("profiles.frame"), _("profiles.err_select_for_delete"))
            return
        name = self.profile_tree.item(sel[0], "values")[0]
        if not messagebox.askyesno(_("common.confirm"), _("profiles.confirm_delete", name=name), icon="warning"):
            return
        if delete_profile(name):
            self._refresh_profile_list()
        else:
            messagebox.showerror(_("common.error"), _("profiles.err_delete_failed", name=name))

    # ---------- token ----------
    def _load_token_state(self):
        token, source = load_token()
        if token:
            self.token_var.set(token)
            lbl = {"env": _("token.from_env"), "keychain": _("token.from_keychain")}.get(source, "")
            self.token_status_var.set(lbl)

        if has_keyring():
            self.token_mode_cb.set(MODES["keychain"])

    def _save_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning(_("common.error"), _("token.err_empty"))
            return

        if not has_keyring():
            messagebox.showerror(_("common.error"), _("token.err_keychain"))
            return

        try:
            save_token(token, self.token_mode_cb.get())
            self.token_status_var.set(_("token.saved"))
        except Exception as e:
            messagebox.showerror(_("common.error"), _("token.err_save", e=e))

    # ---------- file ----------
    def _update_profile_desc(self, event=None):
        name = self.profile_var.get()
        if not name:
            self.profile_desc_var.set("")
            return
        cfg = get_profile(name)
        if not cfg:
            self.profile_desc_var.set("")
            return
        parts = [cfg.get("description", "")]
        diar = _("profile.diarize_mark") if cfg.get("diarize") else ""
        align = _("profile.align_mark") if cfg.get("align") else ""
        extras = " · ".join(filter(None, [align, diar]))
        chunk = cfg.get("chunk_minutes", 0)
        if chunk:
            extras += _("profile.chunk_mark", n=chunk)
        cpu = cfg.get("cpu_profile", "high")
        if cpu != "high":
            extras += _("profile.cpu_mark", level=cpu)
        if extras:
            parts.append(f"[{extras}]")
        self.profile_desc_var.set("  " + "  ".join(parts))
        # sync cpu combobox with profile default
        self.cpu_var.set(cpu)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title=_("file.dialog_title"),
            filetypes=[(_("file.dialog_filter_name"), _("file.dialog_filter_pattern")), (_("file.dialog_all_files"), "*.*")])
        if path:
            self.file_var.set(path)

    # ---------- registry ----------
    def _refresh_registry_list(self):
        entries = list_external()
        names = [e["name"] for e in entries]
        self.reg_cb.configure(values=names)
        if names:
            self.reg_cb.set("")
        else:
            self.reg_cb.set(_("registry.empty_combobox"))

    def _on_registry_pick(self, event=None):
        name = self._reg_refresh_var.get()
        if not name:
            return
        for e in list_external():
            if e["name"] == name:
                self.file_var.set(e["path"])
                break

    def _add_to_registry(self):
        path = self.file_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning(_("registry.frame"), _("registry.err_no_file"))
            return
        err = add_external(path)
        if err:
            messagebox.showwarning(_("registry.frame"), _("registry.err_add_failed", err=err))
        else:
            self._refresh_registry_list()
            messagebox.showinfo(_("registry.frame"), _("registry.info_added"))

    # ---------- run ----------
    def _get_token(self) -> str | None:
        token, _ = load_token()
        if token:
            return token
        t = self.token_var.get().strip()
        return t if t else None

    def _run(self):
        if self._running:
            return

        file_path = self.file_var.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning(_("common.error"), _("run.err_no_file"))
            return

        token = self._get_token()
        if not token:
            messagebox.showwarning(_("common.error"), _("run.err_no_token"))
            return

        profile_name = self.profile_var.get()
        if not profile_name:
            messagebox.showwarning(_("common.error"), _("run.err_no_profile"))
            return

        cfg = get_profile(profile_name)
        if not cfg:
            messagebox.showwarning(_("common.error"), _("run.err_profile_not_found", name=profile_name))
            return

        self._running = True
        self._stop_event = threading.Event()
        self.run_btn.configure(text=_("run.cancel"), bootstyle="danger", command=self._cancel)
        self.progress.start(10)
        self.eta_var.set("")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self._switch_to_log()

        self._worker = threading.Thread(
            target=self._transcribe_worker,
            args=(file_path, cfg, token, self._stop_event), daemon=True)
        self._worker.start()
        self.after(200, self._poll_worker)

    def _cancel(self):
        if self._stop_event:
            self._stop_event.set()
        self.run_btn.configure(state=DISABLED, text=_("run.cancelling"))

    def _on_close(self):
        if self._running:
            if messagebox.askyesno(_("common.confirm"), _("run.confirm_exit")):
                self._cancel()
                self.destroy()
        else:
            self.destroy()

    def _switch_to_log(self):
        for i in range(self._notebook.index("end")):
            if self._notebook.tab(i, "text") == _("tab.log"):
                self._notebook.select(i)
                break

    def _transcribe_worker(self, file_path: str, cfg: dict, token: str,
                           stop_event: threading.Event):
        from whisper_offline import (WhisperTranscriber, DownloadCancelledError,
                                     TranscriptionCancelledError)

        redirector = _LogRedirector(self._log_queue)
        old_stdout = sys.stdout
        sys.stdout = redirector
        try:
            transcriber = WhisperTranscriber(
                hf_token=token,
                model_size=cfg.get("model", "large-v3"),
                language=cfg.get("language", "uk"),
                do_align=cfg.get("align", True),
                do_diarize=cfg.get("diarize", True),
                chunk_minutes=cfg.get("chunk_minutes", 0),
                max_workers=cfg.get("max_workers", 2),
                allow_download=self.allow_dl_var.get(),
                clean_filter=cfg.get("clean_filter", "full"),
                cpu_profile=self.cpu_var.get(),
                stop_event=stop_event,
            )
            transcriber.transcribe(file_path)
        except DownloadCancelledError as e:
            msg = str(e) or _("run.log_cancelled")
            self._log_queue.put(msg + "\n")
        except TranscriptionCancelledError:
            self._log_queue.put(_("run.log_stopped"))
        except Exception as e:
            self._log_queue.put(_("run.log_error", e=e))
        finally:
            sys.stdout = old_stdout
            self._running = False
            self.after(0, self._on_done)

    def _drain_log(self):
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if msg.startswith("[ETA]"):
                self.eta_var.set(msg.strip())
            elif msg.startswith("[DONE]") or msg.startswith("✅"):
                self.eta_var.set("")
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.after(200, self._drain_log)

    def _poll_worker(self):
        if self._worker and self._worker.is_alive():
            self.after(200, self._poll_worker)

    def _on_done(self):
        self.run_btn.configure(state=NORMAL, text=_("run.start"),
                               bootstyle="success", command=self._run)
        self.progress.stop()
        self.eta_var.set("")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, _("run.done"))
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def run_gui():
    from logger import check_ffmpeg
    if not check_ffmpeg():
        messagebox.showerror(_("common.error"), _("ffmpeg.err_not_found"))
        return
    Audio2TextApp().mainloop()
