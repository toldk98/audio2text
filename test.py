import os
import sys
import json
import tempfile
import shutil
import time
import math
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_PASSED = 0
_FAILED = 0

def _check(cond, msg):
    global _PASSED, _FAILED
    if cond:
        _PASSED += 1
    else:
        _FAILED += 1
        print(f"  FAIL: {msg}")

def _section(name):
    print(f"\n=== {name} ===")

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_registry():
    _section("Registry")

    from registry import add_external, list_external, list_dead, remove_entry, load_registry, REGISTRY_PATH

    # backup real registry
    backup = None
    if os.path.exists(REGISTRY_PATH):
        backup = Path(REGISTRY_PATH).read_text()

    try:
        # clean slate
        if os.path.exists(REGISTRY_PATH):
            os.remove(REGISTRY_PATH)

        tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tf.close()
        path = tf.name
        name = os.path.splitext(os.path.basename(path))[0]

        err = add_external(path)
        _check(err is None, "add_external returns None")

        entries = list_external()
        _check(len(entries) == 1, "list_external has 1 entry")
        _check(entries[0]["name"] == name, "entry name matches")

        dead = list_dead()
        _check(len(dead) == 0, "no dead entries while file exists")

        os.remove(path)
        dead = list_dead()
        _check(len(dead) == 1, "dead entry after file removal")

        ok = remove_entry(name)
        _check(ok, "remove_entry returns True")
        _check(len(load_registry()) == 0, "registry empty after removal")

        # add duplicate
        tf2 = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tf2.close()
        err = add_external(tf2.name)
        _check(err is None, "add first time")
        err = add_external(tf2.name)
        _check(err is not None, "duplicate rejected")
        os.remove(tf2.name)

    finally:
        if backup is not None:
            Path(REGISTRY_PATH).write_text(backup)
        elif os.path.exists(REGISTRY_PATH):
            os.remove(REGISTRY_PATH)

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
def test_profiles():
    _section("Profiles")

    from profiles import list_profiles, get_profile, upsert_profile, delete_profile

    test_name = "_test_temp_profile"
    # ensure clean
    delete_profile(test_name)

    cfg = {
        "description": "test",
        "language": "en",
        "align": True,
        "diarize": False,
        "model": "tiny",
        "chunk_minutes": 0,
        "max_workers": 1,
        "clean_filter": "off",
    }
    upsert_profile(test_name, cfg)

    found = get_profile(test_name)
    _check(found is not None, "profile exists after upsert")
    _check(found["language"] == "en", "language matches")
    _check(found["clean_filter"] == "off", "clean_filter matches")

    all_names = [n for n, _ in list_profiles()]
    _check(test_name in all_names, "profile in list_profiles")

    ok = delete_profile(test_name)
    _check(ok, "delete_profile returns True")
    _check(get_profile(test_name) is None, "profile gone after delete")
    _check(delete_profile(test_name) is False, "delete nonexistent returns False")

# ---------------------------------------------------------------------------
# Model cache status
# ---------------------------------------------------------------------------
def test_model_cache_status():
    _section("Model cache status")

    from gui.app import _model_cache_status, _MODEL_SIZES

    for model, expected_size in _MODEL_SIZES.items():
        status = _model_cache_status(model)
        _check(isinstance(status, str) and len(status) > 0, f"status for {model}: {status}")

    uncached = _model_cache_status("nonexistent_model_xyz")
    _check(uncached.startswith("⚡"), "unknown model shows ⚡")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def test_config():
    _section("Config")

    from config import model_name_list, language_list, chunk_options

    _check(len(model_name_list) > 5, "model_name_list has entries")
    _check("uk" in language_list, "uk in language_list")
    _check("en" in language_list, "en in language_list")
    _check(0 in chunk_options, "0 in chunk_options")
    _check(all(isinstance(x, int) for x in chunk_options), "chunk_options are ints")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_heavy_imports():
    """Mock whisperx, torch, whisperx.diarize to allow importing whisper_offline."""
    mock_whisperx = mock.MagicMock()
    mock_whisperx.load_audio = mock.MagicMock()
    mock_whisperx.load_model = mock.MagicMock()
    mock_whisperx.load_align_model = mock.MagicMock()
    mock_whisperx.align = mock.MagicMock()
    mock_whisperx.assign_word_speakers = mock.MagicMock()

    mock_torch = mock.MagicMock()
    mock_torch.cuda.is_available.return_value = False

    mock_diarize = mock.MagicMock()
    mock_diarize.DiarizationPipeline = mock.MagicMock()

    sys.modules["whisperx"] = mock_whisperx
    sys.modules["torch"] = mock_torch
    sys.modules["whisperx.diarize"] = mock_diarize


