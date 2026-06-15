import io
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import *

from profiles import list_profiles, get_profile
from registry import AUDIO_DIR
from whisper_offline import WhisperTranscriber, DownloadCancelledError
from gui.token_manager import load_token, save_token, get_storage_mode, MODES, has_keyring


class _LogRedirector(io.TextIOBase):
    def __init__(self, msg_queue: queue.Queue):
        self.queue = msg_queue
        self.original = sys.stdout

    def write(self, message):
        self.original.write(message)
        self.queue.put(message)

    def flush(self):
        self.original.flush()


def _profile_names() -> list[str]:
    return sorted(name for name, _ in list_profiles())


class Audio2TextApp(tb.Window):
    def __init__(self):
        super().__init__(title="Audio2Text Transcriber", themename="darkly")
        self.geometry("820x680")
        self.minsize(640, 480)
        self._worker: threading.Thread | None = None
        self._running = False
        self._log_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_token_state()
        self.after(200, self._drain_log)

    def _build_ui(self):
        self._notebook = tb.Notebook(self)
        self._notebook.pack(fill=BOTH, expand=True, padx=10, pady=(10, 5))

        transcribe = tb.Frame(self._notebook)
        log_tab = tb.Frame(self._notebook)
        self._notebook.add(transcribe, text="Транскрипція")
        self._notebook.add(log_tab, text="Лог")

        self._build_transcribe_tab(transcribe)
        self._build_log_tab(log_tab)

    def _build_transcribe_tab(self, parent: tb.Frame):
        parent.columnconfigure(0, weight=1)

        # --- File ---
        frame = tb.LabelFrame(parent, text="Аудіофайл", padding=10)
        frame.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)
        frame.columnconfigure(1, weight=1)

        self.file_var = tk.StringVar(value=AUDIO_DIR)
        tb.Entry(frame, textvariable=self.file_var).grid(row=0, column=1, sticky=EW, padx=(5, 5))
        tb.Button(frame, text="Огляд", command=self._browse_file).grid(row=0, column=2)

        # --- Token ---
        frame = tb.LabelFrame(parent, text="HuggingFace Token", padding=10)
        frame.grid(row=1, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(1, weight=1)

        self.token_var = tk.StringVar()
        self.token_entry = tb.Entry(frame, textvariable=self.token_var, show="*", width=50)
        self.token_entry.grid(row=0, column=1, sticky=EW, padx=(5, 5))

        self.token_mode_var = tk.StringVar()
        self.token_mode_cb = tb.Combobox(frame, textvariable=self.token_mode_var,
                                         values=list(MODES.values()), state="readonly", width=30)
        self.token_mode_cb.grid(row=0, column=2, padx=(0, 5))

        tb.Button(frame, text="Зберегти", command=self._save_token).grid(row=0, column=3)

        self.token_status_var = tk.StringVar(value="")
        tb.Label(frame, textvariable=self.token_status_var, foreground="gray").grid(
            row=1, column=1, columnspan=3, sticky=W, pady=(3, 0))

        # --- Profile ---
        frame = tb.LabelFrame(parent, text="Профіль транскрипції", padding=10)
        frame.grid(row=2, column=0, sticky=EW, pady=5, padx=10)
        frame.columnconfigure(1, weight=1)

        self.profile_var = tk.StringVar()
        names = _profile_names()
        self.profile_cb = tb.Combobox(frame, textvariable=self.profile_var,
                                      values=names, state="readonly", width=40)
        self.profile_cb.grid(row=0, column=1, sticky=W, padx=(5, 0))
        if names:
            self.profile_cb.current(0)

        # --- Run ---
        self.run_btn = tb.Button(parent, text="▶ Запустити", bootstyle="success",
                                 command=self._run, width=20)
        self.run_btn.grid(row=3, column=0, pady=(10, 5))

    def _build_log_tab(self, parent: tb.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        self.progress = tb.Progressbar(parent, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky=EW, pady=(10, 5), padx=10)

        self.log_text = tk.Text(parent, height=20, bg="#1e1e1e", fg="#d4d4d4",
                                font=("Consolas", 10), state=tk.DISABLED)
        self.log_text.grid(row=1, column=0, sticky=NSEW, padx=10, pady=(0, 10))

        scroll = tb.Scrollbar(parent, orient=tk.VERTICAL, command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky=NS, pady=(0, 10))
        self.log_text.configure(yscrollcommand=scroll.set)

    # ---------- token ----------
    def _load_token_state(self):
        token, source = load_token()
        if token:
            self.token_var.set(token)
            lbl = {"env": "🔑 змінна HF_TOKEN", "keychain": "🔑 системне сховище",
                   "file": "🔑 settings.json"}.get(source, "")
            self.token_status_var.set(lbl)

        mode = get_storage_mode()
        if mode and mode in MODES:
            self.token_mode_cb.set(MODES[mode])
        elif has_keyring():
            self.token_mode_cb.set(MODES["keychain"])
        else:
            self.token_mode_cb.set(MODES["file"])

    def _save_token(self):
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning("Помилка", "Введіть токен.")
            return

        mode_label = self.token_mode_cb.get()
        mode = next((k for k, v in MODES.items() if v == mode_label), None)
        if mode is None or mode == "ask":
            self.token_status_var.set("⚠ режим «питати кожен запуск» — токен не збережено")
            return

        try:
            save_token(token, mode)
            self.token_status_var.set("✅ токен збережено")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося зберегти токен:\n{e}")

    # ---------- file ----------
    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Виберіть аудіофайл",
            filetypes=[("Аудіо", "*.m4a *.wav *.mp3 *.ogg"), ("Всі файли", "*.*")])
        if path:
            self.file_var.set(path)

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
            messagebox.showwarning("Помилка", "Виберіть існуючий аудіофайл.")
            return

        token = self._get_token()
        if not token:
            messagebox.showwarning("Помилка", "Введіть HF_TOKEN (або збережіть його).")
            return

        profile_name = self.profile_var.get()
        if not profile_name:
            messagebox.showwarning("Помилка", "Виберіть профіль.")
            return

        cfg = get_profile(profile_name)
        if not cfg:
            messagebox.showwarning("Помилка", f"Профіль '{profile_name}' не знайдено.")
            return

        self._running = True
        self.run_btn.configure(state=DISABLED, text="⏳ Обробка...")
        self.progress.start(10)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self._switch_to_log()

        self._worker = threading.Thread(
            target=self._transcribe_worker, args=(file_path, cfg, token), daemon=True)
        self._worker.start()
        self.after(200, self._poll_worker)

    def _switch_to_log(self):
        for i in range(self._notebook.index("end")):
            if self._notebook.tab(i, "text") == "Лог":
                self._notebook.select(i)
                break

    def _transcribe_worker(self, file_path: str, cfg: dict, token: str):
        redirector = _LogRedirector(self._log_queue)
        old_stdout = sys.stdout
        sys.stdout = redirector
        try:
            transcriber = WhisperTranscriber(
                hf_token=token,
                model_size=cfg.get("model", "large-v3"),
                language=cfg.get("language", "uk"),
                clean_mode=cfg.get("clean_mode", "temp"),
                clean_dir=cfg.get("clean_dir"),
                post_action=cfg.get("post_action", "delete"),
                post_dir=cfg.get("post_dir"),
                do_align=cfg.get("align", True),
                do_diarize=cfg.get("diarize", True),
                chunk_minutes=cfg.get("chunk_minutes", 0),
                max_workers=cfg.get("max_workers", 2),
            )
            transcriber.transcribe(file_path)
        except DownloadCancelledError:
            self._log_queue.put("❌ Завантаження скасовано користувачем.\n")
        except Exception as e:
            self._log_queue.put(f"❌ Помилка: {e}\n")
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
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.after(200, self._drain_log)

    def _poll_worker(self):
        if self._worker and self._worker.is_alive():
            self.after(200, self._poll_worker)

    def _on_done(self):
        self.run_btn.configure(state=NORMAL, text="▶ Запустити")
        self.progress.stop()
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, "\n✅ Готово.\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def run_gui():
    Audio2TextApp().mainloop()
