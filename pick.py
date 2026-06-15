import os
import subprocess
import sys
import glob
import tempfile
import json
import shutil

import sounddevice as sd
from dotenv import load_dotenv

from config import language_list, clean_mode_list, post_action_list, chunk_options
from profiles import list_profiles
from whisper_offline import WhisperTranscriber, DownloadCancelledError
from whisper_realtime import WhisperRealtimeTranscriber

load_dotenv()


def _check_fzf():
    return shutil.which("fzf") is not None


def _fzf_choice(items: list[str], prompt: str = "Select:") -> str | None:
    if not _check_fzf():
        print("fzf не знайдено. Встанови: sudo apt install fzf")
        return None
    input_bytes = "\n".join(items).encode("utf-8")
    try:
        result = subprocess.run(
            ["fzf", "--prompt", f"{prompt} "],
            input=input_bytes,
            capture_output=True,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8").strip()
        return None
    except subprocess.TimeoutExpired:
        return None


def _fzf_select_audio() -> str | None:
    audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Audio")
    if not os.path.isdir(audio_dir):
        print("❌ Папка ./Audio/ не знайдена")
        return None

    patterns = ["*.m4a", "*.wav", "*.mp3", "*.ogg"]
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(audio_dir, p)))
    files.sort()

    if not files:
        print("❌ Не знайдено аудіофайлів у ./Audio/")
        return None

    labels = [os.path.relpath(f, audio_dir) for f in files]
    chosen = _fzf_choice(labels, prompt="Audio file:")
    if chosen is None:
        return None
    return os.path.join(audio_dir, chosen)


def _fzf_select_device() -> int | None:
    devices = sd.query_devices()
    lines = []
    for i, dev in enumerate(devices):
        name = dev["name"]
        ch = dev["max_input_channels"]
        sr = dev["default_samplerate"]
        lines.append(f"{i}: {name} (in: {ch}, sr: {sr})")

    if not lines:
        print("❌ Не знайдено аудіопристроїв")
        return None

    chosen = _fzf_choice(lines, prompt="Audio device:")
    if chosen is None:
        return None
    idx = int(chosen.split(":")[0])
    return idx


