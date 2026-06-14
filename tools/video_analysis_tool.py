from __future__ import annotations

import json
import os
import re
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

from config import CACHE_DIR, OUTPUT_DIR, is_mock_mode
from tools.keyword_tool import extract_keywords
from tools.llm_client import call_llm
from tools.media_tool import SubtitleItem, parse_srt, save_srt, save_video_markers
from tools.mindmap_tool import create_mindmap_image, generate_mindmap_structure
from tools.summary_tool import generate_summary


def analyze_course_video(
    video_path: str,
    subtitle_path: str | None = None,
    output_dir: str | Path | None = None,
    transcribe_if_missing: bool = True,
    whisper_model_size: str = "base",
    language: str = "zh",
) -> Dict[str, Any]:
    """Analyze an existing course video from subtitles or local transcription."""
    output = Path(output_dir or OUTPUT_DIR)
    output.mkdir(parents=True, exist_ok=True)

    transcript_source = "uploaded_srt"
    if subtitle_path:
        subtitles = parse_srt(Path(subtitle_path).read_text(encoding="utf-8-sig"))
        srt_path = Path(subtitle_path)
    elif transcribe_if_missing:
        transcript_source = "auto_transcription"
        subtitles = transcribe_video_to_subtitles(
            video_path,
            output / "course_video_auto_subtitles.srt",
            model_size=whisper_model_size,
            language=language,
        )
        srt_path = output / "course_video_auto_subtitles.srt"
    else:
        raise ValueError("请上传 SRT 字幕，或开启本地语音识别。")

    if not subtitles:
        raise ValueError("没有识别到可分析的字幕内容。")

    transcript_text = subtitles_to_transcript(subtitles)
    transcript_path = output / "course_video_transcript.txt"
    transcript_path.write_text(transcript_text, encoding="utf-8")

    fallback = _local_video_analysis(subtitles, transcript_text)
    analysis = fallback if is_mock_mode() else _llm_video_analysis(transcript_text, fallback)
    analysis = _normalize_analysis(analysis, fallback)

    summary = generate_summary(transcript_text)
    keywords = extract_keywords(transcript_text)
    mindmap = generate_mindmap_structure(transcript_text)
    mindmap_json_path = output / "course_video_mindmap.json"
    mindmap_json_path.write_text(json.dumps(mindmap, ensure_ascii=False, indent=2), encoding="utf-8")
    mindmap_path = create_mindmap_image(mindmap, str(output / "course_video_mindmap.png"))

    markers = analysis.get("markers") or fallback["markers"]
    highlights = analysis.get("highlights") or fallback["highlights"]
    summary_md_path = output / "course_video_analysis.md"
    markers_path = output / "course_video_markers.json"
    analysis_json_path = output / "course_video_analysis.json"
    highlighted_path = output / "course_video_highlights.md"

    save_video_markers(markers, markers_path)
    highlighted_md = _highlight_markdown(analysis, highlights, keywords.get("keywords", []))
    highlighted_path.write_text(highlighted_md, encoding="utf-8")

    report = {
        "source_video": str(video_path),
        "subtitle_source": transcript_source,
        "subtitles_path": str(srt_path),
        "transcript_path": str(transcript_path),
        "summary": summary.get("summary", ""),
        "keywords": keywords.get("keywords", []),
        "mindmap_json": str(mindmap_json_path),
        "mindmap_visual": str(mindmap_path),
        "markers": markers,
        "highlights": highlights,
        "analysis": analysis,
        "analysis_markdown": str(summary_md_path),
        "highlights_markdown": str(highlighted_path),
        "markers_path": str(markers_path),
    }
    summary_md_path.write_text(_analysis_markdown(report), encoding="utf-8")
    analysis_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["analysis_json"] = str(analysis_json_path)
    return report


