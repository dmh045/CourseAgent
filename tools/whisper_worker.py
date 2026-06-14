from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.media_tool import SubtitleItem, save_srt


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated faster-whisper transcription worker.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-size", default="base")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "hub"))
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("CT2_NUM_THREADS", "2")

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model_size, device="cpu", compute_type="int8", cpu_threads=2)
    segments, _info = model.transcribe(args.video, language=args.language, vad_filter=True)
    subtitles: list[SubtitleItem] = []
    for index, segment in enumerate(segments, start=1):
        text = " ".join(str(segment.text).split())
        if text:
            subtitles.append(SubtitleItem(index=index, start=float(segment.start), end=float(segment.end), text=text))
    save_srt(subtitles, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
