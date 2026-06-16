import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

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
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_registry()
    test_profiles()
    test_model_cache_status()
    test_config()

    total = _PASSED + _FAILED
    print(f"\n{'='*40}")
    print(f"  PASSED: {_PASSED}/{total}")
    print(f"  FAILED: {_FAILED}/{total}")
    sys.exit(0 if _FAILED == 0 else 1)
