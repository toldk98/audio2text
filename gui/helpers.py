import os
import time

from config import cpu_levels, MODEL_SIZES_MB
from gui.lang import _
from profiles import list_profiles
from workdirs import WorkDirs


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
    for key in ("size.bytes", "size.kb", "size.mb", "size.gb"):
        if abs(size) < 1024:
            return f"{size:.1f} {_(key)}"
        size /= 1024
    return f"{size:.1f} {_('size.tb')}"


def _scan_model_cache() -> list[dict]:
    entries = []

    whisper_dir = WorkDirs().whisper_cache
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

    hf_dir = WorkDirs().hf_hub
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


def _fmt_model_size_gui(mb: int) -> str:
    if mb >= 1024:
        gb = round(mb / 1024, 1)
        s = f"{gb:g}".rstrip("0").rstrip(".")
        return f"~{s} GB"
    return f"~{mb} MB"


_MODEL_SIZES = {k: _fmt_model_size_gui(v) for k, v in MODEL_SIZES_MB.items()}


def _model_cache_status(model_size: str) -> str:
    size_str = _MODEL_SIZES.get(model_size, "")
    whisper_pt = os.path.join(WorkDirs().whisper_cache, f"{model_size}.pt")
    if os.path.isfile(whisper_pt):
        sz = os.path.getsize(whisper_pt)
        return _format_size(sz)

    hf_dir = WorkDirs().hf_hub
    nd = os.path.join(hf_dir, f"models--Systran--faster-whisper-{model_size}")
    if os.path.isdir(nd):
        return _format_size(_dir_size(nd))

    if model_size.startswith("distil-"):
        d = os.path.join(hf_dir, f"models--Systran--faster-distil-whisper-{model_size[7:]}")
        if os.path.isdir(d):
            return _format_size(_dir_size(d))

    return f"⚡ {size_str}" if size_str else "⚡"


def _profile_names(mode: str | None = None) -> list[str]:
    return sorted(name for name, _ in list_profiles(mode=mode))


def _cpu_display_map() -> dict[str, str]:
    return {level: _(f"cpu.level_{level}") for level in cpu_levels}


def _cpu_level_from_workers(max_workers: int) -> str:
    ncpu = os.cpu_count() or 4
    ratio = max_workers / ncpu
    for name, lvl in sorted(cpu_levels.items(),
                            key=lambda x: x[1]["min_workers_ratio"], reverse=True):
        if ratio >= lvl["min_workers_ratio"]:
            return name
    return "low"


def _filter_display_map() -> dict[str, str]:
    return {"full": _("filter.value_full"), "light": _("filter.value_light"), "off": _("filter.value_off")}


def _lang_display_map() -> dict[str, str]:
    locales_dir = os.path.join(os.path.dirname(__file__), "locales")
    codes = []
    try:
        for fn in sorted(os.listdir(locales_dir)):
            if fn.endswith(".json"):
                codes.append(fn[:-5])
    except OSError:
        codes = ["uk", "en"]
    return {code: _(f"lang.{code}") for code in codes}
