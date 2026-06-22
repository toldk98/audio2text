import logging
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
from registry import list_external, list_dead, add_external, remove_entry, load_registry
from gui.token_manager import load_token, save_token, _token_modes, has_keyring
from config import cpu_levels, MODEL_SIZES_MB
from timing import TimingDB
from split_audio import _get_duration
from gui.lang import _, _inst
from workdirs import WorkDirs
from settings import load_settings, save_settings
from gui.helpers import (_dir_size, _format_size, _scan_model_cache,
                         _model_cache_status, _profile_names, _MODEL_SIZES,
                         _cpu_display_map, _cpu_level_from_workers, _filter_display_map, _lang_display_map)
from gui.widgets import _ToolTip, _GuiLogHandler


class Audio2TextApp(tb.Window):
    def __init__(self):
        settings = load_settings()
        theme = settings.get("theme", "darkly")
        super().__init__(title=_("app.title"), themename=theme)
        self.geometry("820x680")
        self.minsize(640, 480)
        self._worker: threading.Thread | None = None
        self._running = False
        self.timing_gui = TimingDB()
        self._stop_event: threading.Event | None = None
        self._log_queue: queue.Queue = queue.Queue()
        self._hf_token_validated = False
        self._hf_token_valid = False

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
        self._file_frame = tb.LabelFrame(parent, text=_("file.frame"))
        self._file_frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)
        self._file_frame.columnconfigure(1, weight=1)

        self.file_var = tk.StringVar(value=WorkDirs().audio_dir)
        tb.Entry(self._file_frame, textvariable=self.file_var).grid(row=0, column=1, sticky=EW, padx=(5, 5))
        self._browse_btn = tb.Button(self._file_frame, text=_("file.browse"), command=self._browse_file)
        self._browse_btn.grid(row=0, column=2)

        self._reg_refresh_var = tk.StringVar()
        self._reg_label = tb.Label(self._file_frame, text=_("file.registry_label"))
        self._reg_label.grid(row=1, column=0, padx=(0, 5), pady=(5, 0))
        self.reg_cb = tb.Combobox(self._file_frame, textvariable=self._reg_refresh_var,
                                  values=[], state="readonly", width=50)
        self.reg_cb.grid(row=1, column=1, sticky=EW, padx=(5, 5), pady=(5, 0))
        self.reg_cb.bind("<<ComboboxSelected>>", self._on_registry_pick)
        self._reg_add_btn = tb.Button(self._file_frame, text=_("file.add_to_registry"),
                                      command=self._add_to_registry, width=14)
        self._reg_add_btn.grid(row=1, column=2, pady=(5, 0))
        self._refresh_registry_list()

        # --- Profile ---
        self._profile_frame = tb.LabelFrame(parent, text=_("profile.frame"))
        self._profile_frame.grid(row=1, column=0, sticky=EW, pady=5, padx=10)
        self._profile_frame.columnconfigure(1, weight=1)

        self.profile_var = tk.StringVar()
        names = _profile_names()
        self.profile_cb = tb.Combobox(self._profile_frame, textvariable=self.profile_var,
                                      values=names, state="readonly", width=40)
        self.profile_cb.grid(row=0, column=1, sticky=W, padx=(5, 0))
        if names:
            self.profile_cb.current(0)

        self.profile_desc_var = tk.StringVar()
        tb.Label(self._profile_frame, textvariable=self.profile_desc_var, foreground="gray", wraplength=600).grid(
            row=1, column=1, sticky=W, padx=(5, 0), pady=(3, 0))

        self._timing_var = tk.StringVar()
        tb.Label(self._profile_frame, textvariable=self._timing_var, foreground="cyan",
                 wraplength=600, font=("", 8, "")).grid(
            row=2, column=1, sticky=W, padx=(5, 0), pady=(1, 0))

        # --- Token ---
        self._token_frame = tb.LabelFrame(parent, text=_("token.frame"))
        self._token_frame.grid(row=2, column=0, sticky=EW, pady=5, padx=10)
        self._token_frame.columnconfigure(1, weight=1)

        self.token_var = tk.StringVar()
        self.token_entry = tb.Entry(self._token_frame, textvariable=self.token_var, show="*", width=50)
        self.token_entry.grid(row=0, column=1, sticky=EW, padx=(5, 5))

        self.token_mode_var = tk.StringVar()
        self.token_mode_cb = tb.Combobox(self._token_frame, textvariable=self.token_mode_var,
                                         values=list(_token_modes().values()), state="readonly", width=30)
        self.token_mode_cb.grid(row=0, column=2, padx=(0, 5))

        self._save_token_btn = tb.Button(self._token_frame, text=_("token.save"), command=self._save_token)
        self._save_token_btn.grid(row=0, column=3)

        self.token_status_var = tk.StringVar(value="")
        tb.Label(self._token_frame, textvariable=self.token_status_var, foreground="gray").grid(
            row=1, column=1, columnspan=3, sticky=W, pady=(3, 0))
        self._token_frame.grid_remove()

        # --- Override Panel ---
        self._ov_btn = tb.Button(parent, text="", command=self._toggle_ov,
                                 bootstyle="secondary-link", width=35)
        self._ov_btn.grid(row=3, column=0, sticky=W, pady=(5, 0), padx=10)

        self._ov_frame = tb.Frame(parent)
        self._ov_visible = False
        self._ov_dirty = False

        ncpu = os.cpu_count() or 4
        self._ov_workers_var = tk.IntVar(value=2)
        self._ov_workers_lbl = tb.Label(self._ov_frame, text=_("cpu.label"))
        self._ov_workers_lbl.grid(row=0, column=0, sticky=W, padx=(5, 5), pady=2)
        self._ov_scale = tb.Scale(self._ov_frame, from_=1, to=ncpu,
                                  variable=self._ov_workers_var, orient=tk.HORIZONTAL,
                                  length=200, command=lambda v: self._on_ov_change())
        self._ov_scale.grid(row=0, column=1, sticky=EW, padx=(0, 10), pady=2)

        self._ov_workers_display = tk.StringVar(value="2 · Високе")
        self._ov_workers_lbl2 = tb.Label(self._ov_frame, textvariable=self._ov_workers_display,
                                         foreground="cyan", width=30)
        self._ov_workers_lbl2.grid(row=0, column=2, sticky=W, pady=2)

        self._ov_chunk_var = tk.IntVar(value=0)
        self._ov_chunk_lbl = tb.Label(self._ov_frame, text=_("profiles.dialog_chunk"))
        self._ov_chunk_lbl.grid(row=1, column=0, sticky=W, padx=(5, 5), pady=2)
        ov_chunk_spin = tb.Spinbox(self._ov_frame, from_=0, to=60, textvariable=self._ov_chunk_var, width=8)
        ov_chunk_spin.grid(row=1, column=1, sticky=W, padx=(0, 10), pady=2)

        f_disp = _filter_display_map()
        self._ov_filter_var = tk.StringVar()
        self._ov_filter_lbl = tb.Label(self._ov_frame, text=_("profiles.dialog_filter"))
        self._ov_filter_lbl.grid(row=2, column=0, sticky=W, padx=(5, 5), pady=2)
        self._ov_filter_cb = tb.Combobox(self._ov_frame, textvariable=self._ov_filter_var,
                                         values=list(f_disp.values()), state="readonly", width=12)
        self._ov_filter_cb.grid(row=2, column=1, sticky=W, padx=(0, 10), pady=2)

        self._ov_align_var = tk.BooleanVar(value=True)
        self._ov_diarize_var = tk.BooleanVar(value=False)
        ov_align_frame = tb.Frame(self._ov_frame)
        ov_align_frame.grid(row=3, column=0, columnspan=2, sticky=W, padx=5, pady=2)
        self._ov_align_cb = tb.Checkbutton(ov_align_frame, text=_("profiles.dialog_align"),
                                           variable=self._ov_align_var)
        self._ov_align_cb.pack(side=LEFT, padx=(0, 15))
        self._ov_diarize_cb = tb.Checkbutton(ov_align_frame, text=_("profiles.dialog_diarize"),
                                             variable=self._ov_diarize_var)
        self._ov_diarize_cb.pack(side=LEFT)

        self._ov_refresh_btn_text()
        self._update_workers_display()
        for var in (self._ov_workers_var, self._ov_chunk_var,
                    self._ov_filter_var, self._ov_align_var, self._ov_diarize_var):
            var.trace_add("write", lambda *a: self._on_ov_change())
        self.profile_cb.bind("<<ComboboxSelected>>", self._update_profile_desc)
        self.file_var.trace_add("write", lambda *a: self._update_profile_desc())
        self._update_profile_desc()

        # --- Run ---
        self.run_btn = tb.Button(parent, text=_("run.start"), bootstyle="success",
                                 command=self._run, width=20)
        self.run_btn.grid(row=5, column=0, pady=(10, 5))

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
        parent.rowconfigure(0, weight=1)

        self._settings_sub = tb.Notebook(parent)
        self._settings_sub.grid(row=0, column=0, sticky=NSEW, padx=10, pady=(10, 10))

        # --- Sub-tab: General (Theme + Language) ---
        self._general_frame = tb.Frame(self._settings_sub)
        self._general_frame.columnconfigure(0, weight=1)
        self._settings_sub.add(self._general_frame, text=_("settings.sub_general"))

        self._theme_frame = tb.LabelFrame(self._general_frame, text=_("settings.theme_frame"))
        self._theme_frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)
        self._theme_frame.columnconfigure(1, weight=1)

        self.theme_var = tk.StringVar(value=self.style.theme.name)
        themes = sorted(self.style.theme_names())
        tb.Combobox(self._theme_frame, textvariable=self.theme_var, values=themes,
                    state="readonly", width=30).grid(row=0, column=1, sticky=W, padx=(5, 5))
        self._theme_apply_btn = tb.Button(self._theme_frame, text=_("settings.theme_apply"),
                                          command=self._apply_theme)
        self._theme_apply_btn.grid(row=0, column=2)

        self._lang_frame = tb.LabelFrame(self._general_frame, text=_("settings.lang_frame"))
        self._lang_frame.grid(row=1, column=0, sticky=EW, pady=5, padx=10)
        self._lang_frame.columnconfigure(1, weight=1)
        self._lang_label = tb.Label(self._lang_frame, text=_("settings.lang_label"))
        self._lang_label.grid(row=0, column=0, sticky=W, padx=(10, 5), pady=5)
        ldm = _lang_display_map()
        self.lang_var = tk.StringVar(value=ldm.get(_inst.current, "uk"))
        self._lang_cb = tb.Combobox(self._lang_frame, textvariable=self.lang_var,
                                    values=sorted(ldm.values()), state="readonly", width=16)
        self._lang_cb.grid(row=0, column=1, sticky=W, padx=(0, 10), pady=5)
        self._lang_apply_btn = tb.Button(self._lang_frame, text=_("settings.lang_apply"),
                                         command=self._apply_lang)
        self._lang_apply_btn.grid(row=0, column=2)

        self._general_frame.rowconfigure(2, weight=1)

        # --- Sub-tab: Profiles ---
        profiles = tb.Frame(self._settings_sub)
        profiles.columnconfigure(0, weight=1)
        profiles.rowconfigure(0, weight=1)
        self._settings_sub.add(profiles, text=_("settings.sub_profiles"))

        self._profiles_sub = tb.Notebook(profiles)
        self._profiles_sub.grid(row=0, column=0, sticky=NSEW, padx=0, pady=0)

        # v2.0: add realtime tab via self._profiles_sub.add(realtime_tab, text=_("settings.sub_realtime"))

        file_tab = tb.Frame(self._profiles_sub)
        file_tab.columnconfigure(0, weight=1)
        file_tab.rowconfigure(0, weight=1)
        self._profiles_sub.add(file_tab, text=_("profiles.sub_file"))

        self._pf_frame = tb.LabelFrame(file_tab, text=_("profiles.frame"))
        self._pf_frame.grid(row=0, column=0, sticky=NSEW, pady=(10, 10), padx=10)
        self._pf_frame.columnconfigure(0, weight=1)
        self._pf_frame.rowconfigure(0, weight=1)

        self.profile_tree = ttk.Treeview(self._pf_frame, columns=("name", "model", "lang", "opts"),
                                         show="headings", selectmode="browse")
        self.profile_tree.heading("name", text=_("profiles.col_name"))
        self.profile_tree.heading("model", text=_("profiles.col_model"))
        self.profile_tree.heading("lang", text=_("profiles.col_lang"))
        self.profile_tree.heading("opts", text=_("profiles.col_opts"))
        self.profile_tree.column("name", width=160)
        self.profile_tree.column("model", width=140)
        self.profile_tree.column("lang", width=50)
        self.profile_tree.column("opts", width=200)
        self.profile_tree.grid(row=0, column=0, sticky=NSEW, pady=(5, 5), padx=5)
        self.profile_tree.bind("<Double-1>", lambda e: self._edit_selected_profile())

        pf_btn_row = tb.Frame(self._pf_frame)
        pf_btn_row.grid(row=1, column=0, sticky=W, padx=5, pady=(0, 5))
        self._pf_add_btn = tb.Button(pf_btn_row, text=_("profiles.add"), command=self._add_profile_dialog,
                                     width=12)
        self._pf_add_btn.pack(side=LEFT, padx=(0, 3))
        self._pf_edit_btn = tb.Button(pf_btn_row, text=_("profiles.edit"), command=self._edit_selected_profile,
                                      width=14)
        self._pf_edit_btn.pack(side=LEFT, padx=(0, 3))
        self._pf_del_btn = tb.Button(pf_btn_row, text=_("profiles.delete"), bootstyle="danger",
                                     command=self._delete_selected_profile, width=12)
        self._pf_del_btn.pack(side=LEFT)

        # --- Sub-tab: Models (auto-download + cache) ---
        models = tb.Frame(self._settings_sub)
        models.columnconfigure(0, weight=1)
        models.rowconfigure(1, weight=1)
        self._settings_sub.add(models, text=_("settings.sub_models"))

        self._mdl_frame = tb.LabelFrame(models, text=_("settings.models_frame"))
        self._mdl_frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)

        self.allow_dl_var = tk.BooleanVar(value=True)
        self._auto_dl_check = tb.Checkbutton(self._mdl_frame, text=_("settings.models_auto"),
                                             variable=self.allow_dl_var)
        self._auto_dl_check.grid(row=0, column=0, sticky=W, pady=5, padx=5)
        self._auto_dl_hint = tb.Label(self._mdl_frame, text=_("settings.models_auto_hint"),
                                      foreground="gray", wraplength=600)
        self._auto_dl_hint.grid(row=1, column=0, sticky=W, padx=(15, 5), pady=(0, 5))

        self._cache_frame = tb.LabelFrame(models, text=_("cache.frame"))
        self._cache_frame.grid(row=1, column=0, sticky=NSEW, pady=5, padx=10)
        self._cache_frame.columnconfigure(0, weight=1)
        self._cache_frame.rowconfigure(1, weight=1)

        cache_btn_row = tb.Frame(self._cache_frame)
        cache_btn_row.grid(row=0, column=0, sticky=W, pady=(5, 0), padx=5)
        self._cache_refresh_btn = tb.Button(cache_btn_row, text=_("cache.refresh"),
                                            command=self._refresh_cache_list, width=14)
        self._cache_refresh_btn.pack(side=LEFT, padx=(0, 5))
        self._cache_del_btn = tb.Button(cache_btn_row, text=_("cache.delete_selected"),
                                        bootstyle="danger", command=self._delete_selected_cache)
        self._cache_del_btn.pack(side=LEFT)

        cache_columns = ("name", "type", "size", "date")
        self.cache_tree = ttk.Treeview(self._cache_frame, columns=cache_columns, show="headings",
                                       selectmode="extended")
        self.cache_tree.heading("name", text=_("cache.col_name"))
        self.cache_tree.heading("type", text=_("cache.col_type"))
        self.cache_tree.heading("size", text=_("cache.col_size"))
        self.cache_tree.heading("date", text=_("cache.col_date"))
        self.cache_tree.column("name", width=320)
        self.cache_tree.column("type", width=80)
        self.cache_tree.column("size", width=90, anchor="e")
        self.cache_tree.column("date", width=90)
        self.cache_tree.grid(row=1, column=0, sticky=NSEW, pady=5, padx=5)

        self.cache_total_var = tk.StringVar(value="")
        tb.Label(self._cache_frame, textvariable=self.cache_total_var, foreground="gray").grid(
            row=2, column=0, sticky=E, padx=10, pady=(0, 5))

        # --- Sub-tab: Files (Registry) ---
        files = tb.Frame(self._settings_sub)
        files.columnconfigure(0, weight=1)
        files.rowconfigure(0, weight=1)
        self._settings_sub.add(files, text=_("settings.sub_files"))

        self._reg_frame = tb.LabelFrame(files, text=_("registry.frame"))
        self._reg_frame.grid(row=0, column=0, sticky=NSEW, pady=(10, 10), padx=10)
        self._reg_frame.columnconfigure(0, weight=1)
        self._reg_frame.rowconfigure(0, weight=1)

        self.reg_tree = ttk.Treeview(self._reg_frame, columns=("name", "path", "status"),
                                     show="headings", selectmode="browse")
        self.reg_tree.heading("name", text=_("registry.col_name"))
        self.reg_tree.heading("path", text=_("registry.col_path"))
        self.reg_tree.heading("status", text=_("registry.col_status"))
        self.reg_tree.column("name", width=120)
        self.reg_tree.column("path", width=320)
        self.reg_tree.column("status", width=60)
        self.reg_tree.grid(row=0, column=0, sticky=NSEW, pady=(5, 5), padx=5)

        reg_btn_row = tb.Frame(self._reg_frame)
        reg_btn_row.grid(row=1, column=0, sticky=W, padx=5, pady=(0, 5))
        self._reg_refresh_btn = tb.Button(reg_btn_row, text=_("registry.refresh"),
                                          command=self._refresh_registry_tree, width=4)
        self._reg_refresh_btn.pack(side=LEFT, padx=(0, 3))
        self._reg_del_btn = tb.Button(reg_btn_row, text=_("registry.delete"), bootstyle="danger",
                                      command=self._delete_selected_registry, width=14)
        self._reg_del_btn.pack(side=LEFT, padx=(0, 3))
        self._reg_clean_btn = tb.Button(reg_btn_row, text=_("registry.clean_dead"),
                                        command=self._clean_dead_registry, width=14)
        self._reg_clean_btn.pack(side=LEFT)

        self._cache_entries: list[dict] = []
        self._refresh_cache_list()
        self._refresh_registry_tree()
        self._refresh_profile_list()

    def _apply_theme(self):
        name = self.theme_var.get()
        if name:
            self.style.theme_use(name)
            save_settings({"theme": name})

    def _apply_lang(self):
        ldm = _lang_display_map()
        rev = {v: k for k, v in ldm.items()}
        lang = rev.get(self.lang_var.get(), "uk")
        if lang == _inst.current:
            return
        _inst.switch_to(lang)
        save_settings({"lang": lang})

        self._notebook.tab(0, text=_("tab.transcribe"))
        self._notebook.tab(1, text=_("tab.log"))
        self._notebook.tab(2, text=_("tab.settings"))

        self._file_frame.configure(text=_("file.frame"))
        self._browse_btn.configure(text=_("file.browse"))
        self._reg_label.configure(text=_("file.registry_label"))
        self._reg_add_btn.configure(text=_("file.add_to_registry"))
        self._token_frame.configure(text=_("token.frame"))
        self._save_token_btn.configure(text=_("token.save"))
        self._profile_frame.configure(text=_("profile.frame"))
        self.run_btn.configure(text=_("run.start"))

        self._ov_workers_lbl.configure(text=_("cpu.label"))
        self._ov_chunk_lbl.configure(text=_("profiles.dialog_chunk"))
        self._ov_filter_lbl.configure(text=_("profiles.dialog_filter"))
        self._ov_align_cb.configure(text=_("profiles.dialog_align"))
        self._ov_diarize_cb.configure(text=_("profiles.dialog_diarize"))
        self._update_workers_display()
        f_disp = _filter_display_map()
        f_rev = {v: k for k, v in f_disp.items()}
        cur_f = f_rev.get(self._ov_filter_var.get(), "full")
        self._ov_filter_cb.configure(values=list(f_disp.values()))
        self._ov_filter_var.set(f_disp[cur_f])
        self._ov_refresh_btn_text()

        self._settings_sub.tab(0, text=_("settings.sub_general"))
        self._settings_sub.tab(1, text=_("settings.sub_profiles"))
        self._settings_sub.tab(2, text=_("settings.sub_models"))
        self._settings_sub.tab(3, text=_("settings.sub_files"))
        self._theme_frame.configure(text=_("settings.theme_frame"))
        self._theme_apply_btn.configure(text=_("settings.theme_apply"))
        self._lang_frame.configure(text=_("settings.lang_frame"))
        self._lang_label.configure(text=_("settings.lang_label"))
        self._lang_apply_btn.configure(text=_("settings.lang_apply"))

        self._profiles_sub.tab(0, text=_("profiles.sub_file"))
        self._pf_frame.configure(text=_("profiles.frame"))
        self._pf_add_btn.configure(text=_("profiles.add"))
        self._pf_edit_btn.configure(text=_("profiles.edit"))
        self._pf_del_btn.configure(text=_("profiles.delete"))
        self.profile_tree.heading("name", text=_("profiles.col_name"))
        self.profile_tree.heading("model", text=_("profiles.col_model"))
        self.profile_tree.heading("lang", text=_("profiles.col_lang"))
        self.profile_tree.heading("opts", text=_("profiles.col_opts"))

        self._mdl_frame.configure(text=_("settings.models_frame"))
        self._auto_dl_check.configure(text=_("settings.models_auto"))
        self._auto_dl_hint.configure(text=_("settings.models_auto_hint"))
        self._cache_frame.configure(text=_("cache.frame"))
        self._cache_refresh_btn.configure(text=_("cache.refresh"))
        self._cache_del_btn.configure(text=_("cache.delete_selected"))
        self.cache_tree.heading("name", text=_("cache.col_name"))
        self.cache_tree.heading("type", text=_("cache.col_type"))
        self.cache_tree.heading("size", text=_("cache.col_size"))
        self.cache_tree.heading("date", text=_("cache.col_date"))

        self._reg_frame.configure(text=_("registry.frame"))
        self._reg_refresh_btn.configure(text=_("registry.refresh"))
        self._reg_del_btn.configure(text=_("registry.delete"))
        self._reg_clean_btn.configure(text=_("registry.clean_dead"))
        self.reg_tree.heading("name", text=_("registry.col_name"))
        self.reg_tree.heading("path", text=_("registry.col_path"))
        self.reg_tree.heading("status", text=_("registry.col_status"))

        ldm = _lang_display_map()
        self.lang_var.set(ldm.get(lang, "uk"))
        self._lang_cb.configure(values=sorted(ldm.values()))

        mode_disp = _token_modes()
        self.token_mode_cb.configure(values=list(mode_disp.values()))
        current_mode = self.token_mode_var.get()
        if current_mode in mode_disp.values():
            self.token_mode_var.set(current_mode)
        elif mode_disp:
            self.token_mode_cb.current(0)

    # ---------- override panel ----------
    def _toggle_ov(self):
        self._ov_visible = not self._ov_visible
        if self._ov_visible:
            self._ov_frame.grid(row=4, column=0, sticky=EW, pady=(3, 0), padx=10)
        else:
            self._ov_frame.grid_remove()
        self._ov_refresh_btn_text()

    def _ov_refresh_btn_text(self):
        prefix = "▼" if self._ov_visible else "▶"
        base = _("override.header")
        if self._ov_dirty and not self._ov_visible:
            self._ov_btn.configure(text=f"{prefix} {base} ⚡")
        else:
            self._ov_btn.configure(text=f"{prefix} {base}")

    def _update_workers_display(self):
        val = self._ov_workers_var.get()
        level = _cpu_level_from_workers(val)
        level_text = _(f"cpu.level_{level}")
        self._ov_workers_display.set(f"{val} · {level_text}")

    def _on_ov_change(self):
        if getattr(self, "_ov_syncing", False):
            return
        self._ov_dirty = True
        self._update_workers_display()
        self._ov_refresh_btn_text()
        self._update_profile_desc(_resync=False)

    def _sync_ov_from_profile(self, cfg: dict):
        self._ov_syncing = True
        f_disp = _filter_display_map()
        self._ov_workers_var.set(cfg.get("max_workers", 2))
        self._ov_chunk_var.set(cfg.get("chunk_minutes", 0))
        filter_raw = cfg.get("clean_filter", "full")
        self._ov_filter_var.set(f_disp.get(filter_raw, filter_raw))
        self._ov_align_var.set(cfg.get("align", True))
        self._ov_diarize_var.set(cfg.get("diarize", True))
        self._ov_syncing = False
        self._ov_dirty = False
        self._update_workers_display()
        self._ov_refresh_btn_text()

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
        for item in self.reg_tree.get_children():
            self.reg_tree.delete(item)
        entries = load_registry()
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
    def _refresh_profile_list(self, mode: str = "file"):
        for item in self.profile_tree.get_children():
            self.profile_tree.delete(item)
        for name, cfg in sorted(list_profiles(mode=mode), key=lambda x: x[0]):
            model = cfg.get("model", "-")
            lang = cfg.get("language", "-")
            opts = []
            if cfg.get("align"):
                opts.append("align")
            if cfg.get("diarize"):
                opts.append("diar")
            if cfg.get("chunk_minutes", 0) > 0:
                opts.append(f"chunk{cfg['chunk_minutes']}")
            opts_str = ", ".join(opts) if opts else "-"
            self.profile_tree.insert("", tk.END, values=(name, model, lang, opts_str))
        self._refresh_transcribe_profiles()

    def _refresh_transcribe_profiles(self):
        names = _profile_names(mode="file")
        self.profile_cb.configure(values=names)
        if names and self.profile_var.get() not in names:
            self.profile_cb.current(0)
        self._update_profile_desc()

    def _open_profile_dialog(self, title: str, initial: dict | None = None, mode: str = "file") -> dict | None:
        dialog = tb.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("540x560")
        dialog.minsize(480, 520)
        dialog.columnconfigure(1, weight=1)

        result: dict = {}

        lang_display_map = {v: k for k, v in _lang_display_map().items()}

        row = 0
        tb.Label(dialog, text=_("profiles.dialog_name")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=(10, 2))
        name_var = tk.StringVar(value=(initial or {}).get("_name", ""))
        tb.Entry(dialog, textvariable=name_var, width=40).grid(row=row, column=1, sticky=EW, padx=(0, 10), pady=(10, 2))

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_desc")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        desc_var = tk.StringVar(value=(initial or {}).get("description", ""))
        tb.Entry(dialog, textvariable=desc_var, width=50).grid(row=row, column=1, sticky=EW, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_lang")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        lang_init_code = (initial or {}).get("language", "uk")
        lang_init_display = next((d for d, c in lang_display_map.items() if c == lang_init_code),
                                 _(f"lang.{lang_init_code}"))
        lang_var = tk.StringVar(value=lang_init_display)
        sorted_lang_displays = sorted(lang_display_map.keys())
        tb.Combobox(dialog, textvariable=lang_var, values=sorted_lang_displays,
                    state="readonly", width=22).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        filter_lbl = tb.Label(dialog, text=_("profiles.dialog_filter"))
        filter_lbl.grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        _ToolTip(filter_lbl, _("profiles.dialog_filter_tooltip"))
        f_disp = _filter_display_map()
        filter_init_raw = (initial or {}).get("clean_filter", "full")
        filter_var = tk.StringVar(value=f_disp.get(filter_init_raw, filter_init_raw))
        tb.Combobox(dialog, textvariable=filter_var, values=list(f_disp.values()),
                    state="readonly", width=12).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

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

        def _update_model_status(*args):
            s = _model_cache_status(model_var.get())
            model_status_var.set(s)
            model_status_lbl.configure(bootstyle="warning" if s.startswith("⚡") else "success")

        model_var.trace_add("write", _update_model_status)
        _update_model_status()

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_align")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        align_var = tk.BooleanVar(value=(initial or {}).get("align", False))
        tb.Checkbutton(dialog, variable=align_var).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_diarize")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        diarize_var = tk.BooleanVar(value=(initial or {}).get("diarize", False))
        tb.Checkbutton(dialog, variable=diarize_var).grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        f_rev = {v: k for k, v in _filter_display_map().items()}

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_workers")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        ncpu = os.cpu_count() or 4
        workers_var = tk.IntVar(value=(initial or {}).get("max_workers", 2))
        workers_spin = tb.Spinbox(dialog, from_=1, to=ncpu, textvariable=workers_var, width=8)
        workers_spin.grid(row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        row += 1
        tb.Label(dialog, text=_("profiles.dialog_chunk")).grid(row=row, column=0, sticky=W, padx=(10, 5), pady=2)
        chunk_var = tk.IntVar(value=(initial or {}).get("chunk_minutes", 0))
        tb.Spinbox(dialog, from_=0, to=60, textvariable=chunk_var, width=8).grid(
            row=row, column=1, sticky=W, padx=(0, 10), pady=2)

        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning(_("common.error"), _("profiles.dialog_err_name_required"), parent=dialog)
                return
            cfg = {
                "description": desc_var.get().strip(),
                "language": lang_display_map.get(lang_var.get(), "uk"),
                "align": align_var.get(),
                "diarize": diarize_var.get(),
                "chunk_minutes": chunk_var.get(),
                "max_workers": workers_var.get(),
                "clean_filter": f_rev.get(filter_var.get(), "full"),
                "mode": mode,
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
        result = self._open_profile_dialog(_("profiles.dialog_add_title"), mode="file")
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
        profile_mode = cfg.get("mode", "file")
        result = self._open_profile_dialog(_("profiles.dialog_edit_title", name=name), initial=cfg, mode=profile_mode)
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
            self._hf_token_validated = False

        if has_keyring():
            self.token_mode_cb.set(_token_modes()["keychain"])

    def _save_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning(_("common.error"), _("token.err_empty"))
            return

        modes = _token_modes()
        rev_modes = {v: k for k, v in modes.items()}
        mode_key = rev_modes.get(self.token_mode_cb.get(), "keychain")

        if mode_key == "keychain" and not has_keyring():
            messagebox.showerror(_("common.error"), _("token.err_keychain"))
            return

        try:
            save_token(token, mode_key)
            self.token_status_var.set(_("token.saved"))
            self._hf_token_validated = False
            self._update_token_visibility(True)
        except Exception as e:
            messagebox.showerror(_("common.error"), _("token.err_save", e=e))

    # ---------- file ----------
    def _validate_hf_token(self, token: str) -> bool:
        if not token:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {token}"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _update_token_visibility(self, needed: bool):
        if not needed:
            self._token_frame.grid_remove()
            return

        token, _ = load_token()
        if not token:
            self._token_frame.grid()
            return

        if not self._hf_token_validated:
            self._hf_token_valid = self._validate_hf_token(token)
            self._hf_token_validated = True

        if self._hf_token_valid:
            self._token_frame.grid_remove()
        else:
            self._token_frame.grid()

    def _update_profile_desc(self, event=None, _resync=True):
        name = self.profile_var.get()
        if not name:
            self.profile_desc_var.set("")
            self._timing_var.set("")
            self.run_btn.configure(text=_("run.start"))
            return
        cfg = get_profile(name)
        if not cfg:
            self.profile_desc_var.set("")
            self._timing_var.set("")
            self.run_btn.configure(text=_("run.start"))
            return

        if _resync:
            self._sync_ov_from_profile(cfg)

        model = cfg.get("model", "large-v3")
        workers = self._ov_workers_var.get()
        level = _cpu_level_from_workers(workers)
        level_text = _(f"cpu.level_{level}")
        try:
            import torch
            device_str = "CUDA" if torch.cuda.is_available() else "CPU"
        except ImportError:
            device_str = "CPU"
        self.profile_desc_var.set(
            f"  {model} · {device_str} · {workers} {'потоків' if workers > 1 else 'потік'} · {level_text}")

        self._update_token_visibility(self._ov_diarize_var.get())

        # --- timing breakdown ---
        file_path = self.file_var.get().strip()
        if not file_path or not os.path.exists(file_path):
            self._timing_var.set("")
            self.run_btn.configure(text=_("run.start"))
            return

        duration = _get_duration(file_path)
        if not duration:
            self._timing_var.set("")
            return

        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
        f_rev = {v: k for k, v in _filter_display_map().items()}
        chunk_minutes = self._ov_chunk_var.get()
        do_align = self._ov_align_var.get()
        do_diarize = self._ov_diarize_var.get()
        do_clean = f_rev.get(self._ov_filter_var.get(), "full") != "off"

        try:
            pred = self.timing_gui.predict(
                model, device, duration,
                chunk_minutes, do_align, do_diarize, do_clean,
                max_workers=self._ov_workers_var.get(),
            )
        except Exception:
            self._timing_var.set("")
            self.run_btn.configure(text=_("run.start"))
            return

        def fmt(s: float) -> str:
            if s >= 3600:
                return f"{s / 3600:.1f} год"
            if s >= 60:
                return f"{s / 60:.0f} хв"
            return f"{s:.0f} с"

        lines = []
        if pred["clean"]:
            lines.append(f"  🧹 {_('timing.clean')}  ~{fmt(pred['clean'])}")
        if pred["split"]:
            n = pred.get("n_chunks", 1)
            ch = f" · {n} {'чанків' if n > 1 else 'чанк'}"
            lines.append(f"  ✂️ {_('timing.split')}  ~{fmt(pred['split'])}{ch}")
        if pred["transcribe"]:
            lines.append(f"  🎤 {_('timing.transcribe')}  ~{fmt(pred['transcribe'])}")
        if pred["merge"]:
            lines.append(f"  🧩 {_('timing.merge')}  ~{fmt(pred['merge'])}")
        if pred["align"]:
            lines.append(f"  📐 {_('timing.align')}  ~{fmt(pred['align'])}")
        if pred["diarize"]:
            lines.append(f"  👤 {_('timing.diarize')}  ~{fmt(pred['diarize'])}")
        lines.append(f"  ─────────────────────")
        lines.append(f"  ∑ {_('timing.total')}  ~{fmt(pred['total'])}")
        self._timing_var.set("\n".join(lines))

        # update run button
        total_str = fmt(pred["total"])
        self.run_btn.configure(text=f"⏵ {_('run.start')} (≈{total_str})")

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title=_("file.dialog_title"),
            filetypes=[(_("file.dialog_filter_name"), _("file.dialog_filter_pattern")),
                       (_("file.dialog_all_files"), "*.*")])
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

        from whisper_offline import _probe_nice
        ok, msg = _probe_nice()
        if not ok:
            key = "run.warn_cpu_priority" if hasattr(os, "nice") else "run.warn_cpu_priority_win"
            if not messagebox.askyesno(_("common.warning"), _(key, msg=msg), icon="warning"):
                return

        profile_name = self.profile_var.get()
        if not profile_name:
            messagebox.showwarning(_("common.error"), _("run.err_no_profile"))
            return

        cfg = get_profile(profile_name)
        if not cfg:
            messagebox.showwarning(_("common.error"), _("run.err_profile_not_found", name=profile_name))
            return

        # Merge override panel values into cfg
        f_rev = {v: k for k, v in _filter_display_map().items()}
        cfg["max_workers"] = self._ov_workers_var.get()
        cfg["chunk_minutes"] = self._ov_chunk_var.get()
        cfg["clean_filter"] = f_rev.get(self._ov_filter_var.get(), "full")
        cfg["align"] = self._ov_align_var.get()
        cfg["diarize"] = self._ov_diarize_var.get()

        # only require HF token when diarization is enabled
        self._hf_token_validated = False
        token = self._get_token()
        if cfg.get("diarize", True) and not token:
            messagebox.showwarning(_("common.error"), _("run.err_no_token"))
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
            args=(file_path, cfg, token or "", self._stop_event), daemon=True)
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

        gui_handler = _GuiLogHandler(self._log_queue)
        root_logger = logging.getLogger("audio2text")
        root_logger.addHandler(gui_handler)
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
            root_logger.removeHandler(gui_handler)
            self._running = False
            self.after(0, self._on_done)

    def _drain_log_now(self):
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

    def _drain_log(self):
        self._drain_log_now()
        self.after(200, self._drain_log)

    def _poll_worker(self):
        if self._worker and self._worker.is_alive():
            self.after(200, self._poll_worker)

    def _on_done(self):
        self._drain_log_now()
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
