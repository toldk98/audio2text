import argparse
import os
import sys
import shutil
import time
from dotenv import load_dotenv

from config import model_name_list, chunk_options
from whisper_offline import WhisperTranscriber, DownloadCancelledError
from whisper_realtime import WhisperRealtimeTranscriber
from workdirs import WorkDirs

load_dotenv()

_WHISPER_CACHE = WorkDirs().whisper_cache
_HF_CACHE = WorkDirs().hf_hub

_PROFILE_KEYS = {
    "model": "model_name",
    "language": "language",
    "align": "align",
    "diarize": "diarize",
    "clean_filter": "clean_filter",
    "cpu_profile": "cpu_profile",
    "chunk_minutes": "chunk_minutes",
    "max_workers": "max_workers",
}


def build_parser():
    chunk_help = f"Розбити файл на частини по N хв для паралельної обробки (0 = вимкнено). Доступно: {chunk_options}"
    parser = argparse.ArgumentParser(
        description="WhisperX Transcriber — офлайн та реальний час (мікрофон + динаміки)"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["file", "realtime", "pick"],
        help="Режим роботи: 'file' — з файлу, 'realtime' — у реальному часі, 'pick' — інтерактивний вибір",
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Назва або ID пристрою (для режиму 'realtime')",
    )
    parser.add_argument(
        "--model_name",
        choices=model_name_list,
        default=None,
        help="Розмір моделі WhisX",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=None,
        help="Мова транскрипції",
    )
    parser.add_argument(
        "--out_file",
        type=str,
        default=None,
        help="Вихідний файл (для file — .txt, для realtime — .wav)",
    )
    parser.add_argument(
        "--chunk_minutes",
        type=int,
        default=None,
        choices=chunk_options,
        help=chunk_help,
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=None,
        help="Кількість паралельних потоків для обробки чанків",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Автоматично підтверджувати завантаження моделей (без запиту)",
    )
    parser.add_argument(
        "--align",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Вирівнювання через wav2vec2 (--no-align щоб вимкнути)",
    )
    parser.add_argument(
        "--diarize",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Діаризація через pyannote (--no-diarize щоб вимкнути)",
    )
    parser.add_argument(
        "--clean_filter",
        choices=["full", "light", "off"],
        default=None,
        help="Рівень фільтрації аудіо (full — ffmpeg, light — легка, off — без)",
    )
    parser.add_argument(
        "--cpu_profile",
        choices=["high", "medium", "low"],
        default=None,
        help="Рівень завантаження CPU (high — всі ядра, medium — половина, low — чверть)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Ім'я профілю транскрипції (заповнює інші параметри)",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Показувати прогрес у вигляді шкали",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Показати всі кешовані моделі та вийти",
    )
    parser.add_argument(
        "--delete-model",
        type=str,
        default=None,
        help="Видалити модель з кешу та вийти",
    )
    return parser


def _list_cached_models():
    entries = []
    if os.path.isdir(_WHISPER_CACHE):
        for fname in os.listdir(_WHISPER_CACHE):
            fpath = os.path.join(_WHISPER_CACHE, fname)
            if fname.endswith(".pt") and os.path.isfile(fpath):
                sz = os.path.getsize(fpath)
                name = fname.removesuffix(".pt")
                entries.append({"name": name, "type": "Whisper", "size": sz})

    if os.path.isdir(_HF_CACHE):
        for entry in sorted(os.listdir(_HF_CACHE)):
            if not entry.startswith("models--"):
                continue
            parts = entry.split("--")
            name = "/".join(parts[1:])
            fpath = os.path.join(_HF_CACHE, entry)
            if not os.path.isdir(fpath):
                continue
            sz = _dir_size(fpath)
            entries.append({"name": name, "type": "HF Hub", "size": sz})
    return entries


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


def _delete_model(model_name: str) -> bool:
    removed = False

    pt = os.path.join(_WHISPER_CACHE, f"{model_name}.pt")
    if os.path.isfile(pt):
        os.remove(pt)
        print(f"  ✖ Видалено: {pt}")
        removed = True

    for prefix, suffix in [
        ("models--Systran--faster-whisper-", ""),
        ("models--Systran--faster-distil-whisper-", ""),
    ]:
        dir_name = prefix + model_name + suffix
        d = os.path.join(_HF_CACHE, dir_name)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            print(f"  ✖ Видалено: {d}")
            removed = True

    return removed


