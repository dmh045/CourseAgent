from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def save_json(data: Dict[str, Any], output_path: str | Path) -> str:
    """Save a JSON structure with UTF-8 encoding."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def save_summary_markdown(summary: Dict[str, Any], output_path: str | Path) -> str:
    """Save the generated summary as Markdown."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# 文档摘要\n\n{summary.get('summary', '')}\n", encoding="utf-8")
    return str(path)


def create_run_report(state: Dict[str, Any], output_path: str | Path) -> str:
    """Create a Markdown report describing the Agent run and output files."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output_files = [
        "summary.md",
        "keywords.json",
        "mindmap.json",
        "mindmap.png / mindmap.mmd",
        "ppt_outline.json",
        "speech_script.md",
        "generated_presentation.pptx",
        "final_video.mp4",
        "narration_audio/narration.mp3",
        "subtitles.srt",
        "video_markers.json",
        "video_chapters.md",
        "voice_report.json",
    ]
    lines = [
        "# CourseAgent 运行报告",
        "",
        f"任务目标：{state.get('user_goal', '')}",
        "",
        "## Planner 决策",
        "",
        f"策略：{state.get('plan', {}).get('strategy', '动态工具调用')}",
        "",
        f"选择工具：{' -> '.join(state.get('selected_tools', []))}",
        "",
        "## 执行日志",
        "",
    ]
    lines.extend(f"- {item}" for item in state.get("logs", []))
    if state.get("trace"):
        lines.extend(["", "## Thought / Action / Observation", ""])
        for item in state.get("trace", []):
            lines.extend(
                [
                    f"### Step {item.get('step')} - {item.get('action')}",
                    "",
                    f"Thought：{item.get('thought')}",
                    "",
                    f"Observation：{item.get('observation')}",
                    "",
                ]
            )
    if state.get("repairs"):
        lines.extend(["", "## Auto-Repair 记录", ""])
        for repair in state.get("repairs", []):
            lines.append(f"- {repair.get('artifact')} -> {repair.get('tool')}")
    if state.get("errors"):
        lines.extend(["", "## 错误信息", ""])
        lines.extend(f"- {item}" for item in state.get("errors", []))
    if state.get("verification"):
        lines.extend(["", "## 产物校验", ""])
        lines.append(f"校验结果：{'通过' if state['verification'].get('ok') else '未通过'}")
        for item in state["verification"].get("files", []):
            status = "OK" if item.get("exists") and item.get("size", 0) > 0 else "MISSING"
            lines.append(f"- {status} {item.get('name')}: {item.get('path')} ({item.get('size', 0)} bytes)")
    lines.extend(["", "## 输出文件", ""])
    lines.extend(f"- output/{item}" for item in output_files)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
