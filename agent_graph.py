from __future__ import annotations

import os
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

from config import OUTPUT_DIR, ensure_directories, get_api_settings
from tools.document_tool import read_document
from tools.history_tool import collect_artifacts, create_run_dir, list_manifests, write_manifest
from tools.keyword_tool import extract_keywords
from tools.media_tool import create_explanation_video
from tools.mindmap_tool import create_mindmap_image, generate_mindmap_structure
from tools.planner_tool import plan_task
from tools.ppt_outline_tool import generate_ppt_outline
from tools.ppt_tool import create_ppt
from tools.report_tool import create_run_report, save_json, save_summary_markdown
from tools.script_tool import generate_slide_scripts, save_speech_script
from tools.summary_tool import generate_summary
from tools.verifier_tool import verify_outputs


class AgentState(TypedDict, total=False):
    user_goal: str
    file_path: str
    document_text: str
    document_preview: str
    plan: Dict[str, Any]
    selected_tools: List[str]
    summary: Dict[str, Any]
    keywords: Dict[str, Any]
    mindmap: Dict[str, Any]
    mindmap_image_path: Optional[str]
    ppt_outline: Dict[str, Any]
    slide_scripts: Dict[str, Any]
    ppt_path: Optional[str]
    video_path: Optional[str]
    verification: Dict[str, Any]
    repairs: List[Dict[str, Any]]
    report_path: Optional[str]
    manifest_path: Optional[str]
    output_dir: str
    run_id: str
    artifacts: Dict[str, str]
    timings: Dict[str, float]
    logs: List[str]
    trace: List[Dict[str, Any]]
    errors: List[str]


ToolFunc = Callable[[AgentState], AgentState]


def _log(state: AgentState, message: str) -> None:
    state.setdefault("logs", []).append(message)


def _trace(state: AgentState, thought: str, action: str, observation: str) -> None:
    state.setdefault("trace", []).append(
        {
            "step": len(state.get("trace", [])) + 1,
            "thought": thought,
            "action": action,
            "observation": observation,
        }
    )


def _clean_previous_outputs() -> None:
    known_outputs = [
        "summary.md",
        "keywords.json",
        "mindmap.json",
        "mindmap.png",
        "mindmap.mmd",
        "mindmap",
        "ppt_outline.json",
        "speech_script.md",
        "generated_presentation.pptx",
        "final_video.mp4",
        "subtitles.srt",
        "video_markers.json",
        "video_chapters.md",
        "voice_report.json",
        "run_report.md",
    ]
    for name in known_outputs:
        path = OUTPUT_DIR / name
        if path.exists() and path.is_file():
            try:
                path.unlink(missing_ok=True)
            except (PermissionError, FileNotFoundError):
                continue


def _output_dir(state: AgentState) -> Path:
    return Path(state.get("output_dir") or OUTPUT_DIR)


def read_document_node(state: AgentState) -> AgentState:
    text = read_document(state["file_path"])
    if not text.strip():
        raise ValueError("文档读取成功，但内容为空。")
    state["document_text"] = text
    state["document_preview"] = text[:1500]
    _log(state, "已读取文档并生成文本预览。")
    _trace(
        state,
        "所有生成任务都必须先理解上传文档，因此先调用文档读取工具。",
        "read_document",
        f"读取到 {len(text)} 个字符，预览长度 {len(state['document_preview'])}。",
    )
    return state


def planner_node(state: AgentState) -> AgentState:
    state["plan"] = plan_task(state["user_goal"], state["document_preview"])
    tools = _planned_tools(state)
    state["selected_tools"] = tools
    _log(state, f"已生成动态任务计划：{', '.join(tools)}。")
    _trace(
        state,
        "Planner 根据用户目标和文档预览决定需要哪些工具，并补齐显式目标要求的产物。",
        "plan_task",
        f"选择 {len(tools)} 个工具：{', '.join(tools)}。",
    )
    return state


def summary_node(state: AgentState) -> AgentState:
    state["summary"] = generate_summary(state["document_text"])
    save_summary_markdown(state["summary"], _output_dir(state) / "summary.md")
    _log(state, "已生成文档摘要。")
    _trace(state, "摘要用于压缩资料主题，供大纲和答辩说明复用。", "generate_summary", "已写入 output/summary.md。")
    return state


def keyword_node(state: AgentState) -> AgentState:
    state["keywords"] = extract_keywords(state["document_text"])
    save_json(state["keywords"], _output_dir(state) / "keywords.json")
    count = len(state["keywords"].get("keywords", []))
    _log(state, "已提取关键词。")
    _trace(state, "关键词用于建立知识结构，也能帮助 PPT 聚焦重点。", "extract_keywords", f"提取到 {count} 个关键词。")
    return state