# ---------------------------------------------------------------------------
# _model_cached (core transcription helper)
# ---------------------------------------------------------------------------
def test_model_cached_core():
    _section("_model_cached")

    # Mock heavy dependencies before importing whisper_offline
    _mock_heavy_imports()

    from whisper_offline import _model_cached

    # 1 — no cache files exist → False
    with mock.patch("os.path.isfile", return_value=False), \
         mock.patch("os.path.isdir", return_value=False):
        result = _model_cached("tiny")
        _check(result is False, "no cache returns False")

    # 2 — whisper .pt exists → True
    with mock.patch("os.path.isfile", return_value=True), \
         mock.patch("os.path.isdir", return_value=False):
        result = _model_cached("tiny")
        _check(result is True, "whisper .pt cache returns True")

    # 3 — huggingface hub dir exists (faster-whisper) → True
    with mock.patch("os.path.isfile", return_value=False), \
         mock.patch("os.path.isdir", return_value=True):
        result = _model_cached("tiny")
        _check(result is True, "hf hub faster-whisper returns True")

    # 4 — huggingface hub dir exists (distil) → True
    with mock.patch("os.path.isfile", return_value=False), \
         mock.patch("os.path.isdir", return_value=True):
        result = _model_cached("distil-large-v2")
        _check(result is True, "hf hub distil returns True")

    # 5 — returns bool for all known model sizes (no crash)
    for model in ["tiny", "base", "small", "medium", "large-v3", "turbo"]:
        r = _model_cached(model)
        _check(isinstance(r, bool), f"_model_cached('{model}') returns bool")


# ---------------------------------------------------------------------------
# _segments_to_text (output formatting)
# ---------------------------------------------------------------------------
def test_segments_to_text():
    _section("_segments_to_text")

    _mock_heavy_imports()
    from whisper_offline import WhisperTranscriber

    t = object.__new__(WhisperTranscriber)

    result = {
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " Hello ", "speaker": "SPEAKER_01"},
            {"start": 2.0, "end": 3.5, "text": "World", "speaker": "Unknown"},
            {"start": 5.0, "end": 6.0, "text": "Test without speaker"},
        ]
    }
    lines = t._segments_to_text(result)
    _check(len(lines) == 3, "3 lines for 3 segments")
    _check(lines[0] == "[  0.00-  1.50] SPEAKER_01: Hello", "line 0 format")
    _check(lines[1] == "[  2.00-  3.50] Unknown: World", "line 1 format")
    _check(lines[2] == "[  5.00-  6.00] Unknown: Test without speaker",
           "line 2 – missing speaker defaults to Unknown")

    # empty segments
    empty = {"segments": []}
    _check(t._segments_to_text(empty) == [], "empty segments list")