def transcribe_video_to_subtitles(
    video_path: str,
    output_srt: str | Path,
    model_size: str = "base",
    language: str = "zh",
) -> List[SubtitleItem]:
    """Transcribe a video into SRT with faster-whisper when it is available."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ValueError(
            "当前环境未安装本地语音识别库 faster-whisper。请先上传 SRT 字幕，或释放磁盘空间后安装 faster-whisper。"
        ) from exc

    cache_dir = Path(os.getenv("COURSEAGENT_MODEL_CACHE", str(CACHE_DIR / "models" / "whisper")))
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "hub"))
    cached_srt = cache_dir / "transcripts" / f"{_file_hash(video_path)}_{model_size}_{language}.srt"
    if cached_srt.exists():
        output = Path(output_srt)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached_srt, output)
        return parse_srt(output.read_text(encoding="utf-8-sig"))

    output = Path(output_srt)
    output.parent.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).with_name("whisper_worker.py")
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(cache_dir))
    env.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "hub"))
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("CT2_NUM_THREADS", "2")
    timeout = int(os.getenv("COURSEAGENT_TRANSCRIBE_TIMEOUT", "1800"))
    command = [
        sys.executable,
        str(worker),
        "--video",
        str(video_path),
        "--output",
        str(output),
        "--model-size",
        model_size,
        "--language",
        language,
        "--cache-dir",
        str(cache_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("当前 Python 环境不可用，无法启动本地语音识别子进程。") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"本地语音识别超过 {timeout} 秒仍未完成。建议上传 SRT 字幕，或改用 base/small 模型后重试。"
        ) from exc

    if completed.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        stderr_tail = (completed.stderr or completed.stdout or "").strip()[-1200:]
        detail = f"\n底层输出：{stderr_tail}" if stderr_tail else ""
        raise ValueError(
            "本地语音识别进程异常退出，但主工作台已保持运行。"
            "这通常是 faster-whisper/ctranslate2 在当前机器上加载较大模型时发生的原生崩溃。"
            "建议优先上传 SRT 字幕，或使用 base/small 模型重试。"
            f"{detail}"
        )

    subtitles = parse_srt(output.read_text(encoding="utf-8-sig"))
    if not subtitles:
        raise ValueError("本地语音识别没有生成可分析的字幕内容。建议上传 SRT 字幕或换用 base/small 模型。")
    cached_srt.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(output, cached_srt)
    except Exception:
        pass
    return subtitles


def transcribe_video_to_subtitles(
    video_path: str,
    output_srt: str | Path,
    model_size: str = "base",
    language: str = "zh",
) -> List[SubtitleItem]:
    """Transcribe a video into SRT with isolated workers and a torch fallback."""
    cache_dir = Path(os.getenv("COURSEAGENT_MODEL_CACHE", str(CACHE_DIR / "models" / "whisper")))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_srt = cache_dir / "transcripts" / f"{_file_hash(video_path)}_{model_size}_{language}.srt"
    output = Path(output_srt)
    if cached_srt.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached_srt, output)
        return parse_srt(output.read_text(encoding="utf-8-sig"))

    output.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(os.getenv("COURSEAGENT_TRANSCRIBE_TIMEOUT", "1800"))
    errors: list[str] = []
    torch_python = Path(
        os.getenv("COURSEAGENT_TORCH_WHISPER_PYTHON", r"E:\CourseAgent\venvs\whisper_torch\Scripts\python.exe")
    )
    preferred_backend = os.getenv("COURSEAGENT_TRANSCRIBE_BACKEND", "").strip().lower()
    if not preferred_backend:
        preferred_backend = "torch" if torch_python.exists() else "auto"
    ok = False

    if preferred_backend != "torch":
        faster_env = _worker_env(cache_dir)
        faster_env.setdefault("HF_HOME", str(cache_dir))
        faster_env.setdefault("HUGGINGFACE_HUB_CACHE", str(cache_dir / "hub"))
        faster_env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        faster_env.setdefault("OMP_NUM_THREADS", "2")
        faster_env.setdefault("CT2_NUM_THREADS", "2")
        ok, message = _run_transcription_worker(
            [
                sys.executable,
                str(Path(__file__).with_name("whisper_worker.py")),
                "--video",
                str(video_path),
                "--output",
                str(output),
                "--model-size",
                model_size,
                "--language",
                language,
                "--cache-dir",
                str(cache_dir),
            ],
            faster_env,
            timeout,
        )
        if not ok:
            errors.append(f"faster-whisper failed: {message}")
    else:
        errors.append("faster-whisper skipped: PyTorch Whisper is the preferred backend on this machine")

    if not ok and preferred_backend != "faster":
        output.unlink(missing_ok=True)
        if torch_python.exists():
            torch_cache_dir = cache_dir / "torch"
            ok, message = _run_transcription_worker(
                [
                    str(torch_python),
                    str(Path(__file__).with_name("torch_whisper_worker.py")),
                    "--video",
                    str(video_path),
                    "--output",
                    str(output),
                    "--model-size",
                    model_size,
                    "--language",
                    language,
                    "--cache-dir",
                    str(torch_cache_dir),
                ],
                _worker_env(torch_cache_dir),
                timeout,
            )
            if not ok:
                errors.append(f"PyTorch Whisper failed: {message}")
        else:
            errors.append(f"PyTorch Whisper env missing: {torch_python}")

    if not ok or not output.exists() or output.stat().st_size == 0:
        raise ValueError(
            "本地语音识别没有成功生成字幕。已尝试 faster-whisper 和 PyTorch Whisper 备用后端。"
            "如果仍失败，建议先上传 SRT 字幕完成课程视频分析。\n"
            + "\n".join(errors)[-2400:]
        )

    subtitles = parse_srt(output.read_text(encoding="utf-8-sig"))
    if not subtitles:
        raise ValueError("本地语音识别没有生成可分析的字幕内容。建议上传 SRT 字幕或换用 base/small 模型。")
    cached_srt.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(output, cached_srt)
    except Exception:
        pass
    return subtitles


def _worker_env(cache_dir: Path) -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("TMP", str(CACHE_DIR / "tmp"))
    env.setdefault("TEMP", str(CACHE_DIR / "tmp"))
    Path(env["TMP"]).mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return env


def _run_transcription_worker(command: list[str], env: dict[str, str], timeout: int) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return False, f"unable to start process: {exc}"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout} seconds"

    if completed.returncode == 0:
        return True, ""
    output = (completed.stderr or completed.stdout or "").strip()
    return False, f"exit code {completed.returncode}; output: {output[-1200:]}" if output else f"exit code {completed.returncode}"


def _file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def subtitles_to_transcript(subtitles: Sequence[SubtitleItem]) -> str:
    lines = []
    for item in subtitles:
        lines.append(f"[{_seconds_to_clock(item.start)} - {_seconds_to_clock(item.end)}] {item.text}")
    return "\n".join(lines)


def _llm_video_analysis(transcript_text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
你是 CourseAgent 的课堂视频分析器。请严格基于字幕转录内容，输出 JSON。

要求：
1. summary：用中文总结课堂视频讲了什么，必须聚焦课程知识点。
2. key_points：列出 6-10 个核心知识点，每个包含 title、explanation、evidence。
3. markers：列出 5-10 个重点时间戳，每个包含 start、end、title、summary、importance。
4. highlights：列出 4-8 个最值得复习的高亮片段，每个包含 start、end、quote、reason、tags。
5. 不要编造字幕中没有的知识点。

JSON 结构：
{{
  "summary": "...",
  "key_points": [{{"title": "...", "explanation": "...", "evidence": "..."}}],
  "markers": [{{"start": 0, "end": 30, "title": "...", "summary": "...", "importance": "high"}}],
  "highlights": [{{"start": 0, "end": 30, "quote": "...", "reason": "...", "tags": ["..."]}}]
}}

字幕转录：
{transcript_text[:30000]}
""".strip()
    result = call_llm(prompt, expect_json=True, fallback=fallback)
    return result if isinstance(result, dict) else fallback