def _fzf_choice_tsv(items: list[str], prompt: str = "Select:") -> str | None:
    if not _check_fzf():
        return None
    input_bytes = "\n".join(items).encode("utf-8")
    try:
        result = subprocess.run(
            ["fzf", "--prompt", f"{prompt} ",
             "--delimiter", "\t", "--with-nth", "1"],
            input=input_bytes,
            capture_output=True,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8").strip()
        return None
    except subprocess.TimeoutExpired:
        return None


def _get_category(cfg: dict) -> str:
    model = cfg["model"]
    mode = cfg["mode"]
    if mode == "realtime":
        return "\U0001f3a4 Реальний час"
    if model in {"tiny", "base", "small", "medium"}:
        return "\u26a1 Швидко"
    if model in {"distil-large-v2", "distil-large-v3", "distil-large-v3.5", "large-v3-turbo", "turbo"}:
        return "\u26a1\u26a1 Швидко + якісно"
    if model in {"large-v1", "large-v2", "large", "large-v3"}:
        return "\U0001f422 Максимальна якість"
    return "\U0001f4e6 Інше"


def _pick_profile() -> tuple[str, dict] | None:
    all_profiles = list_profiles()
    if not all_profiles:
        return None

    profile_lookup = {name: cfg for name, cfg in all_profiles}
    category_order = [
        "\u26a1 Швидко",
        "\u26a1\u26a1 Швидко + якісно",
        "\U0001f422 Максимальна якість",
        "\U0001f3a4 Реальний час",
    ]
    grouped = {cat: [] for cat in category_order}

    for name, cfg in all_profiles:
        cat = _get_category(cfg)
        if cat in grouped:
            grouped[cat].append((name, cfg))

    lines = []
    tab = "\t"
    for cat in category_order:
        items = grouped[cat]
        if not items:
            continue
        lines.append(f"\u2500\u2500 {cat} \u2500\u2500{tab}__HEADER__")
        for name, cfg in items:
            chunk = f" | \u0447\u0430\u043d\u043a\u0438 {cfg['chunk_minutes']}\u0445\u0432" if cfg.get("chunk_minutes", 0) > 0 else ""
            diar = "\U0001f464" if cfg.get("diarize") else "  "
            model = cfg["model"]
            desc = cfg["description"]
            display = f"  {diar} [{model:16s}] {name:25s} {desc}{chunk}"
            lines.append(f"{display}{tab}{name}")

    input_str = "\n".join(lines)

    profiles_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(profile_lookup, profiles_tmp, ensure_ascii=False)
    profiles_path = profiles_tmp.name
    profiles_tmp.close()

    script_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    script_tmp.write(f"""#!/usr/bin/env python3
import json, sys
d = json.load(open({profiles_path!r}))
raw = sys.argv[1] if len(sys.argv) > 1 else ""
parts = raw.split("\\t")
name = parts[1] if len(parts) > 1 and parts[1] != "__HEADER__" else ""
c = d.get(name, {{}})
if not c:
    print("\u2500\u2500 select a profile \u2500\u2500")
    sys.exit(0)
print(f'  Model:       {{c.get("model","-")}}')
print(f'  Language:    {{c.get("language","-")}}')
print(f'  Align:       {{"\u2705" if c.get("align") else "\u274c"}}')
print(f'  Diarize:     {{"\U0001f464" if c.get("diarize") else "\u274c"}}')
if c.get("chunk_minutes", 0) > 0:
    print(f'  Chunked:     {{c["chunk_minutes"]}} min ({{c.get("max_workers",2)}} workers)')
print(f'  Clean mode:  {{c.get("clean_mode","-")}}')
print(f'  Post action: {{c.get("post_action","-")}}')
print()
print(f'  {{c.get("description","")}}')
""")
    script_path = script_tmp.name
    script_tmp.close()

    try:
        result = subprocess.run(
            ["fzf",
             "--prompt", "Profile: ",
             "--delimiter", "\t",
             "--with-nth", "1",
             "--preview", f"python3 {script_path} {{}}",
             "--preview-window", "right:42%:wrap",
             "--header", "\u2191\u2193 navigate | Enter select | / search"],
            input=input_str.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        selected = result.stdout.decode("utf-8").strip()
        parts = selected.split("\t")
        if len(parts) >= 2 and parts[1] != "__HEADER__":
            name = parts[1]
            if name in profile_lookup:
                return name, profile_lookup[name]
        return None
    finally:
        os.unlink(profiles_path)
        os.unlink(script_path)


def _edit_cfg(cfg: dict) -> dict:
    tab = "\t"
    while True:
        items = []
        items.append(f"Language         {cfg.get('language', 'uk')}{tab}language")
        if cfg.get("mode") == "file":
            clean = cfg.get("clean_mode", "temp")
            if clean == "custom":
                clean += f" ({cfg.get('clean_dir', '?')})"
            items.append(f"Clean mode       {clean}{tab}clean_mode")
            items.append(f"Post action      {cfg.get('post_action', 'delete')}{tab}post_action")
            items.append(f"Diarization      {'yes' if cfg.get('diarize', False) else 'no'}{tab}diarize")
            items.append(f"Chunk minutes    {cfg.get('chunk_minutes', 0)}{tab}chunk_minutes")
        if cfg.get("mode") == "realtime":
            items.append(f"Chunk duration   {cfg.get('chunk_duration', 3)} sec{tab}chunk_duration")
            items.append(f"Record both      {'yes' if cfg.get('record_both', False) else 'no'}{tab}record_both")

        items.append(f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500{tab}__SEP__")
        items.append(f"\u25b6 Run now{tab}__RUN__")

        chosen = _fzf_choice_tsv(items, prompt="Edit params (Enter to run):")
        if chosen is None:
            return cfg

        parts = chosen.split(tab)
        action = parts[1] if len(parts) > 1 else "__RUN__"

        if action == "__RUN__":
            return cfg

        if action == "language":
            l = _fzf_choice(language_list, prompt="Language:")
            if l:
                cfg["language"] = l

        elif action == "clean_mode":
            c = _fzf_choice(clean_mode_list, prompt="Clean mode:")
            if c:
                cfg["clean_mode"] = c
                if c == "custom":
                    print(f"Current clean dir: {cfg.get('clean_dir', '(not set)')}")
                    inp = input("Enter path (Enter to skip): ").strip()
                    if inp:
                        cfg["clean_dir"] = inp

        elif action == "post_action":
            p = _fzf_choice(post_action_list, prompt="Post action:")
            if p:
                cfg["post_action"] = p
                if p == "move":
                    print(f"Current move dir: {cfg.get('post_dir', '(not set)')}")
                    inp = input("Enter path (Enter to skip): ").strip()
                    if inp:
                        cfg["post_dir"] = inp

        elif action == "diarize":
            d = _fzf_choice(["yes", "no"], prompt="Diarization:")
            if d:
                cfg["diarize"] = d == "yes"

        elif action == "chunk_minutes":
            c = _fzf_choice([str(x) for x in chunk_options], prompt="Chunk minutes:")
            if c:
                cfg["chunk_minutes"] = int(c)

        elif action == "chunk_duration":
            inp = input("Chunk duration (sec): ").strip()
            if inp.isdigit():
                cfg["chunk_duration"] = int(inp)

        elif action == "record_both":
            r = _fzf_choice(["yes", "no"], prompt="Record both:")
            if r:
                cfg["record_both"] = r == "yes"


def _run_file_mode(cfg: dict, audio_path: str):
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("❌ HF_TOKEN не знайдено в .env")
        sys.exit(1)

    transcriber = WhisperTranscriber(
        hf_token=hf_token,
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
    transcriber.transcribe(audio_path)


def _run_realtime_mode(cfg: dict):
    device_idx = None
    device_str = None

    choose_device = _fzf_choice(["yes - вибрати пристрій", "no - системний за замовчуванням"],
                                 prompt="Select audio device?")
    if choose_device and choose_device.startswith("yes"):
        device_idx = _fzf_select_device()

    if device_idx is not None:
        device_str = str(device_idx)

    rt = WhisperRealtimeTranscriber(
        model_size=cfg.get("model", "tiny"),
        language=cfg.get("language", "uk"),
        chunk_duration=cfg.get("chunk_duration", 3),
        record_both=cfg.get("record_both", False),
        save_audio=cfg.get("save_audio", True),
        out_file=cfg.get("out_file", "session_record.wav"),
        mic_device=device_str,
        spk_device=device_str,
    )
    rt.start()


def run_pick():
    print("=== WhisperX Pick Mode ===")

    while True:
        profile = _pick_profile()
        if profile is None:
            print("❌ Профіль не вибрано")
            return

        name, cfg = profile
        print(f"Вибрано: {name} ({cfg['model']})")
        cfg = _edit_cfg(cfg)

        try:
            if cfg["mode"] == "file":
                audio_path = _fzf_select_audio()
                if audio_path is None:
                    return
                _run_file_mode(cfg, audio_path)
            else:
                _run_realtime_mode(cfg)
            break
        except DownloadCancelledError:
            print("↩ Повернення до вибору профілю...")
            continue
