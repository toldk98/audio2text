import queue
import sys
import threading
import time
import wave
import numpy as np
import sounddevice as sd
import torch
import whisperx

from whisper_offline import _confirm_download, DownloadCancelledError


class WhisperRealtimeTranscriber:
    def __init__(
            self,
            model_size: str = "tiny",
            language: str = "uk",
            sample_rate: int = 16000,
            chunk_duration: int = 3,
            save_audio: bool = True,
            out_file: str = "session_record.wav",
            record_both: bool = True,
            mic_device=None,
            spk_device=None,
    ):
        self.model_size = model_size
        self.language = language
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.save_audio = save_audio
        self.out_file = out_file
        self.record_both = record_both
        self.mic_device = mic_device
        self.spk_device = spk_device

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"

        self.time_process = time.time()
        self.session_start_time = None

        print(f"[INFO] Ініціалізація WhisperRealtimeTranscriber...")
        print(f"[INFO] Пристрій: {self.device}, модель: {self.model_size}")

        _confirm_download(self.model_size, do_align=False, do_diarize=False)

        t0 = time.time()
        self.model = whisperx.load_model(
            self.model_size,
            device=self.device,
            language=self.language,
            compute_type=self.compute_type,
        )
        t1 = time.time()
        print(f"[TIME] Модель завантажена за {t1 - t0:.2f} с")

        self.recording = False
        self.q = queue.Queue()

    def _elapsed(self, label: str) -> str:
        delta = time.time() - self.time_process
        return f"[TIME] {label}: {delta:.2f} с від старту об'єкта"

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        self.q.put(indata.copy())

    def _record_audio(self):
        print("[🎙️] Почато запис. Натисни Ctrl+C для зупинки.")
        print(self._elapsed("Старт аудіозахоплення"))

        mic_stream = None
        spk_stream = None

        if self.record_both:
            print("[INFO] Режим запису обох потоків (мікрофон + динаміки).")
            mic_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.mic_device or None,
                callback=self._audio_callback,
            )
            spk_stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=self.spk_device or None,
                callback=self._audio_callback,
            )

            mic_stream.start()
            spk_stream.start()

            while self.recording:
                sd.sleep(200)

            mic_stream.stop()
            spk_stream.stop()
        else:
            with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    device=self.mic_device or None,
                    callback=self._audio_callback,
            ):
                while self.recording:
                    sd.sleep(200)

        print(self._elapsed("Зупинка аудіозахоплення"))

    def _process_audio(self):
        buffer = np.array([], dtype=np.float32)
        segment_id = 0

        realtime_pipeline_start = time.time()

        wf = None
        if self.save_audio:
            wf = wave.open(self.out_file, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)

        while self.recording or not self.q.empty():
            try:
                chunk = self.q.get(timeout=1)
                buffer = np.concatenate((buffer, chunk.flatten()))
                if wf:
                    wf.writeframes((chunk * 32767).astype(np.int16).tobytes())
            except queue.Empty:
                continue

            if len(buffer) >= self.sample_rate * self.chunk_duration:
                block = buffer[: self.sample_rate * self.chunk_duration]
                buffer = buffer[self.sample_rate * self.chunk_duration:]

                print(f"\n[INFO] Обробка блоку {segment_id} ({self.chunk_duration}s)...")

                t_transcribe_start = time.time()
                result = self.model.transcribe(block)
                t_transcribe_end = time.time()

                text = result.get("text", "").strip()
                if text:
                    elapsed_live = time.time() - realtime_pipeline_start
                    print(f"[{elapsed_live:6.1f}s] 🗣️ {text}")
                    print(f"[TIME] Блок {segment_id} розпізнано за {t_transcribe_end - t_transcribe_start:.2f} с")

                segment_id += 1

        if wf:
            wf.close()
            print(f"[💾] Запис збережено: {self.out_file}")

        total_session = 0.0
        if self.session_start_time is not None:
            total_session = time.time() - self.session_start_time

        print(f"[🛑] Потік завершено. Загальний час сесії: {total_session:.2f} с")
        print(self._elapsed("Обробку аудіопотоку завершено"))

    def start(self):
        if self.recording:
            print("[WARN] Запис уже триває.")
            return

        self.session_start_time = time.time()
        self.recording = True

        t_rec = threading.Thread(target=self._record_audio)
        t_proc = threading.Thread(target=self._process_audio)

        t_rec.start()
        t_proc.start()

        try:
            while self.recording:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

        t_rec.join()
        t_proc.join()

        total_session = time.time() - self.session_start_time
        print(f"[DONE] Сесію завершено. Тривалість: {total_session:.2f} с")
        print(self._elapsed("Сесія повністю завершена"))

    def stop(self):
        print("\n[INFO] Зупинка...")
        self.recording = False
