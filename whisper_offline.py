import os
import subprocess
import sys
import threading
import time
import whisperx
import torch
from concurrent.futures import ThreadPoolExecutor, as_completed
from whisperx.diarize import DiarizationPipeline
from split_audio import split_audio, dedup_segments, _get_duration
from logger import get_logger
from timing import TimingDB
from workdir import WorkDir
from config import WHISPER_CACHE_DIR, HF_HUB_DIR

logger = get_logger(__name__)

try:
    import psutil
except ImportError:
    psutil = None

MODEL_RESOURCE_MB = {
    "tiny": 150, "base": 300, "small": 500,
    "medium": 1500, "large-v1": 3000, "large-v2": 3000,
    "large-v3": 3000, "large": 3000,
    "distil-large-v2": 1500, "distil-large-v3": 1500,
    "distil-large-v3.5": 1500,
    "large-v3-turbo": 3000, "turbo": 3000,
}


def _check_resources(model_size: str, do_align: bool, do_diarize: bool) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []

    if psutil is None:
        return warnings, errors

    need_mb = MODEL_RESOURCE_MB.get(model_size, 1000)

    # 1. RAM (warnings only, never blocks)
    free_mb = psutil.virtual_memory().available / 1024 / 1024
    need_ram_mb = need_mb + (300 if do_align else 0) + (200 if do_diarize else 0) + 200
    if free_mb < need_ram_mb:
        warnings.append(
            f"⚠️ Вільно лише {free_mb:.0f} MB RAM, а модель + сервіси потребують ~{need_ram_mb} MB.\n"
            f"   Рекомендується ≥{need_ram_mb * 2:.0f} MB. Можливий OOM."
        )
    elif free_mb < need_ram_mb * 2:
        warnings.append(
            f"⚠️ Вільно {free_mb:.0f} MB RAM (потрібно ~{need_ram_mb} MB).\n"
            f"   Рекомендується ≥{need_ram_mb * 2:.0f} MB."
        )

    # 2. Disk for model download (error — blocks if not cached AND full)
    if not _model_cached(model_size):
        candidates = [HF_HUB_DIR, WHISPER_CACHE_DIR, os.path.expanduser("~")]
        cache_dir = next((d for d in candidates if os.path.exists(d)),
                         os.path.expanduser("~"))
        free_disk_mb = psutil.disk_usage(cache_dir).free / 1024 / 1024
        need_disk_mb = need_mb * 3
        if free_disk_mb < need_disk_mb:
            errors.append(
                f"❌ На диску «{cache_dir}» лише {free_disk_mb:.0f} MB вільно.\n"
                f"   Для завантаження моделі «{model_size}» потрібно ≥{need_disk_mb:.0f} MB ({need_mb} MB × 3).\n"
                f"   Завантаження заблоковано — ризик втрати даних."
            )

    return warnings, errors


def _check_output_disk(work_dir_path: str, input_path: str) -> list[str]:
    warnings: list[str] = []
    if psutil is None:
        return warnings
    try:
        free_mb = psutil.disk_usage(work_dir_path).free / 1024 / 1024
        input_mb = os.path.getsize(input_path) / 1024 / 1024
    except OSError:
        return warnings

    ext = os.path.splitext(input_path)[1].lower()
    expansion = 1 if ext == ".wav" else 10
    estimated_mb = max(input_mb * expansion, 500)

    if free_mb < estimated_mb:
        warnings.append(
            f"⚠️ На диску «{work_dir_path}» лише {free_mb:.0f} MB вільно.\n"
            f"   Для обробки потрібно ~{estimated_mb:.0f} MB"
            f" (вхідний ×{expansion}{' — стиснений формат' if expansion > 1 else ''}).\n"
            f"   Рекомендується ≥{estimated_mb * 2:.0f} MB."
        )
    return warnings