# ---------------------------------------------------------------------------
# TimingDB
# ---------------------------------------------------------------------------
def test_timing_db():
    _section("TimingDB")

    import timing
    from timing import TimingDB, CHUNK_DEFAULTS

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name
    Path(temp_path).write_text("{}")

    orig_path = timing.TIMINGS_PATH
    try:
        timing.TIMINGS_PATH = temp_path
        db = TimingDB()

        # get() returns defaults for untouched keys
        val = db.get("tiny", "cpu", "chunk")
        _check(val == CHUNK_DEFAULTS[("tiny", "cpu")],
               f"chunk default tiny/cpu = {val}")
        val = db.get("large-v3", "cpu", "align")
        _check(val == 60.0, f"align default large-v3/cpu = {val}")

        # update() stores running average
        db.update("tiny", "cpu", "chunk", 10.0)
        _check(db.get("tiny", "cpu", "chunk") == 10.0, "single update")
        db.update("tiny", "cpu", "chunk", 20.0)
        _check(db.get("tiny", "cpu", "chunk") == 15.0, "running avg (10+20)/2=15")

        # save() writes file
        db.save()
        raw = json.loads(Path(temp_path).read_text())
        _check("tiny_cpu" in raw, "key exists after save")
        _check(raw["tiny_cpu"]["chunk"] == 15.0, "saved running avg")

        # predict() with known params
        pred = db.predict("tiny", "cpu", audio_duration_sec=600,
                          chunk_minutes=10, do_align=True, do_diarize=False)
        _check(pred["n_chunks"] == 1, "600s/10min = 1 chunk")
        _check(pred["clean"] > 0, "clean time > 0")
        _check(pred["transcribe"] > 0, "transcribe time > 0")
        _check(pred["align"] > 0, "align time > 0")
        _check(pred["diarize"] == 0, "diarize = 0 when disabled")
        _check(pred["total"] == pred["clean"] + pred["transcribe"] + pred["align"],
               "total = clean + transcribe + align")

        # predict with multiple chunks
        pred2 = db.predict("tiny", "cpu", 1800, 10, False, False)
        _check(pred2["n_chunks"] == 3, "1800s/10min = 3 chunks")

        # predict without chunking
        pred3 = db.predict("tiny", "cpu", 300, 0, False, False)
        _check(pred3["n_chunks"] == 1, "chunk_minutes=0 → 1 chunk")

    finally:
        timing.TIMINGS_PATH = orig_path
        os.remove(temp_path)


# ---------------------------------------------------------------------------
# WorkDir
# ---------------------------------------------------------------------------
def test_workdir():
    _section("WorkDir")

    from workdir import WorkDir

    with tempfile.TemporaryDirectory() as tmp:
        # create work dir
        input_path = os.path.join(tmp, "test_audio.m4a")
        Path(input_path).touch()
        wd = WorkDir(input_path, base_dir=tmp)
        _check(os.path.isdir(wd.path), "workdir path created")
        _check(wd.session_id.startswith("test_audio_"), "session_id prefix")

        # find_existing returns it
        found = WorkDir.find_existing(input_path, base_dir=tmp)
        _check(found is not None, "find_existing finds created workdir")
        _check(found.session_id == wd.session_id, "same session_id")

        # save / load json
        data = {"segments": [{"start": 0.0, "end": 1.0}]}
        wd.save_json(data, "test.json")
        loaded = wd.load_json("test.json")
        _check(loaded == data, "load_json returns saved data")

        # load_json nonexistent → None
        _check(wd.load_json("nonexistent.json") is None, "load_json missing → None")

        # transcribed_chunk_keys
        keys = wd.transcribed_chunk_keys()
        _check(keys == set(), "no chunks yet → empty set")

        chunks_dir = wd.ensure_chunks_dir()
        _check(os.path.isdir(chunks_dir), "chunks dir created")

        transcribed_dir = os.path.join(wd.path, "transcribed")
        os.makedirs(transcribed_dir, exist_ok=True)

        wd.save_transcribed_chunk("chunk_0000", [{"seg": 1}])
        wd.save_transcribed_chunk("chunk_0001", [{"seg": 2}])
        keys = wd.transcribed_chunk_keys()
        _check(keys == {"chunk_0000", "chunk_0001"}, "transcribed_chunk_keys")

        # cleanup
        wd.cleanup()
        _check(not os.path.exists(wd.path), "workdir cleaned up")

    # find_existing with no base dir → None
    none_found = WorkDir.find_existing("/nonexistent/path/audio.m4a", base_dir=tmp)
    _check(none_found is None, "find_existing no match → None")


# ---------------------------------------------------------------------------
# dedup_segments
# ---------------------------------------------------------------------------
def test_dedup_segments():
    _section("dedup_segments")

    from split_audio import dedup_segments

    # empty
    _check(dedup_segments([], 5.0) == [], "empty input")

    # single segment
    s = [{"start": 0.0, "end": 10.0}]
    _check(dedup_segments(s, 5.0) == s, "single segment unchanged")

    # no overlap
    segs = [{"start": 0.0, "end": 5.0}, {"start": 10.0, "end": 15.0}]
    _check(dedup_segments(segs, 5.0) == segs, "no overlap → unchanged")

    # heavy overlap (>2.5s) → second dropped
    segs = [{"start": 0.0, "end": 10.0}, {"start": 2.0, "end": 12.0}]
    r = dedup_segments(segs, 5.0)
    _check(len(r) == 1, "heavy overlap → deduped to 1 segment")

    # small overlap (<2.5s) → start adjusted to prev end
    segs = [{"start": 0.0, "end": 10.0}, {"start": 9.0, "end": 15.0}]
    r = dedup_segments(segs, 5.0)
    _check(len(r) == 2, "small overlap → keeps both")
    _check(r[1]["start"] == 10.0, "second start adjusted to prev end")