def mindmap_node(state: AgentState) -> AgentState:
    state["mindmap"] = generate_mindmap_structure(state["document_text"])
    save_json(state["mindmap"], _output_dir(state) / "mindmap.json")
    state["mindmap_image_path"] = create_mindmap_image(state["mindmap"], str(_output_dir(state) / "mindmap.png"))
    _log(state, "已生成思维导图结构和可视化文件。")
    _trace(
        state,
        "用户目标需要知识结构展示，因此调用思维导图工具。",
        "generate_mindmap",
        f"已生成 {Path(state['mindmap_image_path']).name}。",
    )
    return state


def outline_node(state: AgentState) -> AgentState:
    _ensure_tool_done(state, "generate_summary")
    _ensure_tool_done(state, "extract_keywords")
    summary_text = state.get("summary", {}).get("summary", "")
    keywords = state.get("keywords", {}).get("keywords", [])
    state["ppt_outline"] = generate_ppt_outline(state["document_text"], summary_text, keywords)
    save_json(state["ppt_outline"], _output_dir(state) / "ppt_outline.json")
    slide_count = len(state["ppt_outline"].get("slides", []))
    _log(state, "已生成 PPT 大纲。")
    _trace(state, "PPT 需要先把资料组织成答辩叙事结构。", "generate_ppt_outline", f"生成 {slide_count} 页大纲。")
    return state


def script_node(state: AgentState) -> AgentState:
    _ensure_tool_done(state, "generate_ppt_outline")
    state["slide_scripts"] = generate_slide_scripts(state["ppt_outline"])
    save_speech_script(state["slide_scripts"], _output_dir(state) / "speech_script.md")
    count = len(state["slide_scripts"].get("scripts", []))
    _log(state, "已生成每页讲稿。")
    _trace(state, "讲稿让 PPT 从展示材料变成可直接答辩的口播材料。", "generate_slide_scripts", f"生成 {count} 页讲稿。")
    return state


def ppt_node(state: AgentState) -> AgentState:
    _ensure_tool_done(state, "generate_ppt_outline")
    _ensure_tool_done(state, "generate_slide_scripts")
    if _tool_requested(state, "generate_mindmap") and not state.get("mindmap_image_path"):
        _ensure_tool_done(state, "generate_mindmap")
    state["ppt_path"] = create_ppt(
        state["ppt_outline"],
        state["slide_scripts"],
        state.get("mindmap_image_path"),
        str(_output_dir(state) / "generated_presentation.pptx"),
    )
    _log(state, "已生成 PPT 文件。")
    _trace(state, "用户目标需要演示文稿，因此把大纲、导图和讲稿写入 PPT 文件。", "create_ppt", "已生成 generated_presentation.pptx。")
    return state


def video_node(state: AgentState) -> AgentState:
    _ensure_tool_done(state, "generate_ppt_outline")
    _ensure_tool_done(state, "generate_slide_scripts")
    voice_enabled = os.getenv("COURSEAGENT_ENABLE_TTS", "true").lower() not in {"0", "false", "no", "off"}
    state["video_path"] = create_explanation_video(
        state["ppt_outline"],
        state["slide_scripts"],
        str(_output_dir(state) / "final_video.mp4"),
        voice_enabled=voice_enabled,
    )
    _log(state, "已生成讲解视频文件。")
    _trace(state, "用户目标需要讲解视频，因此把每页大纲、讲稿和语音合成为带字幕的视频。", "create_video", "已生成 final_video.mp4、字幕、语音报告和时间戳。")
    return state


TOOL_REGISTRY: Dict[str, ToolFunc] = {
    "read_document": read_document_node,
    "generate_summary": summary_node,
    "extract_keywords": keyword_node,
    "generate_mindmap": mindmap_node,
    "generate_ppt_outline": outline_node,
    "generate_slide_scripts": script_node,
    "create_ppt": ppt_node,
    "create_video": video_node,
}


TOOL_ALIASES = {
    "generate_mindmap_structure": "generate_mindmap",
    "create_mindmap_image": "generate_mindmap",
    "generate_ppt": "create_ppt",
    "create_audio_from_scripts": "create_video",
    "create_video_from_slides_and_audio": "create_video",
}


def executor_node(state: AgentState) -> AgentState:
    for tool in _planned_tools(state):
        if tool == "read_document":
            continue
        _ensure_tool_done(state, tool)
    _log(state, "已按动态计划完成工具调用。")
    return state


def verifier_node(state: AgentState) -> AgentState:
    state["verification"] = verify_outputs(state, planned_tools=_planned_tools(state), output_dir=_output_dir(state))
    if not state["verification"].get("ok"):
        _auto_repair(state)
        state["verification"] = verify_outputs(state, planned_tools=_planned_tools(state), output_dir=_output_dir(state))
    if not state["verification"].get("ok"):
        missing = ", ".join(item["name"] for item in state["verification"].get("missing", []))
        raise ValueError(f"以下产物未正确生成：{missing}")
    _log(state, "已完成产物完整性校验。")
    _trace(state, "Verifier 检查计划内产物是否真实存在，并确认文件非空。", "verify_outputs", "计划内产物校验通过。")
    return state


