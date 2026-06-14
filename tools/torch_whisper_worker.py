from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.media_tool import SubtitleItem, save_srt


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated PyTorch Whisper transcription worker.")
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-size", default="base")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
    os.environ.setdefault("WHISPER_CACHE", str(cache_dir))

    try:
        import imageio_ffmpeg

        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffmpeg_alias = cache_dir / "ffmpeg.exe"
        if not ffmpeg_alias.exists():
            shutil.copyfile(ffmpeg_exe, ffmpeg_alias)
        os.environ["PATH"] = str(cache_dir) + os.pathsep + str(ffmpeg_exe.parent) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

    import whisper

    model = whisper.load_model(args.model_size, download_root=str(cache_dir))
    result = model.transcribe(
        args.video,
        language=args.language,
        fp16=False,
        verbose=False,
    )
    subtitles: list[SubtitleItem] = []
    for index, segment in enumerate(result.get("segments", []), start=1):
        text = " ".join(str(segment.get("text", "")).split())
        if text:
            subtitles.append(
                SubtitleItem(
                    index=index,
                    start=float(segment.get("start", 0.0)),
                    end=float(segment.get("end", 0.0)),
                    text=text,
                )
            )
    save_srt(subtitles, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