def _local_video_analysis(subtitles: Sequence[SubtitleItem], transcript_text: str) -> Dict[str, Any]:
    chunks = _chunk_subtitles(subtitles, target_seconds=90)
    terms = _top_terms(transcript_text, limit=12)
    markers = []
    highlights = []
    key_points = []
    for index, chunk in enumerate(chunks[:10], start=1):
        text = _clean_text(" ".join(item.text for item in chunk["items"]))
        title_terms = [term for term in terms if term in text][:2]
        title = " / ".join(title_terms) if title_terms else f"课堂片段 {index}"
        summary = text[:90] + ("..." if len(text) > 90 else "")
        marker = {
            "start": round(chunk["start"], 2),
            "end": round(chunk["end"], 2),
            "title": title,
            "summary": summary,
            "importance": "high" if index <= 3 else "medium",
        }
        markers.append(marker)
        if title_terms or index <= 4:
            highlights.append(
                {
                    "start": marker["start"],
                    "end": marker["end"],
                    "quote": summary,
                    "reason": "该片段包含课程中的核心概念、方法步骤或案例说明。",
                    "tags": title_terms or [title],
                }
            )
        key_points.append(
            {
                "title": title,
                "explanation": summary,
                "evidence": f"{_seconds_to_clock(chunk['start'])} - {_seconds_to_clock(chunk['end'])}",
            }
        )
    return {
        "summary": _clean_text(transcript_text)[:420],
        "key_points": key_points[:8],
        "markers": markers[:8],
        "highlights": highlights[:6],
    }