def final_node(state: AgentState) -> AgentState:
    out = _output_dir(state)
    state["report_path"] = create_run_report(state, out / "run_report.md")
    state["artifacts"] = _document_artifacts(out)
    state["manifest_path"] = _write_document_manifest(state, "success" if not state.get("errors") else "failed")
    _log(state, "流程完成，已生成运行报告。")
    return state


def run_agent(file_path: str, user_goal: str, output_dir: str | Path | None = None) -> AgentState:
    """Run CourseAgent as a dynamic Planner + Executor + Verifier workflow."""
    ensure_directories()
    out = Path(output_dir) if output_dir else create_run_dir("document", file_path)
    out.mkdir(parents=True, exist_ok=True)
    fingerprint = _document_fingerprint(file_path, user_goal)
    cached = _find_cached_document(fingerprint)
    if cached and not output_dir:
        return _restore_cached_run(cached, out, file_path, user_goal)
    state: AgentState = {
        "file_path": file_path,
        "user_goal": user_goal,
        "output_dir": str(out),
        "run_id": out.name,
        "logs": [],
        "trace": [],
        "repairs": [],
        "errors": [],
        "timings": {},
        "artifacts": {},
    }
    state["cache_fingerprint"] = fingerprint
    nodes = [
        read_document_node,
        planner_node,
        executor_node,
        verifier_node,
        final_node,
    ]
    for node in nodes:
        try:
            started = time.perf_counter()
            state = node(state)
            state.setdefault("timings", {})[node.__name__] = round(time.perf_counter() - started, 3)
        except Exception as exc:
            message = f"{node.__name__} 执行失败：{exc}"
            state.setdefault("errors", []).append(message)
            _log(state, message)
            try:
                state["report_path"] = create_run_report(state, _output_dir(state) / "run_report.md")
                state["artifacts"] = _document_artifacts(_output_dir(state))
                state["manifest_path"] = _write_document_manifest(state, "failed")
            except Exception:
                pass
            break
    return state


def _planned_tools(state: AgentState) -> List[str]:
    tools: List[str] = []
    for step in state.get("plan", {}).get("steps", []):
        raw_tool = str(step.get("tool", "")).strip()
        tool = TOOL_ALIASES.get(raw_tool, raw_tool)
        if tool in TOOL_REGISTRY and tool not in tools:
            tools.append(tool)
    return tools or ["read_document", "generate_summary", "extract_keywords"]


def _tool_requested(state: AgentState, tool: str) -> bool:
    return tool in _planned_tools(state)


def _ensure_tool_done(state: AgentState, tool: str, force: bool = False) -> AgentState:
    tool = TOOL_ALIASES.get(tool, tool)
    if not force and _is_tool_done(state, tool):
        return state
    if tool not in TOOL_REGISTRY:
        raise ValueError(f"未知工具：{tool}")
    return TOOL_REGISTRY[tool](state)


def _is_tool_done(state: AgentState, tool: str) -> bool:
    checks = {
        "read_document": bool(state.get("document_text")),
        "generate_summary": bool(state.get("summary")),
        "extract_keywords": bool(state.get("keywords")),
        "generate_mindmap": bool(state.get("mindmap_image_path")),
        "generate_ppt_outline": bool(state.get("ppt_outline")),
        "generate_slide_scripts": bool(state.get("slide_scripts")),
        "create_ppt": bool(state.get("ppt_path")) and Path(state["ppt_path"]).exists(),
        "create_video": bool(state.get("video_path")) and Path(state["video_path"]).exists(),
    }
    return checks.get(tool, False)


def _auto_repair(state: AgentState) -> None:
    repair_map = {
        "summary": "generate_summary",
        "keywords": "extract_keywords",
        "mindmap_json": "generate_mindmap",
        "mindmap_visual": "generate_mindmap",
        "ppt_outline": "generate_ppt_outline",
        "speech_script": "generate_slide_scripts",
        "ppt": "create_ppt",
        "video": "create_video",
        "subtitles": "create_video",
        "video_markers": "create_video",
        "video_chapters": "create_video",
        "voice_report": "create_video",
    }
    for item in state.get("verification", {}).get("missing", []):
        name = item.get("name")
        tool = repair_map.get(name)
        if not tool:
            continue
        _trace(state, "Verifier 发现计划内产物缺失，触发自动修复。", f"repair:{tool}", f"修复对象：{name}")
        state.setdefault("repairs", []).append({"artifact": name, "tool": tool})
        _ensure_tool_done(state, tool, force=True)