def _apply_cpu_profile(level: str) -> int | None:
    os.environ.pop("OMP_NUM_THREADS", None)
    os.environ.pop("MKL_NUM_THREADS", None)
    os.environ.pop("OPENBLAS_NUM_THREADS", None)
    os.environ.pop("TORCH_NUM_THREADS", None)

    ncpu = os.cpu_count() or 4

    if level == "low":
        n_threads = 1
        os.environ["OMP_NUM_THREADS"] = "1"
        os.environ["MKL_NUM_THREADS"] = "1"
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
        os.environ["TORCH_NUM_THREADS"] = "1"
        try:
            import psutil
            psutil.Process().nice(19)
        except Exception:
            pass

    elif level == "medium":
        n_threads = max(2, ncpu // 2)
        os.environ["OMP_NUM_THREADS"] = str(n_threads)
        os.environ["MKL_NUM_THREADS"] = str(n_threads)
        os.environ["OPENBLAS_NUM_THREADS"] = str(n_threads)
        os.environ["TORCH_NUM_THREADS"] = str(n_threads)
        try:
            import psutil
            psutil.Process().nice(10)
        except Exception:
            pass

    else:
        n_threads = ncpu

    logger.info(f"[INFO] CPU профіль: {level} ({os.environ.get('OMP_NUM_THREADS', 'всі')} потоків)")
    return n_threads


class DownloadCancelledError(Exception):
    pass


class TranscriptionCancelledError(Exception):
    pass


def _model_cached(model_size: str) -> bool:
    if os.path.isfile(os.path.join(WHISPER_CACHE_DIR, f"{model_size}.pt")):
        return True

    hf_dir = HF_HUB_DIR
    # Non-distil models: faster-whisper-{model_size}
    nd = os.path.join(hf_dir, f"models--Systran--faster-whisper-{model_size}")
    if os.path.isdir(nd):
        return True
    # Distil models: faster-distil-whisper-{model_size} (strip distil- prefix)
    if model_size.startswith("distil-"):
        d = os.path.join(hf_dir, f"models--Systran--faster-distil-whisper-{model_size[7:]}")
        if os.path.isdir(d):
            return True

    return False


def _confirm_download(model_size: str, do_align: bool, do_diarize: bool, allow_download: bool = True):
    if _model_cached(model_size):
        return

    sizes = {
        "tiny": "~150 MB", "base": "~300 MB", "small": "~500 MB",
        "medium": "~1.5 GB", "large-v1": "~3 GB", "large-v2": "~3 GB",
        "large-v3": "~3 GB", "large": "~3 GB",
        "distil-large-v2": "~1.5 GB", "distil-large-v3": "~1.5 GB",
        "distil-large-v3.5": "~1.5 GB",
        "large-v3-turbo": "~3 GB", "turbo": "~3 GB",
    }
    size_str = sizes.get(model_size, "~1 GB")

    logger.warning(f"\n⚠️ Модель '{model_size}' ({size_str}) не знайдено в кеші.")
    logger.info(f"   Потрібно завантажити {size_str} з інтернету (одноразово).")
    if do_align:
        logger.info(f"   Додатково: align модель (~300 MB) при першому використанні.")
    if do_diarize:
        logger.info(f"   Додатково: діаризаційна модель (~200 MB) при першому використанні.")

    if not allow_download:
        raise DownloadCancelledError(f"Завантаження моделі '{model_size}' скасовано — 'allow_download=False'")

    logger.info(f"   Завантаження...")


class WhisperTranscriber:
    def __init__(
            self,
            hf_token: str,
            model_size: str = "base",
            language: str = "uk",
            do_align: bool = True,
            do_diarize: bool = True,
            chunk_minutes: int = 0,
            max_workers: int = 2,
            allow_download: bool = True,
            clean_filter: str = "full",
            cpu_profile: str = "high",
            stop_event: threading.Event | None = None,
            progress_callback=None,
    ):
        self.hf_token = hf_token
        self.model_size = model_size
        self.language = language
        self.do_align = do_align
        self.do_diarize = do_diarize
        self.chunk_minutes = chunk_minutes
        self.max_workers = max_workers
        self.allow_download = allow_download
        self.clean_filter = clean_filter
        self.cpu_profile = cpu_profile
        self.stop_event = stop_event or threading.Event()
        self.progress_callback = progress_callback

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.timing = TimingDB()
        self.time_process = time.time()

        logger.info(f"[INFO] Ініціалізація WhisperTranscriber...")
        logger.info(f"[INFO] Пристрій: {self.device}, режим обчислень: {self.compute_type}")

        cpu_max_workers = _apply_cpu_profile(self.cpu_profile)
        if self.max_workers > cpu_max_workers:
            logger.info(
                f"[INFO] max_workers знижено {self.max_workers} → {cpu_max_workers}"
                f" (CPU профіль: {self.cpu_profile})"
            )
            self.max_workers = cpu_max_workers

        warnings, errors = _check_resources(
            self.model_size, self.do_align, self.do_diarize
        )
        for w in warnings:
            logger.warning(w)
        if errors:
            for e in errors:
                logger.error(e)
            raise DownloadCancelledError("\n".join(errors))

        _confirm_download(self.model_size, self.do_align, self.do_diarize, self.allow_download)

        self.model = whisperx.load_model(
            self.model_size,
            device=self.device,
            language=self.language,
            compute_type=self.compute_type,
        )
        logger.info(self._elapsed("Ініціалізація моделі завершена"))

    def _elapsed(self, message: str) -> str:
        elapsed = time.time() - self.time_process
        return f"[TIME] {message}: {elapsed:.2f} с"

    def _clean_audio(self, input_audio: str) -> str:
        clean_path = self.work_dir.cleaned_audio

        if os.path.exists(clean_path):
            logger.info(f"[INFO] Використовується кешований cleaned: {clean_path}")
            return clean_path

        if self.clean_filter == "off":
            logger.info(f"[INFO] Очищення аудіо вимкнено.")
            return input_audio

        filter_names = {"full": "afftdn,loudnorm", "light": "highpass=f=200,lowpass=f=3000"}
        af = filter_names.get(self.clean_filter, "afftdn,loudnorm")
        logger.info(f"[INFO] Очищення аудіо через ffmpeg ({af})...")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_audio,
            "-ar", "16000",
            "-ac", "1",
            "-af", af,
            clean_path,
        ]

        try:
            subprocess.run(
                ffmpeg_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"[INFO] Створено очищений файл: {clean_path}")
            return clean_path
        except subprocess.CalledProcessError as e:
            logger.warning("[WARN] ffmpeg завершився з помилкою, використовується оригінальний файл.")
            logger.warning(e.stderr.decode("utf-8", errors="ignore"))
            return input_audio

    def _segments_to_text(self, result: dict) -> list[str]:
        lines = []
        for seg in result["segments"]:
            start = seg["start"]
            end = seg["end"]
            spk = seg.get("speaker", "Unknown")
            txt = seg["text"].strip()
            lines.append(f"[{start:6.2f}-{end:6.2f}] {spk}: {txt}")
        return lines

    def _write_result(self, result: dict, output_txt: str):
        lines = self._segments_to_text(result)
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _align_and_diarize(self, audio, segments, output_txt):
        result = None

        if self.do_align:
            logger.info(f"[INFO] Вирівнювання тексту...")
            t1 = time.time()
            model_a, metadata = whisperx.load_align_model(
                language_code=self.language, device=self.device
            )
            result = whisperx.align(segments, model_a, metadata, audio, self.device)
            align_elapsed = time.time() - t1
            self.timing.update(self.model_size, self.device, "align", align_elapsed)
            logger.info(f"[TIME] Вирівнювання: {align_elapsed:.2f} с")
        else:
            result = {"segments": segments}

        if self.do_diarize:
            if self.stop_event.is_set():
                raise TranscriptionCancelledError()
            logger.info(f"[INFO] Виконується діаризація...")
            t2 = time.time()
            diarize_model = DiarizationPipeline(
                use_auth_token=self.hf_token, device=self.device
            )
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)
            diarize_elapsed = time.time() - t2
            self.timing.update(self.model_size, self.device, "diarize", diarize_elapsed)
            logger.info(f"[TIME] Діаризація: {diarize_elapsed:.2f} с")

        self._write_result(result, output_txt)
        logger.info(f"[DONE] Текст збережено у: {output_txt}")
        return result

    def _transcribe_chunk(self, chunk_path: str, start_time: float) -> list[dict]:
        audio = whisperx.load_audio(chunk_path)
        result = self.model.transcribe(audio)
        for seg in result["segments"]:
            seg["start"] += start_time
            seg["end"] += start_time
        return result["segments"]

    def _load_or_transcribe_chunks(self, chunks: list[tuple[str, float]]) -> list[dict]:
        done_keys = self.work_dir.transcribed_chunk_keys()
        all_segments = []

        for path, start in chunks:
            key = os.path.splitext(os.path.basename(path))[0]
            if key in done_keys:
                cached = self.work_dir.load_json(f"transcribed/{key}.json")
                if cached:
                    all_segments.extend(cached)

        new_chunks = [
            (p, s) for p, s in chunks
            if os.path.splitext(os.path.basename(p))[0] not in done_keys
        ]

        if new_chunks:
            n_resume = len(chunks) - len(new_chunks)
            if n_resume > 0:
                logger.info(f"[INFO] Resume: {n_resume}/{len(chunks)} чанків уже транскрибовано")
            logger.info(f"[INFO] Транскрибується {len(new_chunks)} чанків...")

            t_start = time.time()
            completed = 0
            chunk_times = []

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                fut_map = {executor.submit(self._transcribe_chunk, p, s): (p, s) for p, s in new_chunks}
                for fut in as_completed(fut_map):
                    if self.stop_event.is_set():
                        logger.info(f"[INFO] Скасовано: оброблено {completed}/{len(new_chunks)} чанків")
                        break
                    p, s = fut_map[fut]
                    t_chunk = time.time()
                    segs = fut.result()
                    chunk_times.append(time.time() - t_chunk)
                    key = os.path.splitext(os.path.basename(p))[0]
                    self.work_dir.save_transcribed_chunk(key, segs)
                    all_segments.extend(segs)
                    completed += 1
                    if completed % 2 == 0 or completed == len(new_chunks):
                        avg = sum(chunk_times) / len(chunk_times)
                        remaining = avg * (len(new_chunks) - completed)
                        logger.info(f"[ETA] Чанк {completed}/{len(new_chunks)} · залишилось ~{remaining:.0f} с")
                        if self.progress_callback:
                            self.progress_callback(completed, len(new_chunks), remaining)

            if chunk_times:
                avg_chunk = sum(chunk_times) / len(chunk_times)
                self.timing.update(self.model_size, self.device, "chunk", avg_chunk)

        return all_segments

    def transcribe_chunked(self, input_audio: str, output_txt: str = None):
        if not os.path.exists(input_audio):
            raise FileNotFoundError(f"Файл '{input_audio}' не знайдено")

        self._original_path = input_audio
        existing = WorkDir.find_existing(input_audio)
        if existing:
            logger.info(f"[INFO] Resume: знайдено робочу директорію {existing.session_id}")
            self.work_dir = existing
        else:
            self.work_dir = WorkDir(input_audio)
        start_total = time.time()

        try:
            logger.info(f"[INFO] Обробка файлу: {input_audio}")

            for w in _check_output_disk(self.work_dir.path, input_audio):
                logger.warning(w)

            t_stage = time.time()
            cleaned = self._clean_audio(input_audio)
            clean_elapsed = time.time() - t_stage
            self.timing.update(self.model_size, self.device, "clean", clean_elapsed)
            logger.info(self._elapsed("Очищення аудіо завершено"))

            if self.stop_event.is_set():
                raise TranscriptionCancelledError()

            chunk_sec = self.chunk_minutes * 60
            chunks = split_audio(cleaned, chunk_sec=chunk_sec, overlap_sec=5,
                                 output_dir=self.work_dir.ensure_chunks_dir())
            logger.info(f"[INFO] Розбито на {len(chunks)} частин по {self.chunk_minutes} хв")

            if self.work_dir.merged_exists:
                merged = self.work_dir.load_json("merged.json")
                logger.info(f"[INFO] Resume: завантажено merged.json ({len(merged)} сегментів)")
            else:
                n_total = len(chunks)
                duration_est = n_total * self.chunk_minutes * 60
                pred = self.timing.predict(
                    self.model_size, self.device, duration_est,
                    self.chunk_minutes, self.do_align, self.do_diarize
                )
                logger.info(f"[INFO] Прогнозований час транскрипції: ~{pred['total']/60:.0f} хв ({n_total} чанків)")

                t0 = time.time()
                all_segments = self._load_or_transcribe_chunks(chunks)
                all_segments.sort(key=lambda s: s["start"])
                merged = dedup_segments(all_segments, overlap_sec=5.0)
                self.work_dir.save_json(merged, "merged.json")
                logger.info(f"[TIME] Транскрипція + зведення: {time.time() - t0:.2f} с")
                logger.info(f"[INFO] Сегментів після зведення: {len(merged)}")

            if not output_txt:
                base_path = os.path.splitext(self._original_path)[0]
                output_txt = f"{base_path}_transcribed.txt"

            if self.work_dir.aligned_exists:
                result = self.work_dir.load_json("aligned.json")
                logger.info(f"[INFO] Resume: завантажено aligned.json")
                self._write_result(result, output_txt)
            else:
                if self.stop_event.is_set():
                    raise TranscriptionCancelledError()

                t_load = time.time()
                audio = whisperx.load_audio(cleaned)
                logger.info(f"[TIME] Завантаження аудіо: {time.time() - t_load:.2f} с")

                result = self._align_and_diarize(audio, merged, output_txt)
                self.work_dir.save_json(result, "aligned.json")

            total_time = time.time() - start_total
            logger.info(f"[DONE] Загальний час обробки: {total_time / 60:.1f} хв ({total_time:.1f} с)")
            self.work_dir.cleanup()
            logger.info(self._elapsed("Обробку завершено"))
            return output_txt
        except Exception:
            logger.info(f"[INFO] Робоча директорія збережена: {self.work_dir.path}")
            raise

    def transcribe(self, input_audio: str, output_txt: str = None):
        if self.chunk_minutes > 0:
            return self.transcribe_chunked(input_audio, output_txt)

        if not os.path.exists(input_audio):
            raise FileNotFoundError(f"Файл '{input_audio}' не знайдено")

        self._original_path = input_audio
        existing = WorkDir.find_existing(input_audio)
        if existing:
            logger.info(f"[INFO] Resume: знайдено робочу директорію {existing.session_id}")
            self.work_dir = existing
        else:
            self.work_dir = WorkDir(input_audio)
        start_total = time.time()

        try:
            logger.info(f"[INFO] Обробка файлу: {input_audio}")

            for w in _check_output_disk(self.work_dir.path, input_audio):
                logger.warning(w)

            t_stage = time.time()
            cleaned = self._clean_audio(input_audio)
            clean_elapsed = time.time() - t_stage
            self.timing.update(self.model_size, self.device, "clean", clean_elapsed)
            logger.info(self._elapsed("Очищення аудіо завершено"))

            if self.stop_event.is_set():
                raise TranscriptionCancelledError()

            if not output_txt:
                base_path = os.path.splitext(self._original_path)[0]
                output_txt = f"{base_path}_transcribed.txt"

            if self.work_dir.aligned_exists:
                result = self.work_dir.load_json("aligned.json")
                logger.info(f"[INFO] Resume: завантажено aligned.json")
                self._write_result(result, output_txt)
            else:
                duration = _get_duration(cleaned) or 0
                pred = self.timing.predict(
                    self.model_size, self.device, duration,
                    0, self.do_align, self.do_diarize
                )
                logger.info(f"[INFO] Прогнозований час транскрипції: ~{pred['total']/60:.0f} хв")

                logger.info(f"[INFO] Початок транскрипції...")
                t0 = time.time()
                audio = whisperx.load_audio(cleaned)
                result = self.model.transcribe(audio)
                transcribe_elapsed = time.time() - t0
                self.timing.update(self.model_size, self.device, "chunk", transcribe_elapsed)
                logger.info(f"[TIME] Транскрипція: {transcribe_elapsed:.2f} с")

                if self.stop_event.is_set():
                    raise TranscriptionCancelledError()

                result = self._align_and_diarize(audio, result["segments"], output_txt)
                self.work_dir.save_json(result, "aligned.json")

            total_time = time.time() - start_total
            logger.info(f"[DONE] Загальний час обробки: {total_time / 60:.1f} хв ({total_time:.1f} с)")
            self.work_dir.cleanup()
            logger.info(self._elapsed("Обробку завершено"))
            return output_txt
        except Exception:
            logger.info(f"[INFO] Робоча директорія збережена: {self.work_dir.path}")
            raise