# ---------------------------------------------------------------------------
# _format_size / _dir_size
# ---------------------------------------------------------------------------
def test_size_helpers():
    _section("_format_size / _dir_size")

    from gui.app import _format_size, _dir_size
    from gui.lang import _inst

    _inst.switch_to("uk")
    _check(_format_size(0) == "0.0 Б", "0 bytes")
    _check(_format_size(1023) == "1023.0 Б", "1023 bytes → Б")
    _check(_format_size(1024) == "1.0 КБ", "1024 bytes → 1.0 КБ")
    _check(_format_size(1536) == "1.5 КБ", "1536 bytes → 1.5 КБ")
    _check(_format_size(1024**2) == "1.0 МБ", "1 MiB → 1.0 МБ")
    _check(_format_size(1024**3) == "1.0 ГБ", "1 GiB → 1.0 ГБ")
    _check(_format_size(1024**4) == "1.0 ТБ", "1 TiB → 1.0 ТБ")

    # _dir_size
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "a.txt").write_text("hello")
        Path(tmp, "sub").mkdir()
        Path(tmp, "sub", "b.txt").write_text("world" * 100)
        sz = _dir_size(tmp)
        _check(sz > 0, "_dir_size returns positive value")
        _check(isinstance(sz, int), "_dir_size returns int")
        # verify it walks recursively
        _check(sz > 500, "_dir_size includes subdirectory files")


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------
def test_exception_classes():
    _section("Exception classes")

    _mock_heavy_imports()
    from whisper_offline import DownloadCancelledError, TranscriptionCancelledError

    # instantiate
    e1 = DownloadCancelledError("test")
    _check(str(e1) == "test", "DownloadCancelledError message")

    e2 = TranscriptionCancelledError("cancel")
    _check(str(e2) == "cancel", "TranscriptionCancelledError message")

    # catchable
    try:
        raise DownloadCancelledError("no download")
    except DownloadCancelledError:
        _check(True, "DownloadCancelledError catchable")

    try:
        raise TranscriptionCancelledError()
    except TranscriptionCancelledError:
        _check(True, "TranscriptionCancelledError catchable")


# ---------------------------------------------------------------------------
# Timing defaults consistency (extra safety)
# ---------------------------------------------------------------------------
def test_timing_defaults_consistency():
    _section("Timing defaults consistency")

    from timing import CHUNK_DEFAULTS, STAGE_DEFAULTS

    # every model that has cpu default should also have cuda
    cpu_models = {m for (m, d) in CHUNK_DEFAULTS if d == "cpu"}
    cuda_models = {m for (m, d) in CHUNK_DEFAULTS if d == "cuda"}
    _check(cpu_models == cuda_models,
           f"all cpu models also have cuda default: {cpu_models - cuda_models}")

    # all stage defaults have both cpu and cuda
    for stage, devices in STAGE_DEFAULTS.items():
        _check("cpu" in devices and "cuda" in devices,
               f"stage '{stage}' has cpu and cuda")

    # defaults are positive
    for (m, d), val in CHUNK_DEFAULTS.items():
        _check(val > 0, f"CHUNK_DEFAULTS[({m}, {d})] = {val} > 0")

    # chunk_minutes=0 always returns n_chunks=1 in predict
    from timing import TimingDB
    db = TimingDB()
    for duration in [0, 60, 600, 3600]:
        p = db.predict("tiny", "cpu", duration, 0, False, False)
        _check(p["n_chunks"] == 1, f"chunk_minutes=0 → 1 chunk for {duration}s")


# ---------------------------------------------------------------------------
# cpu_levels in config
# ---------------------------------------------------------------------------
def test_cpu_levels():
    _section("cpu_levels")

    from config import cpu_levels

    _check("high" in cpu_levels, "high in cpu_levels")
    _check("medium" in cpu_levels, "medium in cpu_levels")
    _check("low" in cpu_levels, "low in cpu_levels")
    _check(len(cpu_levels) == 3, "3 cpu levels")