def _document_artifacts(output_dir: Path) -> Dict[str, str]:
    return collect_artifacts(
        output_dir,
        [
            "summary.md",
            "keywords.json",
            "mindmap.json",
            "mindmap.png",
            "mindmap.mmd",
            "ppt_outline.json",
            "speech_script.md",
            "generated_presentation.pptx",
            "final_video.mp4",
            "narration_audio/narration.mp3",
            "subtitles.srt",
            "video_markers.json",
            "video_chapters.md",
            "voice_report.json",
            "run_report.md",
        ],
    )


def _write_document_manifest(state: AgentState, status: str) -> str:
    out = _output_dir(state)
    artifacts = _document_artifacts(out)
    return write_manifest(
        out,
        {
            "type": "document",
            "status": status,
            "title": Path(state.get("file_path", "")).stem or "document",
            "source_file": state.get("file_path", ""),
            "goal": state.get("user_goal", ""),
            "cache_fingerprint": state.get("cache_fingerprint", ""),
            "selected_tools": state.get("selected_tools", []),
            "artifacts": artifacts,
            "timings": state.get("timings", {}),
            "errors": state.get("errors", []),
            "verification": state.get("verification", {}),
        },
    )


def _document_fingerprint(file_path: str | Path, user_goal: str) -> str:
    settings = get_api_settings()
    digest = hashlib.sha256()
    path = Path(file_path)
    if path.exists():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    digest.update(str(user_goal).encode("utf-8", errors="ignore"))
    digest.update(str(settings.get("provider", "")).encode())
    digest.update(str(settings.get("model", "")).encode())
    digest.update(str(settings.get("mock_mode", "")).encode())
    digest.update(b"courseagent-cache-v1")
    return digest.hexdigest()


def _find_cached_document(fingerprint: str) -> Dict[str, Any] | None:
    for item in list_manifests():
        if (
            item.get("type") == "document"
            and item.get("status") == "success"
            and item.get("cache_fingerprint") == fingerprint
            and Path(str(item.get("run_dir", ""))).exists()
        ):
            return item
    return None


def _restore_cached_run(cached: Dict[str, Any], target_dir: Path, file_path: str, user_goal: str) -> AgentState:
    source_dir = Path(str(cached.get("run_dir", "")))
    for item in source_dir.iterdir():
        target = target_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        elif item.name != "manifest.json":
            shutil.copy2(item, target)
    state: AgentState = {
        "file_path": file_path,
        "user_goal": user_goal,
        "output_dir": str(target_dir),
        "run_id": target_dir.name,
        "selected_tools": list(cached.get("selected_tools", [])),
        "logs": ["命中历史缓存，已复用上次成功产物。"],
        "trace": [],
        "repairs": [],
        "errors": [],
        "timings": {"cache_restore": 0.001},
        "artifacts": _document_artifacts(target_dir),
        "cache_fingerprint": cached.get("cache_fingerprint", ""),
    }
    summary_path = target_dir / "summary.md"
    if summary_path.exists():
        state["summary"] = {"summary": summary_path.read_text(encoding="utf-8", errors="ignore")}
    for key, filename in [("keywords", "keywords.json"), ("mindmap", "mindmap.json"), ("ppt_outline", "ppt_outline.json")]:
        path = target_dir / filename
        if path.exists():
            try:
                state[key] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    script_path = target_dir / "speech_script.md"
    if script_path.exists():
        state["slide_scripts"] = {"scripts": []}
    if (target_dir / "mindmap.png").exists():
        state["mindmap_image_path"] = str(target_dir / "mindmap.png")
    elif (target_dir / "mindmap.mmd").exists():
        state["mindmap_image_path"] = str(target_dir / "mindmap.mmd")
    if (target_dir / "generated_presentation.pptx").exists():
        state["ppt_path"] = str(target_dir / "generated_presentation.pptx")
    if (target_dir / "final_video.mp4").exists():
        state["video_path"] = str(target_dir / "final_video.mp4")
    state["verification"] = verify_outputs(state, planned_tools=state.get("selected_tools", []), output_dir=target_dir)
    state["report_path"] = str(target_dir / "run_report.md") if (target_dir / "run_report.md").exists() else None
    state["manifest_path"] = write_manifest(
        target_dir,
        {
            "type": "document",
            "status": "success",
            "title": Path(file_path).stem or "document",
            "source_file": file_path,
            "goal": user_goal,
            "cache_fingerprint": cached.get("cache_fingerprint", ""),
            "cache_hit": True,
            "source_run_id": cached.get("run_id", ""),
            "selected_tools": state.get("selected_tools", []),
            "artifacts": state.get("artifacts", {}),
            "timings": state.get("timings", {}),
            "errors": [],
            "verification": state.get("verification", {}),
        },
    )
    return state