def _progress_callback(completed: int, total: int, remaining: float):
    bar_len = 20
    filled = int(bar_len * completed / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  Прогрес: [{bar}] {completed}/{total}  ETA ~{remaining:.0f} с", end="", flush=True)
    if completed == total:
        print()


def _apply_profile(args, profile_name: str):
    from profiles import get_profile
    cfg = get_profile(profile_name)
    if not cfg:
        print(f"❌ Профіль '{profile_name}' не знайдено")
        sys.exit(1)

    for prof_key, arg_key in _PROFILE_KEYS.items():
        if prof_key == "model":
            if getattr(args, arg_key) is None:
                setattr(args, arg_key, cfg.get("model"))
        elif prof_key in ("align", "diarize"):
            if getattr(args, arg_key) is None:
                setattr(args, arg_key, cfg.get(prof_key, True))
        else:
            if getattr(args, arg_key) is None:
                setattr(args, arg_key, cfg.get(prof_key))

    if args.language is None:
        args.language = "uk"
    if args.model_name is None:
        args.model_name = cfg.get("model", "large-v3")
    if args.chunk_minutes is None:
        args.chunk_minutes = cfg.get("chunk_minutes", 0)
    if args.max_workers is None:
        args.max_workers = cfg.get("max_workers", 2)
    if args.clean_filter is None:
        args.clean_filter = cfg.get("clean_filter", "full")
    if args.cpu_profile is None:
        args.cpu_profile = cfg.get("cpu_profile", "high")
    if args.align is None:
        args.align = cfg.get("align", True)
    if args.diarize is None:
        args.diarize = cfg.get("diarize", True)

    print(f"ℹ Профіль '{profile_name}': {cfg.get('description', '')}")
    return args


def _fill_defaults(args):
    if args.language is None:
        args.language = "uk"
    if args.model_name is None:
        args.model_name = "large-v3"
    if args.chunk_minutes is None:
        args.chunk_minutes = 0
    if args.max_workers is None:
        args.max_workers = 2
    if args.clean_filter is None:
        args.clean_filter = "full"
    if args.cpu_profile is None:
        args.cpu_profile = "high"
    if args.align is None:
        args.align = True
    if args.diarize is None:
        args.diarize = True
    return args


def run_cli():
    parser = build_parser()
    args, remaining = parser.parse_known_args()

    if args.list_models:
        entries = _list_cached_models()
        if not entries:
            print("Немає кешованих моделей.")
            return
        total = 0
        print(f"{'Назва':40s} {'Тип':10s} {'Розмір':>10s}")
        print("-" * 62)
        for e in sorted(entries, key=lambda x: x["name"]):
            sz_str = _format_size(e["size"])
            print(f"{e['name']:40s} {e['type']:10s} {sz_str:>10s}")
            total += e["size"]
        print("-" * 62)
        print(f"{'Всього':40s} {'':10s} {_format_size(total):>10s}")
        return

    if args.delete_model:
        if _delete_model(args.delete_model):
            print(f"✅ Модель '{args.delete_model}' видалено з кешу.")
        else:
            print(f"⚠ Модель '{args.delete_model}' не знайдено в кеші.")
        return

    from logger import check_ffmpeg
    if not check_ffmpeg():
        print("❌ ffmpeg не знайдено. Встановіть ffmpeg для коректної роботи.")
        sys.exit(1)

    if args.mode is None:
        parser.print_help()
        sys.exit(1)

    if args.profile:
        args = _apply_profile(args, args.profile)
    else:
        args = _fill_defaults(args)

    if args.mode == "pick":
        from pick import run_pick
        run_pick()
        return

    try:
        if args.mode == "file":
            input_path = remaining[0] if remaining else None
            if not input_path:
                print("❌ Не вказано шлях до файлу.\n"
                      "Використання: python transcriber.py file <шлях_до_файлу>")
                sys.exit(1)

            from gui.token_manager import load_token
            hf_token, token_source = load_token()
            if not hf_token:
                print("❌ HF_TOKEN не знайдено. Встановіть змінну середовища "
                      "або збережіть токен через keyring (GUI).")
                sys.exit(1)

            from whisper_offline import _model_cached
            if not args.yes and not _model_cached(args.model_name):
                print(f"\n⚠️ Модель '{args.model_name}' не знайдено в кеші.")
                print("   Завантажити? [y/N]: ", end="", flush=True)
                try:
                    resp = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    resp = "n"
                if resp not in ("y", "yes"):
                    print("❌ Скасовано.")
                    sys.exit(0)

            cb = _progress_callback if args.progress else None
            transcriber = WhisperTranscriber(
                hf_token=hf_token,
                model_size=args.model_name,
                language=args.language,
                do_align=args.align,
                do_diarize=args.diarize,
                clean_filter=args.clean_filter,
                cpu_profile=args.cpu_profile,
                chunk_minutes=args.chunk_minutes,
                max_workers=args.max_workers,
                allow_download=args.yes,
                progress_callback=cb,
            )
            transcriber.transcribe(input_path, output_txt=args.out_file)

        elif args.mode == "realtime":
            realtime_transcriber = WhisperRealtimeTranscriber(
                model_size=args.model_name,
                language=args.language,
                save_audio=True,
                out_file=args.out_file or "session_record.wav",
                record_both=True,
                mic_device=args.device,
                spk_device=args.device,
            )
            realtime_transcriber.start()

        else:
            print("❌ Невідомий режим. Використай 'file', 'realtime' або 'pick'.")
    except DownloadCancelledError:
        sys.exit(0)