# ---------------------------------------------------------------------------
# _apply_cpu_profile
# ---------------------------------------------------------------------------
def test_apply_cpu_profile():
    _section("_apply_cpu_profile")

    # Save original env state
    orig = {}
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
              "TORCH_NUM_THREADS"):
        orig[k] = os.environ.get(k)

    _mock_heavy_imports()
    from whisper_offline import _apply_cpu_profile

    ncpu = os.cpu_count() or 4

    try:
        # low — all env vars = 1, cap = 1
        cap = _apply_cpu_profile("low")
        _check(cap == 1, f"low cap = {cap}")
        _check(os.environ.get("OMP_NUM_THREADS") == "1", "low OMP=1")
        _check(os.environ.get("MKL_NUM_THREADS") == "1", "low MKL=1")
        _check(os.environ.get("OPENBLAS_NUM_THREADS") == "1", "low OPENBLAS=1")
        _check(os.environ.get("TORCH_NUM_THREADS") == "1", "low TORCH=1")

        # medium — half cpu count, cap = half
        half = max(2, ncpu // 2)
        cap = _apply_cpu_profile("medium")
        _check(cap == half, f"medium cap = {cap}")
        _check(os.environ.get("OMP_NUM_THREADS") == str(half), f"medium OMP={half}")
        _check(os.environ.get("MKL_NUM_THREADS") == str(half), f"medium MKL={half}")

        # high — all env vars cleared, cap = ncpu
        cap = _apply_cpu_profile("high")
        _check(cap == ncpu, f"high cap = {cap}")
        _check(os.environ.get("OMP_NUM_THREADS") is None, "high OMP cleared")
        _check(os.environ.get("MKL_NUM_THREADS") is None, "high MKL cleared")
        _check(os.environ.get("OPENBLAS_NUM_THREADS") is None, "high OPENBLAS cleared")
        _check(os.environ.get("TORCH_NUM_THREADS") is None, "high TORCH cleared")

        # does not crash when psutil unavailable
        cap = _apply_cpu_profile("low")
        _check(cap == 1, "low again cap = 1")

    finally:
        # Restore
        for k, v in orig.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# _check_resources (OOM + DISKOM)
# ---------------------------------------------------------------------------
def test_check_resources():
    _section("_check_resources")

    _mock_heavy_imports()
    from whisper_offline import _check_resources, MODEL_RESOURCE_MB

    mock_mem = mock.MagicMock()
    mock_disk = mock.MagicMock()

    # 1. Plenty of everything → no warnings, no errors
    mock_mem.available = 64 * 1024**3  # 64 GB
    mock_disk.free = 100 * 1024**3  # 100 GB

    with mock.patch("whisper_offline.psutil.virtual_memory", return_value=mock_mem), \
         mock.patch("whisper_offline.psutil.disk_usage", return_value=mock_disk), \
         mock.patch("whisper_offline._model_cached", return_value=True):
        w, e = _check_resources("tiny", True, True)
        _check(len(w) == 0, "plenty RAM+disk + cached → no warnings")
        _check(len(e) == 0, "plenty RAM+disk + cached → no errors")

    # 2. Very low RAM (< need_ram_mb) → warning with ⚠
    mock_mem.available = 200 * 1024**2  # 200 MB
    with mock.patch("whisper_offline.psutil.virtual_memory", return_value=mock_mem), \
         mock.patch("whisper_offline.psutil.disk_usage", return_value=mock_disk), \
         mock.patch("whisper_offline._model_cached", return_value=True):
        w, e = _check_resources("large-v3", True, True)
        _check(len(w) >= 1, "very low RAM → warning(s)")
        _check(any("⚠️" in x for x in w), "RAM warning has ⚠️")

    # 3. Moderate RAM (1×…2× need) → weaker warning
    need_mb = MODEL_RESOURCE_MB["large-v3"] + 300 + 200 + 200
    mock_mem.available = int(need_mb * 1.5 * 1024**2)
    with mock.patch("whisper_offline.psutil.virtual_memory", return_value=mock_mem), \
         mock.patch("whisper_offline.psutil.disk_usage", return_value=mock_disk), \
         mock.patch("whisper_offline._model_cached", return_value=True):
        w, e = _check_resources("large-v3", True, True)
        _check(len(w) >= 1, "moderate RAM → warning")

    # 4. Low disk + model not cached → error with ❌
    small_disk = mock.MagicMock()
    small_disk.free = 2 * 1024**3  # 2 GB
    mock_mem.available = 64 * 1024**3
    with mock.patch("whisper_offline.psutil.virtual_memory", return_value=mock_mem), \
         mock.patch("whisper_offline.psutil.disk_usage", return_value=small_disk), \
         mock.patch("whisper_offline._model_cached", return_value=False):
        w, e = _check_resources("large-v3", False, False)
        _check(len(e) >= 1, "low disk + not cached → error(s)")
        _check(any("❌" in x for x in e), "disk error has ❌")

    # 5. Low disk but model cached → no error
    with mock.patch("whisper_offline.psutil.virtual_memory", return_value=mock_mem), \
         mock.patch("whisper_offline.psutil.disk_usage", return_value=small_disk), \
         mock.patch("whisper_offline._model_cached", return_value=True):
        w, e = _check_resources("large-v3", False, False)
        _check(len(e) == 0, "low disk but cached → no errors")

    # 6. MODEL_RESOURCE_MB completeness vs config
    from config import model_name_list
    for m in model_name_list:
        _check(m in MODEL_RESOURCE_MB, f"MODEL_RESOURCE_MB has '{m}'")


# ---------------------------------------------------------------------------
# _check_output_disk
# ---------------------------------------------------------------------------
def test_check_output_disk():
    _section("_check_output_disk")

    _mock_heavy_imports()
    from whisper_offline import _check_output_disk

    # 1. psutil not available → no warnings
    with mock.patch("whisper_offline.psutil", None):
        w = _check_output_disk("/tmp", "/nonexistent/test.m4a")
        _check(len(w) == 0, "no psutil → no warnings")

    # 2. Plenty of disk → no warnings
    mock_disk = mock.MagicMock()
    mock_disk.free = 100 * 1024**3  # 100 GB
    with mock.patch("whisper_offline.psutil.disk_usage", return_value=mock_disk), \
         mock.patch("os.path.getsize", return_value=50 * 1024**2):  # 50 MB file
        w = _check_output_disk("/tmp", "test.m4a")
        _check(len(w) == 0, "100 GB free + 50 MB file → no warning")

    # 3. Low disk → warning
    small_disk = mock.MagicMock()
    small_disk.free = 200 * 1024**2  # 200 MB
    with mock.patch("whisper_offline.psutil.disk_usage", return_value=small_disk), \
         mock.patch("os.path.getsize", return_value=100 * 1024**2):  # 100 MB file (est. 1 GB)
        w = _check_output_disk("/tmp", "test.m4a")
        _check(len(w) >= 1, "200 MB free + 100 MB m4a → warning")
        _check(any("⚠️" in x for x in w), "disk warning has ⚠️")

    # 4. WAV file → expansion 1×
    with mock.patch("whisper_offline.psutil.disk_usage", return_value=small_disk), \
         mock.patch("os.path.getsize", return_value=700 * 1024**2):  # 700 MB wav
        w = _check_output_disk("/tmp", "test.wav")
        _check(len(w) >= 1, "wav expansion 1×")
        _check(any("×1" in x for x in w), "wav shows ×1 estimate")

    # 5. Tiny compressed file → min 500 MB estimate
    with mock.patch("whisper_offline.psutil.disk_usage", return_value=small_disk), \
         mock.patch("os.path.getsize", return_value=10 * 1024**2):  # 10 MB
        w = _check_output_disk("/tmp", "test.m4a")
        _check(len(w) >= 1, "10 MB m4a → min 500 MB estimate")
        _check(any("500" in x for x in w), "warning mentions 500 MB floor")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_registry()
    test_profiles()
    test_model_cache_status()
    test_config()
    test_model_cached_core()
    test_segments_to_text()
    test_timing_db()
    test_workdir()
    test_dedup_segments()
    test_size_helpers()
    test_exception_classes()
    test_timing_defaults_consistency()
    test_cpu_levels()
    test_apply_cpu_profile()
    test_check_resources()
    test_check_output_disk()

    total = _PASSED + _FAILED
    print(f"\n{'='*40}")
    print(f"  PASSED: {_PASSED}/{total}")
    print(f"  FAILED: {_FAILED}/{total}")
    sys.exit(0 if _FAILED == 0 else 1)
