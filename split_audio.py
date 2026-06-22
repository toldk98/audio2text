import os
import subprocess


def split_audio(audio_path: str, chunk_sec: int = 600, overlap_sec: int = 5,
                output_dir: str = "") -> list[tuple[str, float]]:
    if not output_dir:
        raise ValueError("output_dir is required")
    base = os.path.splitext(os.path.basename(audio_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    tmpdir = output_dir

    duration = _get_duration(audio_path)
    if duration is None:
        return [(audio_path, 0.0)]

    existing = set()
    if os.path.isdir(tmpdir):
        for f in os.listdir(tmpdir):
            if f.endswith(".wav"):
                existing.add(os.path.join(tmpdir, f))

    chunks = []
    start = 0.0
    index = 0

    while start < duration:
        chunk_end = min(start + chunk_sec + overlap_sec, duration)
        out_path = os.path.join(tmpdir, f"{base}_chunk_{index:04d}.wav")

        if out_path in existing:
            chunks.append((out_path, start))
            start += chunk_sec
            index += 1
            continue

        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", str(start),
            "-to", str(chunk_end),
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            out_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=max(30, chunk_sec * 2))
        except subprocess.TimeoutExpired:
            logger = __import__("logging").getLogger("audio2text.split_audio")
            logger.warning(f"[WARN] ffmpeg split перевищив ліміт, чанк пропущено: {out_path}")
            start += chunk_sec
            index += 1
            continue

        chunks.append((out_path, start))
        start += chunk_sec
        index += 1

    return chunks


def _get_duration(audio_path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                audio_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def dedup_segments(segments: list[dict], overlap_sec: float = 5.0) -> list[dict]:
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        gap = seg["start"] - prev["end"]

        if gap < -overlap_sec * 0.5:
            continue

        if gap < 0:
            seg["start"] = prev["end"]

        merged.append(seg)

    return merged

