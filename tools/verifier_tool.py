from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from config import OUTPUT_DIR


def verify_outputs(
    state: Dict[str, Any],
    planned_tools: List[str] | None = None,
    output_dir: str | Path | None = None,
) -> Dict[str, Any]:
    """Verify that planned Agent artifacts exist and are non-empty."""
    planned = set(planned_tools or [])
    expected = _expected_outputs(state, planned, Path(output_dir or state.get("output_dir") or OUTPUT_DIR))
    files = []
    missing = []
    for name, path in expected.items():
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        item = {"name": name, "path": str(path), "exists": exists, "size": size}
        files.append(item)
        if not exists or size <= 0:
            missing.append(item)

    return {
        "ok": not missing,
        "planned_tools": list(planned),
        "files": files,
        "missing": missing,
    }


def _expected_outputs(state: Dict[str, Any], planned: set[str], output_dir: Path) -> Dict[str, Path]:
    expected: Dict[str, Path] = {}
    if "generate_summary" in planned:
        expected["summary"] = output_dir / "summary.md"
    if "extract_keywords" in planned:
        expected["keywords"] = output_dir / "keywords.json"
    if "generate_mindmap" in planned:
        expected["mindmap_json"] = output_dir / "mindmap.json"
        expected["mindmap_visual"] = Path(state.get("mindmap_image_path") or output_dir / "mindmap.png")
    if "generate_ppt_outline" in planned:
        expected["ppt_outline"] = output_dir / "ppt_outline.json"
    if "generate_slide_scripts" in planned:
        expected["speech_script"] = output_dir / "speech_script.md"
    if "create_ppt" in planned:
        expected["ppt"] = Path(state.get("ppt_path") or output_dir / "generated_presentation.pptx")
    if "create_video" in planned:
        expected["video"] = Path(state.get("video_path") or output_dir / "final_video.mp4")
        expected["subtitles"] = output_dir / "subtitles.srt"
        expected["video_markers"] = output_dir / "video_markers.json"
        expected["video_chapters"] = output_dir / "video_chapters.md"
        expected["voice_report"] = output_dir / "voice_report.json"
    if not expected:
        expected["summary"] = output_dir / "summary.md"
    return expected