def _normalize_analysis(analysis: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(fallback)
    if isinstance(analysis.get("summary"), str) and analysis["summary"].strip():
        normalized["summary"] = analysis["summary"].strip()
    for field in ["key_points", "markers", "highlights"]:
        value = analysis.get(field)
        if isinstance(value, list) and value:
            normalized[field] = value
    for marker in normalized.get("markers", []):
        marker["start"] = float(marker.get("start", 0) or 0)
        marker["end"] = float(marker.get("end", marker["start"] + 30) or marker["start"] + 30)
        marker.setdefault("title", "重点片段")
        marker.setdefault("summary", "")
        marker.setdefault("importance", "medium")
    for highlight in normalized.get("highlights", []):
        highlight["start"] = float(highlight.get("start", 0) or 0)
        highlight["end"] = float(highlight.get("end", highlight["start"] + 30) or highlight["start"] + 30)
        highlight.setdefault("quote", "")
        highlight.setdefault("reason", "重点内容")
        highlight.setdefault("tags", [])
    return normalized


def _chunk_subtitles(subtitles: Sequence[SubtitleItem], target_seconds: float = 90) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    current: List[SubtitleItem] = []
    start = subtitles[0].start if subtitles else 0
    for item in subtitles:
        if current and item.end - start >= target_seconds:
            chunks.append({"start": start, "end": current[-1].end, "items": current})
            current = []
            start = item.start
        current.append(item)
    if current:
        chunks.append({"start": start, "end": current[-1].end, "items": current})
    return chunks


def _top_terms(text: str, limit: int = 12) -> List[str]:
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_\-]{1,24}", text)
    stopwords = {
        "这个",
        "那个",
        "我们",
        "你们",
        "他们",
        "就是",
        "然后",
        "所以",
        "因为",
        "可以",
        "进行",
        "一个",
        "一些",
        "the",
        "and",
        "for",
        "with",
    }
    counts: Dict[str, int] = {}
    for word in candidates:
        word = word.strip()
        if len(word) < 2 or word.lower() in stopwords:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _analysis_markdown(report: Dict[str, Any]) -> str:
    analysis = report["analysis"]
    lines = ["# 课堂视频分析报告", ""]
    lines.extend(["## 视频摘要", "", report.get("summary") or analysis.get("summary", ""), ""])
    lines.extend(["## 核心知识点", ""])
    for item in analysis.get("key_points", []):
        lines.append(f"- **{item.get('title', '知识点')}**：{item.get('explanation', '')}（证据：{item.get('evidence', '')}）")
    lines.extend(["", "## 重点时间戳", ""])
    for marker in report.get("markers", []):
        lines.append(
            f"- `{_seconds_to_clock(float(marker.get('start', 0)))}` - `{_seconds_to_clock(float(marker.get('end', 0)))}` "
            f"**{marker.get('title', '重点片段')}**：{marker.get('summary', '')}"
        )
    lines.extend(["", "## Highlight 重点片段", ""])
    for item in report.get("highlights", []):
        tags = "、".join(str(tag) for tag in item.get("tags", []))
        lines.append(
            f"- <mark>{item.get('quote', '')}</mark> "
            f"`{_seconds_to_clock(float(item.get('start', 0)))}` - `{_seconds_to_clock(float(item.get('end', 0)))}` "
            f"{item.get('reason', '')} {tags}"
        )
    return "\n".join(lines) + "\n"


def _highlight_markdown(analysis: Dict[str, Any], highlights: Sequence[Dict[str, Any]], keywords: Sequence[str]) -> str:
    text = analysis.get("summary", "")
    for keyword in sorted([k for k in keywords if k], key=len, reverse=True)[:12]:
        text = re.sub(f"({re.escape(keyword)})", r"<mark>\1</mark>", text)
    lines = ["# Highlight 重点摘要", "", text, "", "## 重点片段", ""]
    for item in highlights:
        lines.append(
            f"- `{_seconds_to_clock(float(item.get('start', 0)))}` "
            f"<mark>{item.get('quote', '')}</mark>：{item.get('reason', '')}"
        )
    return "\n".join(lines) + "\n"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _seconds_to_clock(value: float) -> str:
    minutes = int(value // 60)
    seconds = int(value % 60)
    return f"{minutes:02d}:{seconds:02d}"
