import argparse
import os
import sys
from dotenv import load_dotenv

from config import model_name_list, chunk_options
from whisper_offline import WhisperTranscriber, DownloadCancelledError
from whisper_realtime import WhisperRealtimeTranscriber

load_dotenv()


def build_parser():
    chunk_help = f"Розбити файл на частини по N хв для паралельної обробки (0 = вимкнено). Доступно: {chunk_options}"
    parser = argparse.ArgumentParser(
        description="WhisperX Transcriber — офлайн та реальний час (мікрофон + динаміки)"
    )
    parser.add_argument(
        "mode",
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
        default="large-v3",
        help="Розмір моделі WhisX",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="uk",
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
        default=0,
        choices=chunk_options,
        help=chunk_help,
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=2,
        help="Кількість паралельних потоків для обробки чанків",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Автоматично підтверджувати завантаження моделей (без запиту)",
    )
    return parser


def run_cli():
    parser = build_parser()
    args, remaining = parser.parse_known_args()

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

            hf_token = os.getenv("HF_TOKEN")
            if not hf_token:
                print("❌ HF_TOKEN не знайдено в .env")
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

            transcriber = WhisperTranscriber(
                hf_token=hf_token,
                model_size=args.model_name,
                language=args.language,
                chunk_minutes=args.chunk_minutes,
                max_workers=args.max_workers,
                allow_download=args.yes,
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
