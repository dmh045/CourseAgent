from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence


@dataclass
class SubtitleItem:
    index: int
    start: float
    end: float
    text: str


def create_explanation_video(
    outline: Dict[str, Any],
    scripts: Dict[str, Any],
    output_path: str,
    seconds_per_slide: int = 5,
    voice_enabled: bool = True,
) -> str:
    """
    Create an animated explanation video with MoviePy.

    Outputs alongside the MP4:
    - subtitles.srt
    - video_markers.json
    - video_chapters.md
    """
    try:
        from moviepy import AudioFileClip, ImageSequenceClip, concatenate_audioclips
    except ImportError as exc:
        raise ValueError("缺少 moviepy，无法生成讲解视频。") from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_dir = output.parent / "video_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    audio_clip = None
    audio_report = _build_narration_audio(
        scripts=scripts,
        audio_dir=output.parent / "narration_audio",
        voice_enabled=voice_enabled,
        audio_file_clip=AudioFileClip,
        concatenate_audioclips=concatenate_audioclips,
    )
    slide_durations = audio_report.get("durations") or [float(seconds_per_slide)] * len(outline.get("slides", []))
    combined_audio = audio_report.get("combined_audio")
    if combined_audio and Path(combined_audio).exists():
        audio_clip = AudioFileClip(str(combined_audio))

    frame_paths, subtitles, markers = _render_animated_frames(
        outline=outline,
        scripts=scripts,
        frame_dir=frame_dir,
        seconds_per_slide=seconds_per_slide,
        slide_durations=slide_durations,
        fps=6,
    )
    if not frame_paths:
        raise ValueError("没有可用于生成视频的 PPT 大纲。")

    clip = ImageSequenceClip([str(path) for path in frame_paths], fps=6)
    if audio_clip:
        clip = clip.with_audio(audio_clip)
        clip.write_videofile(
            str(output),
            fps=6,
            codec="libx264",
            audio_codec="aac",
            logger=None,
            pixel_format="yuv420p",
        )
    else:
        clip.write_videofile(
            str(output),
            fps=6,
            codec="libx264",
            audio=False,
            logger=None,
            pixel_format="yuv420p",
        )
    clip.close()
    if audio_clip:
        audio_clip.close()
    if os.getenv("COURSEAGENT_KEEP_VIDEO_FRAMES", "false").lower() not in {"1", "true", "yes", "on"}:
        shutil.rmtree(frame_dir, ignore_errors=True)

    save_srt(subtitles, output.parent / "subtitles.srt")
    save_video_markers(markers, output.parent / "video_markers.json")
    save_chapters(markers, output.parent / "video_chapters.md")
    (output.parent / "voice_report.json").write_text(json.dumps(audio_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def filter_video_by_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    sensitive_words: Sequence[str] | None = None,
    remove_non_speech: bool = True,
    padding: float = 0.25,
) -> Dict[str, Any]:
    """
    Cut a video according to subtitle text.

    When remove_non_speech is true, only subtitle-covered intervals are kept.
    Subtitle intervals containing sensitive words are removed.
    """
    try:
        from moviepy import VideoFileClip, concatenate_videoclips
    except ImportError as exc:
        raise ValueError("缺少 moviepy，无法处理视频。") from exc

    video = VideoFileClip(video_path)
    subtitles = parse_srt(Path(subtitle_path).read_text(encoding="utf-8-sig"))
    sensitive = [word.strip() for word in (sensitive_words or []) if word.strip()]

    removed = []
    candidate_intervals = []
    for item in subtitles:
        hit_words = [word for word in sensitive if word and word in item.text]
        if hit_words:
            removed.append({"start": item.start, "end": item.end, "text": item.text, "reason": "敏感词：" + "、".join(hit_words)})
            continue
        if remove_non_speech:
            candidate_intervals.append((max(item.start - padding, 0), min(item.end + padding, video.duration)))

    if not remove_non_speech:
        blocked = [(max(item["start"] - padding, 0), min(item["end"] + padding, video.duration)) for item in removed]
        candidate_intervals = _invert_intervals(blocked, video.duration)

    keep_intervals = _merge_intervals(candidate_intervals, max_gap=0.35)
    if not keep_intervals:
        video.close()
        raise ValueError("过滤后没有可保留的视频片段，请调整敏感词或关闭非讲解过滤。")

    clips = [video.subclipped(start, end) for start, end in keep_intervals if end - start > 0.05]
    final = concatenate_videoclips(clips, method="compose") if len(clips) > 1 else clips[0]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(str(output), codec="libx264", audio_codec="aac", logger=None, pixel_format="yuv420p")

    rebased_subtitles = _rebase_subtitles(subtitles, keep_intervals, sensitive)
    filtered_srt = output.with_name(output.stem + "_filtered.srt")
    save_srt(rebased_subtitles, filtered_srt)
    report = {
        "source_video": str(video_path),
        "source_subtitles": str(subtitle_path),
        "output_video": str(output),
        "output_subtitles": str(filtered_srt),
        "keep_intervals": [{"start": s, "end": e, "duration": e - s} for s, e in keep_intervals],
        "removed": removed,
        "remove_non_speech": remove_non_speech,
        "sensitive_words": sensitive,
    }
    report_path = output.with_name(output.stem + "_filter_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for clip in clips:
        clip.close()
    if final not in clips:
        final.close()
    video.close()
    return report


def compose_videos(
    video_paths: Sequence[str],
    output_path: str,
    title: str = "课程讲解视频合成",
) -> Dict[str, Any]:
    """Concatenate multiple videos with a generated title card."""
    try:
        from moviepy import ImageClip, VideoFileClip, concatenate_videoclips
    except ImportError as exc:
        raise ValueError("缺少 moviepy，无法合成视频。") from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    title_card = output.parent / "composition_title.png"
    _render_title_card(title, title_card)

    clips = [ImageClip(str(title_card), duration=2)]
    clips.extend(VideoFileClip(str(path)) for path in video_paths)
    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(str(output), codec="libx264", audio_codec="aac", logger=None, pixel_format="yuv420p")

    report = {
        "title": title,
        "output_video": str(output),
        "segments": [{"path": str(path)} for path in video_paths],
    }
    report_path = output.with_name(output.stem + "_compose_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for clip in clips:
        clip.close()
    final.close()
    return report


def parse_srt(srt_text: str) -> List[SubtitleItem]:
    """Parse a standard SRT string into subtitle items."""
    blocks = re.split(r"\n\s*\n", srt_text.strip(), flags=re.M)
    items: List[SubtitleItem] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            index = len(items) + 1
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        items.append(SubtitleItem(index=index, start=_srt_time_to_seconds(start_raw), end=_srt_time_to_seconds(end_raw), text=" ".join(lines[2:])))
    return items


def save_srt(items: Sequence[SubtitleItem], output_path: str | Path) -> str:
    """Save subtitle items as an SRT file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                str(index),
                f"{_seconds_to_srt_time(item.start)} --> {_seconds_to_srt_time(item.end)}",
                item.text,
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def save_video_markers(markers: Sequence[Dict[str, Any]], output_path: str | Path) -> str:
    """Save timestamp markers as JSON."""
    path = Path(output_path)
    path.write_text(json.dumps(list(markers), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def save_chapters(markers: Sequence[Dict[str, Any]], output_path: str | Path) -> str:
    """Save human-readable video chapters."""
    path = Path(output_path)
    lines = ["# 视频章节与重点时间戳", ""]
    for marker in markers:
        lines.append(f"- `{_seconds_to_clock(marker['start'])}` - {marker['title']}：{marker.get('summary', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _build_narration_audio(
    scripts: Dict[str, Any],
    audio_dir: Path,
    voice_enabled: bool,
    audio_file_clip: Any,
    concatenate_audioclips: Any,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "enabled": bool(voice_enabled),
        "ok": False,
        "voice": os.getenv("COURSEAGENT_TTS_VOICE", "zh-CN-XiaoxiaoNeural"),
        "rate": os.getenv("COURSEAGENT_TTS_RATE", "+0%"),
        "audio_files": [],
        "combined_audio": None,
        "durations": [],
        "message": "",
    }
    script_items = scripts.get("scripts", []) or []
    if not voice_enabled or not script_items:
        report["message"] = "voice disabled or no scripts"
        return report

    audio_dir.mkdir(parents=True, exist_ok=True)
    for old_file in list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.txt")):
        try:
            old_file.unlink()
        except PermissionError:
            pass

    messages: list[str] = []
    try:
        report["audio_files"] = _synthesize_with_edge_tts(script_items, audio_dir, report["voice"], report["rate"])
        if report["audio_files"]:
            report["engine"] = "edge-tts"
    except Exception as exc:
        messages.append(f"edge-tts failed: {exc}")

    if not report["audio_files"]:
        try:
            report["audio_files"] = _synthesize_with_windows_speech(script_items, audio_dir)
            if report["audio_files"]:
                report["engine"] = "windows-sapi"
        except Exception as exc:
            messages.append(f"windows-sapi failed: {exc}")

    if not report["audio_files"]:
        report["ok"] = False
        report["message"] = "TTS failed, generated silent video instead. " + " | ".join(messages)
        return report

    clips = []
    try:
        clips = [audio_file_clip(path) for path in report["audio_files"]]
        report["durations"] = [max(float(clip.duration or 0) + 0.25, 2.0) for clip in clips]
        combined = concatenate_audioclips(clips)
        combined_path = audio_dir / "narration.mp3"
        combined.write_audiofile(str(combined_path), logger=None)
        report["combined_audio"] = str(combined_path)
        report["ok"] = True
        report["message"] = "voice narration generated"
        combined.close()
    except Exception as exc:
        report["ok"] = False
        report["message"] = f"audio merge failed, generated silent video instead: {exc}"
        report["audio_files"] = []
        report["combined_audio"] = None
        report["durations"] = []
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
    return report


def _synthesize_with_edge_tts(script_items: Sequence[Dict[str, Any]], audio_dir: Path, voice: str, rate: str) -> list[str]:
    import edge_tts

    audio_files: list[str] = []

    async def synthesize_all() -> None:
        for index, item in enumerate(script_items, start=1):
            text = _tts_text(str(item.get("script") or item.get("title") or ""))
            if not text:
                continue
            target = audio_dir / f"slide_{index:02d}.mp3"
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
            await asyncio.wait_for(communicate.save(str(target)), timeout=45)
            if target.exists() and target.stat().st_size > 1024:
                audio_files.append(str(target))

    _run_async(synthesize_all())
    return audio_files


def _synthesize_with_windows_speech(script_items: Sequence[Dict[str, Any]], audio_dir: Path) -> list[str]:
    audio_files: list[str] = []
    for index, item in enumerate(script_items, start=1):
        text = _tts_text(str(item.get("script") or item.get("title") or ""))
        if not text:
            continue
        text_path = audio_dir / f"slide_{index:02d}.txt"
        wav_path = audio_dir / f"slide_{index:02d}.wav"
        text_path.write_text(text, encoding="utf-8")
        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$zh = $speaker.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | "
            "Where-Object { $_.Culture.Name -like 'zh-*' } | Select-Object -First 1; "
            "if ($zh) { $speaker.SelectVoice($zh.Name) }; "
            "$speaker.Rate = 0; "
            "$speaker.Volume = 100; "
            f"$text = Get-Content -LiteralPath '{_ps_escape(text_path)}' -Raw -Encoding UTF8; "
            f"$speaker.SetOutputToWaveFile('{_ps_escape(wav_path)}'); "
            "$speaker.Speak($text); "
            "$speaker.Dispose();"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, capture_output=True, text=True, timeout=60)
        if wav_path.exists() and wav_path.stat().st_size > 1024:
            audio_files.append(str(wav_path))
    return audio_files


def _ps_escape(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _run_async(coro: Any) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _tts_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:900]


def _render_animated_frames(
    outline: Dict[str, Any],
    scripts: Dict[str, Any],
    frame_dir: Path,
    seconds_per_slide: int,
    slide_durations: Sequence[float] | None,
    fps: int,
) -> tuple[List[Path], List[SubtitleItem], List[Dict[str, Any]]]:
    from PIL import Image, ImageDraw, ImageFont

    script_map = {item.get("page"): item for item in scripts.get("scripts", [])}
    width, height = 1280, 720
    title_font = _font(ImageFont, 44, bold=True)
    body_font = _font(ImageFont, 30)
    small_font = _font(ImageFont, 22)
    tiny_font = _font(ImageFont, 18)

    frame_paths: List[Path] = []
    subtitles: List[SubtitleItem] = []
    markers: List[Dict[str, Any]] = []
    cursor = 0.0

    for slide_index, slide in enumerate(outline.get("slides", []), start=1):
        page = slide.get("page", slide_index)
        title = str(slide.get("title", ""))
        bullets = [str(item) for item in slide.get("bullets", [])[:5]]
        script = script_map.get(page, {}).get("script", "")
        duration = float(slide_durations[slide_index - 1]) if slide_durations and slide_index - 1 < len(slide_durations) else float(seconds_per_slide)
        duration = max(duration, 2.0)
        start = cursor
        end = start + duration
        cursor = end
        subtitles.append(SubtitleItem(index=slide_index, start=start, end=end, text=script or title))
        markers.append(
            {
                "page": page,
                "title": title,
                "start": start,
                "end": end,
                "summary": "；".join(bullets[:2]),
                "keywords": bullets[:3],
            }
        )

        frame_total = max(1, int(round(duration * fps)))
        for frame_no in range(frame_total):
            progress = frame_no / max(frame_total - 1, 1)
            image = Image.new("RGB", (width, height), "#f8fafc")
            draw = ImageDraw.Draw(image)

            accent_x = int(40 + progress * 70)
            _rect(draw, 0, 0, width, 102, "#1d4ed8")
            draw.text((54, 26), f"第 {page} 页  {title}", font=title_font, fill="white")
            draw.rectangle((0, 102, int(width * progress), 108), fill="#22d3ee")
            draw.ellipse((accent_x, 128, accent_x + 18, 146), fill="#2563eb")
            draw.text((54, 126), "重点要点", font=small_font, fill="#1d4ed8")

            y = 170
            for idx, bullet in enumerate(bullets):
                bullet_color = "#111827" if progress >= idx / max(len(bullets), 1) else "#94a3b8"
                wrapped = _wrap_text(bullet, 29)
                for line_index, line in enumerate(wrapped):
                    prefix = "- " if line_index == 0 else "  "
                    draw.text((78, y), f"{prefix}{line}", font=body_font, fill=bullet_color)
                    y += 40
                y += 7

            _rect(draw, 54, 500, width - 54, 658, "#e0f2fe", outline="#7dd3fc")
            draw.text((78, 520), "字幕 / 讲解词", font=small_font, fill="#0369a1")
            script_y = 552
            for line in _wrap_text(script, 43)[:3]:
                draw.text((78, script_y), line, font=small_font, fill="#0f172a")
                script_y += 31
            draw.text((1038, 676), f"{_seconds_to_clock(start)} - {_seconds_to_clock(end)}", font=tiny_font, fill="#64748b")

            frame_path = frame_dir / f"slide_{slide_index:02d}_{frame_no:03d}.png"
            image.save(frame_path)
            frame_paths.append(frame_path)
    return frame_paths, subtitles, markers


def _render_title_card(title: str, output_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1280, 720
    image = Image.new("RGB", (width, height), "#0f172a")
    draw = ImageDraw.Draw(image)
    title_font = _font(ImageFont, 52, bold=True)
    small_font = _font(ImageFont, 24)
    draw.text((86, 270), title, font=title_font, fill="#f8fafc")
    draw.text((90, 350), "由视频处理工具自动合成", font=small_font, fill="#bae6fd")
    image.save(output_path)


def _font(image_font_module: Any, size: int, bold: bool = False) -> Any:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return image_font_module.truetype(candidate, size=size)
    return image_font_module.load_default()


def _wrap_text(text: str, width: int) -> List[str]:
    if not text:
        return [""]
    lines: List[str] = []
    for paragraph in str(text).splitlines() or [str(text)]:
        lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=True, replace_whitespace=False) or [""])
    return lines


def _rect(draw: Any, x1: int, y1: int, x2: int, y2: int, fill: str, outline: str | None = None) -> None:
    try:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=18, fill=fill, outline=outline)
    except AttributeError:
        draw.rectangle((x1, y1, x2, y2), fill=fill, outline=outline)


def _srt_time_to_seconds(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    seconds = float(rest)
    return int(hours) * 3600 + int(minutes) * 60 + seconds


def _seconds_to_srt_time(value: float) -> str:
    value = max(value, 0)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    millis = int(round((value - int(value)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _seconds_to_clock(value: float) -> str:
    minutes = int(value // 60)
    seconds = int(value % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _merge_intervals(intervals: Sequence[tuple[float, float]], max_gap: float = 0.25) -> List[tuple[float, float]]:
    sorted_intervals = sorted((s, e) for s, e in intervals if e > s)
    if not sorted_intervals:
        return []
    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + max_gap:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _invert_intervals(blocked: Sequence[tuple[float, float]], duration: float) -> List[tuple[float, float]]:
    blocked = _merge_intervals(blocked)
    keep = []
    cursor = 0.0
    for start, end in blocked:
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


def _rebase_subtitles(subtitles: Sequence[SubtitleItem], keep_intervals: Sequence[tuple[float, float]], sensitive_words: Sequence[str]) -> List[SubtitleItem]:
    rebased: List[SubtitleItem] = []
    accumulated = 0.0
    for keep_start, keep_end in keep_intervals:
        for item in subtitles:
            if item.end <= keep_start or item.start >= keep_end:
                continue
            if any(word in item.text for word in sensitive_words):
                continue
            start = accumulated + max(item.start, keep_start) - keep_start
            end = accumulated + min(item.end, keep_end) - keep_start
            if end > start:
                rebased.append(SubtitleItem(index=len(rebased) + 1, start=start, end=end, text=item.text))
        accumulated += keep_end - keep_start
    return rebased
