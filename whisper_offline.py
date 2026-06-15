import os
import shutil
import subprocess
import sys
import tempfile
import time
import whisperx
import torch
from concurrent.futures import ThreadPoolExecutor, as_completed
from whisperx.diarize import DiarizationPipeline
from split_audio import split_audio, dedup_segments
from workdir import WorkDir


class DownloadCancelledError(Exception):
    pass


def _model_cached(model_size: str) -> bool:
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    return os.path.isfile(os.path.join(cache_dir, f"{model_size}.pt"))


def _confirm_download(model_size: str, do_align: bool, do_diarize: bool):
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

    print(f"\n⚠️ Модель '{model_size}' ({size_str}) не знайдено в кеші.")
    print(f"   Потрібно завантажити {size_str} з інтернету (одноразово).")
    if do_align:
        print(f"   Додатково: align модель (~300 MB) при першому використанні.")
    if do_diarize:
        print(f"   Додатково: діаризаційна модель (~200 MB) при першому використанні.")
    response = input("   Продовжити? [y/N]: ").strip().lower()
    if response not in ("y", "yes"):
        raise DownloadCancelledError(f"Завантаження моделі '{model_size}' скасовано")


class WhisperTranscriber:
    def __init__(
            self,
            hf_token: str,
            model_size: str = "base",
            language: str = "uk",
            clean_mode: str = "temp",
            clean_dir: str | None = None,
            post_action: str = "delete",
            post_dir: str | None = None,
            do_align: bool = True,
            do_diarize: bool = True,
            chunk_minutes: int = 0,
            max_workers: int = 2,
    ):
        self.hf_token = hf_token
        self.model_size = model_size
        self.language = language
        self.clean_mode = clean_mode
        self.clean_dir = clean_dir
        self.post_action = post_action
        self.post_dir = post_dir
        self.do_align = do_align
        self.do_diarize = do_diarize
        self.chunk_minutes = chunk_minutes
        self.max_workers = max_workers

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.time_process = time.time()

        print(f"[INFO] Ініціалізація WhisperTranscriber...")
        print(f"[INFO] Пристрій: {self.device}, режим обчислень: {self.compute_type}")

        _confirm_download(self.model_size, self.do_align, self.do_diarize)

        self.model = whisperx.load_model(
            self.model_size,
            device=self.device,
            language=self.language,
            compute_type=self.compute_type,
        )
        print(self._elapsed("Ініціалізація моделі завершена"))

    def _elapsed(self, message: str) -> str:
        elapsed = time.time() - self.time_process
        return f"[TIME] {message}: {elapsed:.2f} с"

    def _clean_audio(self, input_audio: str) -> str:
        if self.work_dir:
            clean_path = self.work_dir.cleaned_audio
        elif self.clean_mode == "custom" and self.clean_dir:
            os.makedirs(self.clean_dir, exist_ok=True)
            base = os.path.basename(input_audio)
            name = os.path.splitext(base)[0]
            clean_path = os.path.join(self.clean_dir, f"{name}_clean.wav")
        else:
            tmp = tempfile.NamedTemporaryFile(suffix="_clean.wav", delete=False)
            clean_path = tmp.name
            tmp.close()

        if os.path.exists(clean_path):
            print(f"[INFO] Використовується кешований cleaned: {clean_path}")
            return clean_path

        print(f"[INFO] Очищення аудіо через ffmpeg (afftdn+loudnorm)...")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_audio,
            "-ar", "16000",
            "-ac", "1",
            "-af", "afftdn,loudnorm",
            clean_path,
        ]

        try:
            subprocess.run(
                ffmpeg_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            print(f"[INFO] Створено очищений файл: {clean_path}")
            return clean_path
        except subprocess.CalledProcessError as e:
            if os.path.exists(clean_path) and not self.work_dir:
                os.unlink(clean_path)
            print("[WARN] ffmpeg завершився з помилкою, використовується оригінальний файл.")
            print(e.stderr.decode("utf-8", errors="ignore"))
            return input_audio

    def _post_process(self, clean_path: str):
        if clean_path == self._original_path:
            return
        if self.work_dir and clean_path == self.work_dir.cleaned_audio:
            if self.post_action in ("keep",):
                print(f"[INFO] Cleaned audio в workdir: {clean_path}")
            return
        if self.post_action == "delete":
            if os.path.exists(clean_path):
                os.unlink(clean_path)
                print(f"[INFO] Видалено: {clean_path}")
        elif self.post_action == "move":
            dst_dir = self.post_dir or os.path.dirname(self._original_path)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, os.path.basename(clean_path))
            shutil.move(clean_path, dst)
            print(f"[INFO] Перенесено: {clean_path} -> {dst}")
        elif self.post_action == "keep":
            print(f"[INFO] Збережено: {clean_path}")

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
            print(f"[INFO] Вирівнювання тексту...")
            t1 = time.time()
            model_a, metadata = whisperx.load_align_model(
                language_code=self.language, device=self.device
            )
            result = whisperx.align(segments, model_a, metadata, audio, self.device)
            print(f"[TIME] Вирівнювання: {time.time() - t1:.2f} с")
        else:
            result = {"segments": segments}

        if self.do_diarize:
            print(f"[INFO] Виконується діаризація...")
            t2 = time.time()
            diarize_model = DiarizationPipeline(
                use_auth_token=self.hf_token, device=self.device
            )
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)
            print(f"[TIME] Діаризація: {time.time() - t2:.2f} с")

        self._write_result(result, output_txt)
        print(f"[DONE] Текст збережено у: {output_txt}")
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
                print(f"[INFO] Resume: {n_resume}/{len(chunks)} чанків уже транскрибовано")
            print(f"[INFO] Транскрибується {len(new_chunks)} чанків...")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                fut_map = {executor.submit(self._transcribe_chunk, p, s): (p, s) for p, s in new_chunks}
                for fut in as_completed(fut_map):
                    p, s = fut_map[fut]
                    segs = fut.result()
                    key = os.path.splitext(os.path.basename(p))[0]
                    self.work_dir.save_transcribed_chunk(key, segs)
                    all_segments.extend(segs)

        return all_segments

    def transcribe_chunked(self, input_audio: str, output_txt: str = None):
        if not os.path.exists(input_audio):
            raise FileNotFoundError(f"Файл '{input_audio}' не знайдено")

        self._original_path = input_audio
        existing = WorkDir.find_existing(input_audio)
        if existing:
            print(f"[INFO] Resume: знайдено робочу директорію {existing.session_id}")
            self.work_dir = existing
        else:
            self.work_dir = WorkDir(input_audio)
        start_total = time.time()

        try:
            print(f"[INFO] Обробка файлу: {input_audio}")

            cleaned = self._clean_audio(input_audio)
            print(self._elapsed("Очищення аудіо завершено"))

            chunk_sec = self.chunk_minutes * 60
            chunks = split_audio(cleaned, chunk_sec=chunk_sec, overlap_sec=5,
                                 output_dir=self.work_dir.ensure_chunks_dir())
            print(f"[INFO] Розбито на {len(chunks)} частин по {self.chunk_minutes} хв")

            if self.work_dir.merged_exists:
                merged = self.work_dir.load_json("merged.json")
                print(f"[INFO] Resume: завантажено merged.json ({len(merged)} сегментів)")
            else:
                t0 = time.time()
                all_segments = self._load_or_transcribe_chunks(chunks)
                all_segments.sort(key=lambda s: s["start"])
                merged = dedup_segments(all_segments, overlap_sec=5.0)
                self.work_dir.save_json(merged, "merged.json")
                print(f"[TIME] Транскрипція + зведення: {time.time() - t0:.2f} с")
                print(f"[INFO] Сегментів після зведення: {len(merged)}")

            if not output_txt:
                base_path = os.path.splitext(self._original_path)[0]
                output_txt = f"{base_path}_transcribed.txt"

            if self.work_dir.aligned_exists:
                result = self.work_dir.load_json("aligned.json")
                print(f"[INFO] Resume: завантажено aligned.json")
                self._write_result(result, output_txt)
            else:
                t_load = time.time()
                audio = whisperx.load_audio(cleaned)
                print(f"[TIME] Завантаження аудіо: {time.time() - t_load:.2f} с")

                result = self._align_and_diarize(audio, merged, output_txt)
                self.work_dir.save_json(result, "aligned.json")

            total_time = time.time() - start_total
            print(f"[DONE] Загальний час обробки: {total_time / 60:.1f} хв ({total_time:.1f} с)")
            self._post_process(cleaned)
            self.work_dir.cleanup()
            print(self._elapsed("Обробку завершено"))
            return output_txt
        except Exception:
            print(f"[INFO] Робоча директорія збережена: {self.work_dir.path}")
            raise

    def transcribe(self, input_audio: str, output_txt: str = None):
        if self.chunk_minutes > 0:
            return self.transcribe_chunked(input_audio, output_txt)

        if not os.path.exists(input_audio):
            raise FileNotFoundError(f"Файл '{input_audio}' не знайдено")

        self._original_path = input_audio
        existing = WorkDir.find_existing(input_audio)
        if existing:
            print(f"[INFO] Resume: знайдено робочу директорію {existing.session_id}")
            self.work_dir = existing
        else:
            self.work_dir = WorkDir(input_audio)
        start_total = time.time()

        try:
            print(f"[INFO] Обробка файлу: {input_audio}")
            cleaned = self._clean_audio(input_audio)
            print(self._elapsed("Очищення аудіо завершено"))

            if not output_txt:
                base_path = os.path.splitext(self._original_path)[0]
                output_txt = f"{base_path}_transcribed.txt"

            if self.work_dir.aligned_exists:
                result = self.work_dir.load_json("aligned.json")
                print(f"[INFO] Resume: завантажено aligned.json")
                self._write_result(result, output_txt)
            else:
                print(f"[INFO] Початок транскрипції...")
                t0 = time.time()
                audio = whisperx.load_audio(cleaned)
                result = self.model.transcribe(audio)
                print(f"[TIME] Транскрипція: {time.time() - t0:.2f} с")

                result = self._align_and_diarize(audio, result["segments"], output_txt)
                self.work_dir.save_json(result, "aligned.json")

            total_time = time.time() - start_total
            print(f"[DONE] Загальний час обробки: {total_time / 60:.1f} хв ({total_time:.1f} с)")
            self._post_process(cleaned)
            self.work_dir.cleanup()
            print(self._elapsed("Обробку завершено"))
            return output_txt
        except Exception:
            print(f"[INFO] Робоча директорія збережена: {self.work_dir.path}")
            raise
