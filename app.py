from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from agent_graph import run_agent
from config import OUTPUT_DIR, PROVIDER_PRESETS, UPLOAD_DIR, ensure_directories, get_api_settings
from tools.history_tool import collect_artifacts, create_run_dir, delete_run, list_manifests, set_pinned, write_manifest
from tools.llm_client import test_llm_connection
from tools.video_analysis_tool import analyze_course_video


ensure_directories()
st.set_page_config(page_title="CourseAgent", layout="wide")

DEFAULT_GOAL = "请把这份课程资料整理成 5 分钟课堂答辩 PPT，并生成摘要、关键词、思维导图、每页讲稿、讲解视频、字幕和重点时间戳。"
DEMO_TEXT = """
软件交互设计课程资料：交互设计过程通常包含 Design Discovery、Design Exploration、Evaluate 和 Production。
Design Discovery 关注客户、产品、业务、市场与技术背景，明确设计问题、目标用户角色、用户任务和设计方向。
Design Exploration 会通过方案提案、演示、低保真原型和故事板探索可能的界面方案。
Design 阶段强调需求驱动，设计关注 artifact 的用途，而不是一开始讨论如何实现。
界面设计的表达形式包括屏幕草图、故事板、流程图、任务结构 outline 和可执行原型。
Task Analysis 与 Contextual Inquiry 通过观察现有工作实践、创建真实使用场景、发现关键任务来支撑设计。
Evaluate with Customers 需要与客户共同评价方案，并根据反馈 Review & Iterate，最终形成基于产品现实的高保真精化设计和规格说明。
""".strip()


def inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ca-bg: #f5f7fb;
            --ca-surface: #ffffff;
            --ca-surface-soft: #f8fafc;
            --ca-border: #dbe3ef;
            --ca-ink: #101828;
            --ca-muted: #667085;
            --ca-blue: #2563eb;
            --ca-cyan: #0891b2;
            --ca-green: #059669;
            --ca-red: #ef4444;
            --ca-yellow: #facc15;
        }
        .stApp { background: var(--ca-bg); }
        .block-container { padding-top: 1.25rem; padding-bottom: 3.5rem; max-width: 1360px; }
        .topbar {
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.8fr);
            gap: 18px;
            border: 1px solid #d7e0ee;
            background: linear-gradient(135deg, #ffffff 0%, #eef6ff 58%, #ecfdf5 100%);
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
            overflow: hidden;
        }
        .topbar h1 { margin: 0 0 9px 0; color: var(--ca-ink); font-size: 32px; line-height: 1.18; letter-spacing: 0; }
        .topbar p { margin: 0; color: #475569; font-size: 15px; line-height: 1.65; max-width: 820px; }
        .hero-kicker {
            color: var(--ca-blue);
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 8px;
        }
        .hero-panel {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            padding: 16px;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
        }
        .hero-panel-title {
            color: var(--ca-ink);
            font-size: 13px;
            font-weight: 800;
            margin-bottom: 12px;
        }
        .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
        .metric-tile {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            padding: 10px;
            min-height: 64px;
        }
        .metric-label { color: #64748b; font-size: 11px; font-weight: 700; margin-bottom: 5px; }
        .metric-value { color: var(--ca-ink); font-size: 13px; font-weight: 800; word-break: break-word; }
        .status-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
        .chip {
            border: 1px solid #bfdbfe;
            background: #eff6ff;
            color: #1e40af;
            padding: 6px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
        }
        .section-head {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: end;
            margin: 22px 0 12px;
            padding-top: 2px;
        }
        .section-kicker {
            color: var(--ca-blue);
            font-size: 12px;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 3px;
        }
        .section-title { color: var(--ca-ink); font-size: 22px; font-weight: 850; margin: 18px 0 10px; letter-spacing: 0; }
        .section-head .section-title { margin: 0; }
        .section-note { color: var(--ca-muted); font-size: 13px; line-height: 1.55; max-width: 520px; text-align: right; }
        .workflow-strip {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
            margin: 4px 0 16px;
        }
        .workflow-step {
            border: 1px solid var(--ca-border);
            background: var(--ca-surface);
            border-radius: 8px;
            padding: 11px 12px;
            min-height: 82px;
        }
        .workflow-step strong {
            display: block;
            color: var(--ca-ink);
            font-size: 13px;
            margin-bottom: 5px;
        }
        .workflow-step span { color: var(--ca-muted); font-size: 12px; line-height: 1.45; }
        .workspace-note {
            border: 1px solid #bfdbfe;
            background: #eff6ff;
            color: #1e3a8a;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 13px;
            line-height: 1.55;
            margin: 8px 0 14px;
        }
        .artifact {
            border: 1px solid var(--ca-border);
            background: var(--ca-surface);
            border-radius: 8px;
            padding: 15px 16px;
            min-height: 112px;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }
        .artifact-title { color: var(--ca-ink); font-size: 16px; font-weight: 800; margin-bottom: 5px; }
        .artifact-meta { color: var(--ca-muted); font-size: 13px; line-height: 1.55; }
        .trace-card {
            border-left: 4px solid var(--ca-blue);
            background: var(--ca-surface);
            padding: 12px 14px;
            border-radius: 8px;
            margin-bottom: 10px;
            border-top: 1px solid var(--ca-border);
            border-right: 1px solid var(--ca-border);
            border-bottom: 1px solid var(--ca-border);
        }
        .trace-card strong { color: var(--ca-ink); }
        .trace-card span { color: #475569; font-size: 13px; line-height: 1.55; }
        .timeline-wrap { margin: 8px 0 12px; }
        .timeline-track {
            position: relative;
            height: 44px;
            border-radius: 8px;
            background: linear-gradient(90deg, #dbeafe, #ccfbf1, #fef3c7);
            border: 1px solid var(--ca-border);
            overflow: hidden;
        }
        .timeline-marker {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 2px;
            background: #0f172a;
        }
        .timeline-label {
            position: absolute;
            top: 7px;
            transform: translateX(-4px);
            color: var(--ca-ink);
            font-size: 11px;
            font-weight: 700;
            white-space: nowrap;
        }
        .marker-card {
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            padding: 10px 12px;
            background: var(--ca-surface);
            margin-bottom: 8px;
        }
        .marker-card strong { color: var(--ca-ink); }
        .marker-card span { color: var(--ca-muted); font-size: 13px; line-height: 1.55; }
        mark {
            background: #fef08a;
            color: #111827;
            padding: 1px 4px;
            border-radius: 4px;
        }
        .keypoint-card {
            border: 1px solid var(--ca-border);
            border-left: 4px solid var(--ca-blue);
            border-radius: 8px;
            padding: 10px 12px;
            background: var(--ca-surface);
            margin-bottom: 8px;
        }
        .keypoint-card strong { color: var(--ca-ink); }
        .keypoint-card span { color: #475569; font-size: 13px; }
        div[data-testid="stFileUploader"] section {
            border-radius: 8px;
            border: 1px dashed #60a5fa;
            background: #f8fafc;
            min-height: 92px;
            padding: 18px 16px;
        }
        div[data-testid="stFileUploader"] section:hover { border-color: var(--ca-blue); background: #eff6ff; }
        div[data-testid="stFileUploader"] button {
            min-width: 128px;
            padding-left: 16px;
            padding-right: 16px;
        }
        div[data-testid="stFileUploader"] small {
            color: #64748b;
        }
        textarea,
        input {
            background: #ffffff !important;
            color: var(--ca-ink) !important;
            border-color: #cbd5e1 !important;
            border-radius: 8px !important;
        }
        textarea:focus,
        input:focus {
            border-color: var(--ca-blue) !important;
            box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
        }
        div[data-baseweb="select"] > div {
            background: #ffffff !important;
            color: var(--ca-ink) !important;
            border-color: #cbd5e1 !important;
            border-radius: 8px !important;
        }
        label, p {
            color: var(--ca-ink);
        }
        div.stDownloadButton > button, div.stButton > button {
            border-radius: 8px;
            min-height: 42px;
            font-weight: 750;
            border: 1px solid #cbd5e1;
        }
        div.stButton > button[kind="primary"] {
            background: var(--ca-red);
            border-color: var(--ca-red);
            color: #ffffff;
        }
        div.stButton > button[kind="primary"]:hover {
            background: #dc2626;
            border-color: #dc2626;
        }
        div[data-testid="stTabs"] button {
            font-weight: 800;
            color: #475569;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--ca-red);
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        section[data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--ca-border);
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--ca-ink);
        }
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #475569 !important;
        }
        .sidebar-status {
            border: 1px solid var(--ca-border);
            border-radius: 8px;
            background: #f8fafc;
            padding: 12px;
            margin: 8px 0 14px;
        }
        .sidebar-status div {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            color: var(--ca-muted);
            font-size: 12px;
            padding: 4px 0;
        }
        .sidebar-status strong { color: var(--ca-ink); font-size: 12px; text-align: right; }
        @media (max-width: 900px) {
            .topbar { grid-template-columns: 1fr; padding: 18px; }
            .metric-grid { grid-template-columns: 1fr; }
            .workflow-strip { grid-template-columns: 1fr; }
            .section-head { display: block; }
            .section-note { text-align: left; margin-top: 6px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def safe_filename(name: str) -> str:
    path = Path(name)
    stem = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", path.stem).strip("_") or "upload"
    return f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix.lower()}"


def file_size(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return "未生成"
    size = p.stat().st_size
    return f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"


def download_button(label: str, path: str | Path, mime: str, key: str) -> None:
    file_path = Path(path)
    if file_path.exists():
        st.download_button(label, file_path.read_bytes(), file_name=file_path.name, mime=mime, key=key, use_container_width=True)
    else:
        st.button(f"{label}（未生成）", disabled=True, use_container_width=True, key=f"disabled_{key}")


def save_uploaded_file(uploaded_file: Any) -> Path:
    upload_path = UPLOAD_DIR / safe_filename(uploaded_file.name)
    upload_path.write_bytes(uploaded_file.getbuffer())
    return upload_path


def save_demo_file() -> Path:
    demo_path = UPLOAD_DIR / "demo_interaction_design.txt"
    demo_path.write_text(DEMO_TEXT, encoding="utf-8")
    return demo_path


def run_and_store(file_path: Path, user_goal: str) -> None:
    st.session_state["last_file_path"] = str(file_path)
    with st.spinner("正在读取文档、规划任务、生成 PPT / 视频 / 导图..."):
        st.session_state["agent_state"] = run_agent(str(file_path), user_goal)
        st.session_state["active_detail_state"] = st.session_state["agent_state"]


def artifact_card(title: str, path: str | Path, note: str) -> None:
    st.markdown(
        f"""
        <div class="artifact">
          <div class="artifact-title">{html.escape(title)}</div>
          <div class="artifact-meta">{html.escape(note)}</div>
          <div class="artifact-meta">{html.escape(Path(path).name)} · {html.escape(file_size(path))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_json_file(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return default


TOOL_LABELS = {
    "read_document": "读取课程文档",
    "generate_summary": "生成摘要",
    "extract_keywords": "提取关键词",
    "generate_mindmap": "生成思维导图",
    "generate_ppt_outline": "生成 PPT 大纲",
    "generate_slide_scripts": "生成逐页讲稿",
    "create_ppt": "生成 PPT 文件",
    "create_video": "合成讲解视频",
    "transcribe_video": "识别课堂字幕",
    "read_uploaded_subtitles": "读取上传字幕",
    "analyze_course_video": "分析课堂视频",
    "generate_video_mindmap": "生成视频导图",
}


TOOL_OBSERVATIONS = {
    "read_document": "已读取上传资料并生成文本预览。",
    "generate_summary": "已生成与课程内容匹配的摘要。",
    "extract_keywords": "已提取课程核心概念和关键词。",
    "generate_mindmap": "已生成知识结构导图。",
    "generate_ppt_outline": "已生成 PPT 页面结构。",
    "generate_slide_scripts": "已生成逐页讲稿。",
    "create_ppt": "已输出 generated_presentation.pptx。",
    "create_video": "已输出讲解视频、字幕和重点时间戳。",
    "transcribe_video": "已得到课堂视频字幕或使用上传 SRT。",
    "read_uploaded_subtitles": "已读取用户上传的 SRT 字幕。",
    "analyze_course_video": "已生成知识点总结、时间戳和 highlight。",
    "generate_video_mindmap": "已生成课堂视频思维导图。",
}


def _display_tool_name(tool: str) -> str:
    return TOOL_LABELS.get(tool, tool)


def _state_artifacts(state: dict[str, Any]) -> dict[str, str]:
    artifacts = state.get("artifacts") or {}
    if artifacts:
        return artifacts
    output_value = state.get("output_dir") or state.get("run_dir")
    if not output_value:
        return {}
    output_dir = Path(output_value)
    if output_dir.exists():
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
                "subtitles.srt",
                "video_markers.json",
                "video_chapters.md",
                "run_report.md",
                "course_video_analysis.md",
                "course_video_analysis.json",
                "course_video_markers.json",
                "course_video_highlights.md",
                "course_video_mindmap.json",
                "course_video_mindmap.png",
                "course_video_mindmap.mmd",
                "course_video_transcript.txt",
                "course_video_auto_subtitles.srt",
            ],
        )
    return {}


def _infer_tools_from_artifacts(state: dict[str, Any]) -> list[str]:
    artifacts = _state_artifacts(state)
    if state.get("type") == "course_video" or any(str(name).startswith("course_video_") for name in artifacts):
        tools = ["read_uploaded_subtitles" if state.get("subtitle_file") else "transcribe_video", "analyze_course_video", "generate_video_mindmap"]
        return [tool for tool in tools if tool]
    tools = ["read_document"]
    if "summary.md" in artifacts:
        tools.append("generate_summary")
    if "keywords.json" in artifacts:
        tools.append("extract_keywords")
    if "mindmap.png" in artifacts or "mindmap.mmd" in artifacts:
        tools.append("generate_mindmap")
    if "ppt_outline.json" in artifacts:
        tools.append("generate_ppt_outline")
    if "speech_script.md" in artifacts:
        tools.append("generate_slide_scripts")
    if "generated_presentation.pptx" in artifacts:
        tools.append("create_ppt")
    if "final_video.mp4" in artifacts or "subtitles.srt" in artifacts:
        tools.append("create_video")
    return tools


def normalize_execution_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    normalized = dict(state)
    normalized["artifacts"] = _state_artifacts(normalized)
    artifacts = normalized["artifacts"]
    if not normalized.get("summary") and artifacts.get("summary.md"):
        summary_path = Path(artifacts["summary.md"])
        if summary_path.exists():
            normalized["summary"] = {"summary": summary_path.read_text(encoding="utf-8", errors="ignore")}
    if not normalized.get("keywords") and artifacts.get("keywords.json"):
        keywords = load_json_file(artifacts["keywords.json"], {})
        if isinstance(keywords, dict):
            normalized["keywords"] = keywords
    if not normalized.get("ppt_outline") and artifacts.get("ppt_outline.json"):
        outline = load_json_file(artifacts["ppt_outline.json"], {})
        if isinstance(outline, dict):
            normalized["ppt_outline"] = outline
    if not normalized.get("slide_scripts") and artifacts.get("speech_script.md"):
        script_path = Path(artifacts["speech_script.md"])
        if script_path.exists():
            normalized["slide_scripts"] = {"raw_markdown": script_path.read_text(encoding="utf-8", errors="ignore")}
    selected = list(normalized.get("selected_tools") or [])
    if not selected:
        selected = _infer_tools_from_artifacts(normalized)
    normalized["selected_tools"] = selected
    if not normalized.get("plan"):
        if normalized.get("type") == "course_video":
            strategy = "课堂视频分析工作流"
            reasoning = "根据课堂视频或字幕生成知识点总结、重点时间戳、highlight 和思维导图。"
        else:
            strategy = "课程文档生成工作流"
            reasoning = "根据用户目标选择文档解析、摘要、关键词、思维导图、PPT、讲稿和视频合成工具。"
        normalized["plan"] = {
            "goal": normalized.get("goal") or normalized.get("user_goal") or normalized.get("title") or "课程资料处理",
            "strategy": strategy,
            "reasoning": reasoning,
            "steps": [{"tool": tool, "name": _display_tool_name(tool)} for tool in selected],
        }
    if not normalized.get("trace"):
        normalized["trace"] = [
            {
                "step": index,
                "thought": f"根据任务目标需要执行“{_display_tool_name(tool)}”。",
                "action": tool,
                "observation": TOOL_OBSERVATIONS.get(tool, "已完成该工具步骤。"),
            }
            for index, tool in enumerate(selected, start=1)
        ]
    if not normalized.get("logs"):
        logs = []
        if normalized.get("cache_hit"):
            logs.append("命中历史缓存，已复用上次成功产物。")
        logs.extend(TOOL_OBSERVATIONS.get(tool, f"已完成 {_display_tool_name(tool)}。") for tool in selected)
        if normalized.get("verification", {}).get("ok") is True or normalized.get("status") == "success":
            logs.append("产物完整性校验通过。")
        normalized["logs"] = logs
    return normalized


def _is_course_video_state(state: dict[str, Any]) -> bool:
    artifacts = state.get("artifacts") or {}
    return state.get("type") == "course_video" or any(str(name).startswith("course_video_") for name in artifacts)


def _artifact_path(state: dict[str, Any], name: str) -> Path | None:
    artifacts = state.get("artifacts") or {}
    value = artifacts.get(name)
    if not value:
        return None
    return Path(value)


def _load_video_analysis_from_state(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("analysis") or state.get("markers"):
        return state
    analysis_path = _artifact_path(state, "course_video_analysis.json")
    if analysis_path:
        payload = load_json_file(analysis_path, {})
        if isinstance(payload, dict):
            return payload
    return {}


def _load_video_markers_from_state(state: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    markers = report.get("markers") or state.get("markers") or []
    if markers:
        return markers
    markers_path = _artifact_path(state, "course_video_markers.json")
    if markers_path:
        payload = load_json_file(markers_path, [])
        if isinstance(payload, list):
            return payload
    return []


def render_marker_timeline(markers: list[dict[str, Any]]) -> None:
    if not markers:
        st.info("暂未生成重点时间戳。")
        return
    duration = max(float(item.get("end", 0)) for item in markers) or 1.0
    marker_html = ['<div class="timeline-wrap"><div class="timeline-track">']
    for item in markers:
        start = float(item.get("start", 0))
        left = max(0, min(100, start / duration * 100))
        label = html.escape(f"{seconds_to_clock(start)} P{item.get('page', '')}")
        marker_html.append(f'<div class="timeline-marker" style="left:{left:.2f}%"></div>')
        marker_html.append(f'<div class="timeline-label" style="left:{left:.2f}%">{label}</div>')
    marker_html.append("</div></div>")
    st.markdown("".join(marker_html), unsafe_allow_html=True)


def render_marker_summary(markers: list[dict[str, Any]]) -> None:
    if not markers:
        return
    st.markdown("##### 时间戳概要提炼")
    for item in markers:
        start = seconds_to_clock(float(item.get("start", 0)))
        end = seconds_to_clock(float(item.get("end", 0)))
        title = html.escape(str(item.get("title", "")))
        summary = html.escape(str(item.get("summary", "")))
        st.markdown(
            f"""
            <div class="marker-card">
              <strong>{start} - {end} · {title}</strong><br>
              <span>{summary}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def seconds_to_clock(value: float) -> str:
    minutes = int(value // 60)
    seconds = int(value % 60)
    return f"{minutes:02d}:{seconds:02d}"


def render_artifact_overview(state: dict[str, Any], key_prefix: str = "workspace") -> None:
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Generated assets</div>
            <div class="section-title">生成产物</div>
          </div>
          <div class="section-note">优先展示最常用的交付文件，更多中间文件和日志在下方详情里查看。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    verification = state.get("verification", {})
    if verification.get("ok"):
        st.success("产物完整性校验通过。PPT、视频、字幕、导图和报告已生成。")
    elif verification:
        st.warning("产物完整性校验未通过，请查看执行日志。")

    output_dir = Path(state.get("output_dir") or OUTPUT_DIR)
    paths = {
        "summary": output_dir / "summary.md",
        "mindmap": Path(state.get("mindmap_image_path") or output_dir / "mindmap.png"),
        "ppt": output_dir / "generated_presentation.pptx",
        "video": output_dir / "final_video.mp4",
        "subtitles": output_dir / "subtitles.srt",
        "markers": output_dir / "video_markers.json",
        "chapters": output_dir / "video_chapters.md",
        "voice_report": output_dir / "voice_report.json",
        "narration_audio": output_dir / "narration_audio" / "narration.mp3",
        "script": output_dir / "speech_script.md",
        "report": output_dir / "run_report.md",
    }

    col1, col2, col3 = st.columns(3)
    with col1:
        artifact_card("文档摘要", paths["summary"], "从上传资料中提炼主题和重点")
        download_button("下载摘要", paths["summary"], "text/markdown", f"{key_prefix}_summary_top")
    with col2:
        artifact_card("答辩 PPT", paths["ppt"], "按资料逻辑生成演示文稿")
        download_button("下载 PPT", paths["ppt"], "application/vnd.openxmlformats-officedocument.presentationml.presentation", f"{key_prefix}_ppt_top")
    with col3:
        artifact_card("讲解视频", paths["video"], "含字幕、章节和重点时间戳")
        download_button("下载视频", paths["video"], "video/mp4", f"{key_prefix}_video_top")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### 思维导图预览")
        mindmap_path = paths["mindmap"]
        if mindmap_path.suffix.lower() == ".png" and mindmap_path.exists():
            st.image(str(mindmap_path), use_container_width=True)
        elif mindmap_path.exists():
            st.code(mindmap_path.read_text(encoding="utf-8"), language="mermaid")
        else:
            st.info("思维导图尚未生成。")
        download_button("下载思维导图", mindmap_path, "image/png" if mindmap_path.suffix.lower() == ".png" else "text/plain", f"{key_prefix}_mindmap_top")

    with right:
        st.markdown("#### 讲解视频预览")
        markers = load_json_file(paths["markers"], [])
        voice_report = load_json_file(paths["voice_report"], {})
        render_marker_timeline(markers)
        if paths["video"].exists():
            st.video(str(paths["video"]))
        else:
            st.info("讲解视频尚未生成。")
        if voice_report:
            if voice_report.get("ok"):
                st.success(f"已合成语音讲解：{voice_report.get('voice', '')}")
            else:
                st.warning(f"语音讲解未合成，当前视频为字幕版：{voice_report.get('message', '')}")
        render_marker_summary(markers)
        cols = st.columns(2)
        with cols[0]:
            download_button("下载字幕 SRT", paths["subtitles"], "text/plain", f"{key_prefix}_subtitles_top")
            download_button("下载重点时间戳", paths["markers"], "application/json", f"{key_prefix}_markers_top")
            download_button("下载讲解音频", paths["narration_audio"], "audio/mpeg", f"{key_prefix}_narration_top")
        with cols[1]:
            download_button("下载讲稿", paths["script"], "text/markdown", f"{key_prefix}_script_top")
            download_button("下载视频章节", paths["chapters"], "text/markdown", f"{key_prefix}_chapters_top")
            download_button("下载语音报告", paths["voice_report"], "application/json", f"{key_prefix}_voice_report_top")
        download_button("下载运行报告", paths["report"], "text/markdown", f"{key_prefix}_report_top")


def render_details(state: dict[str, Any]) -> None:
    state = normalize_execution_state(state) or {}
    is_video_state = _is_course_video_state(state)
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Execution details</div>
            <div class="section-title">内容详情</div>
          </div>
          <div class="section-note">保留 Agent 决策、执行轨迹、PPT 大纲、讲稿和完整下载入口，便于追溯与复用。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    output_dir = Path(state.get("output_dir") or OUTPUT_DIR)
    run_key = str(state.get("run_id") or "current")
    tab_labels = (
        ["Agent 决策", "执行轨迹", "视频总结", "时间戳与导图", "执行日志", "全部下载"]
        if is_video_state
        else ["Agent 决策", "执行轨迹", "摘要与关键词", "PPT 大纲与讲稿", "执行日志", "全部下载"]
    )
    plan_tab, trace_tab, content_tab, outline_tab, log_tab, file_tab = st.tabs(
        tab_labels
    )

    with plan_tab:
        plan = state.get("plan", {})
        st.write(f"**策略：** {plan.get('strategy', '动态工具调用')}")
        if plan.get("reasoning"):
            st.info(plan.get("reasoning"))
        selected = state.get("selected_tools", [])
        if selected:
            st.write(" -> ".join(_display_tool_name(tool) for tool in selected))
        st.json(plan)

    with trace_tab:
        for item in state.get("trace", []):
            st.markdown(
                f"""
                <div class="trace-card">
                  <strong>Step {item.get('step')} · {html.escape(_display_tool_name(str(item.get('action', ''))))}</strong><br>
                  <span>Thought：{html.escape(str(item.get('thought', '')))}</span><br>
                  <span>Observation：{html.escape(str(item.get('observation', '')))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if not state.get("trace"):
            st.info("这次运行没有记录执行轨迹。新运行会自动写入，历史运行会尽量根据产物推断。")
        if state.get("repairs"):
            st.markdown("### 自动修复记录")
            st.json(state.get("repairs", []))

    with content_tab:
        if is_video_state:
            report = _load_video_analysis_from_state(state)
            analysis = report.get("analysis", report)
            summary_text = str(analysis.get("summary") or report.get("summary") or "")
            keywords = report.get("keywords") or analysis.get("keywords") or []
            st.markdown("### 课堂视频总结")
            if summary_text:
                st.markdown(_highlight_html(summary_text, keywords), unsafe_allow_html=True)
            else:
                st.info("暂未读取到视频总结文本。")
            st.markdown("### 核心知识点")
            key_points = analysis.get("key_points") or report.get("key_points") or []
            if key_points:
                for item in key_points:
                    title = html.escape(str(item.get("title", "知识点")))
                    explanation = html.escape(str(item.get("explanation", "")))
                    evidence = html.escape(str(item.get("evidence", "")))
                    st.markdown(
                        f"""
                        <div class="keypoint-card">
                          <strong>{title}</strong><br>
                          <span>{explanation}</span><br>
                          <span>{evidence}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            elif keywords:
                st.write("、".join(str(item) for item in keywords))
        else:
            st.markdown("### 文档摘要")
            st.write(state.get("summary", {}).get("summary", ""))
            st.markdown("### 关键词")
            st.write("、".join(state.get("keywords", {}).get("keywords", [])))

    with outline_tab:
        if is_video_state:
            report = _load_video_analysis_from_state(state)
            markers = _load_video_markers_from_state(state, report)
            st.markdown("### 重点时间戳")
            render_marker_timeline(markers)
            render_marker_summary(markers)
            mindmap_path = _artifact_path(state, "course_video_mindmap.png") or _artifact_path(state, "course_video_mindmap.mmd")
            if mindmap_path and mindmap_path.exists():
                st.markdown("### 视频思维导图")
                if mindmap_path.suffix.lower() == ".png":
                    st.image(str(mindmap_path), use_container_width=True)
                else:
                    st.code(mindmap_path.read_text(encoding="utf-8"), language="mermaid")
        else:
            slides = state.get("ppt_outline", {}).get("slides", [])
            for slide in slides:
                with st.container(border=True):
                    st.markdown(f"**第 {slide.get('page')} 页：{slide.get('title')}**")
                    for bullet in slide.get("bullets", []):
                        st.write(f"- {bullet}")
                    script = next(
                        (item.get("script", "") for item in state.get("slide_scripts", {}).get("scripts", []) if item.get("page") == slide.get("page")),
                        "",
                    )
                    if script:
                        st.caption(script)
            raw_script = state.get("slide_scripts", {}).get("raw_markdown")
            if raw_script and not slides:
                st.markdown("### 讲稿")
                st.markdown(raw_script)

    with log_tab:
        if state.get("verification"):
            st.markdown("### Verifier 校验")
            st.json(state.get("verification", {}))
        for log in state.get("logs", []):
            st.write(f"- {log}")

    with file_tab:
        _render_manifest_downloads(state, f"{run_key}_details")


def render_results(state: dict[str, Any]) -> None:
    if state.get("errors"):
        st.error("流程执行时遇到问题。")
        for error in state["errors"]:
            st.error(error)
        if state.get("logs"):
            with st.expander("查看已完成日志"):
                for log in state.get("logs", []):
                    st.write(f"- {log}")
        return
    render_artifact_overview(state)
    render_details(state)


def render_document_workflow(demo_clicked: bool) -> None:
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Course document workflow</div>
            <div class="section-title">课程文档生成</div>
          </div>
          <div class="section-note">上传课程资料后，Agent 会规划工具链并生成摘要、关键词、思维导图、PPT、讲稿、讲解视频、字幕和时间戳。</div>
        </div>
        <div class="workflow-strip">
          <div class="workflow-step"><strong>1. 上传资料</strong><span>支持 PDF、DOCX、TXT 课程文档</span></div>
          <div class="workflow-step"><strong>2. Agent 规划</strong><span>自动选择摘要、导图、PPT、视频等工具</span></div>
          <div class="workflow-step"><strong>3. 内容生成</strong><span>生成摘要、关键词、讲稿和展示结构</span></div>
          <div class="workflow-step"><strong>4. 产物校验</strong><span>检查缺失产物并尝试自动修复</span></div>
          <div class="workflow-step"><strong>5. 下载交付</strong><span>PPT、视频、字幕、时间戳和报告</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    input_col, goal_col = st.columns([0.95, 1.05])

    with input_col:
        uploaded_file = st.file_uploader("上传课程文档", type=["txt", "docx", "pdf"], key="document_upload")
        if uploaded_file is not None:
            st.success(f"已选择文件：{uploaded_file.name}，点击下方按钮即可分析。")
        else:
            st.info("请选择文件后点击“分析上传文件并生成全部材料”，也可以使用左侧示例演示。")

    with goal_col:
        user_goal = st.text_area("任务目标", value=DEFAULT_GOAL, height=128, key="document_goal")

    st.markdown(
        '<div class="workspace-note">建议保持任务目标具体：说明时长、用途、输出材料和讲解风格。系统会优先遵循上传资料内容，避免生成与课程无关的信息。</div>',
        unsafe_allow_html=True,
    )

    run_col, demo_col = st.columns([1.3, 0.7])
    with run_col:
        run_clicked = st.button("分析上传文件并生成全部材料", type="primary", use_container_width=True)
    with demo_col:
        inline_demo_clicked = st.button("示例一键演示", use_container_width=True)

    if demo_clicked or inline_demo_clicked:
        run_and_store(save_demo_file(), user_goal)

    if run_clicked:
        if uploaded_file is None:
            st.warning("还没有选择文件。请先上传 .txt、.docx 或 .pdf 文件。")
        else:
            run_and_store(save_uploaded_file(uploaded_file), user_goal)

    state = st.session_state.get("agent_state")
    if state:
        if state.get("errors"):
            st.error("最近一次流程执行时遇到问题，请到“运行详情”查看日志。")
        else:
            st.success("最近一次文档工作流已完成。结果可在“产物中心”集中查看和下载。")
            render_artifact_overview(state)


def render_asset_center_legacy(state: dict[str, Any] | None) -> None:
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Delivery center</div>
            <div class="section-title">产物中心</div>
          </div>
          <div class="section-note">集中管理课程文档生成和课堂视频分析的交付文件，避免下载入口散落在各个流程中。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if state:
        if state.get("errors"):
            st.warning("最近一次文档任务未完整完成，以下文件可能来自上一次成功运行。")
        else:
            render_artifact_overview(state)
    else:
        st.info("还没有运行课程文档生成流程。生成后这里会展示摘要、PPT、思维导图、讲解视频、字幕和报告。")

    video_report = st.session_state.get("course_video_analysis_report")
    st.markdown("#### 课堂视频分析产物")
    if video_report:
        col1, col2, col3 = st.columns(3)
        with col1:
            download_button("视频分析报告", video_report["analysis_markdown"], "text/markdown", "asset_video_analysis_md")
            download_button("视频分析 JSON", video_report["analysis_json"], "application/json", "asset_video_analysis_json")
        with col2:
            download_button("视频思维导图", video_report["mindmap_visual"], "image/png", "asset_video_mindmap")
            download_button("视频时间戳", video_report["markers_path"], "application/json", "asset_video_markers")
        with col3:
            download_button("视频字幕 SRT", video_report["subtitles_path"], "text/plain", "asset_video_srt")
            download_button("高亮摘要", video_report["highlights_markdown"], "text/markdown", "asset_video_highlights")
    else:
        st.info("还没有运行课堂视频分析。完成分析后，这里会展示视频摘要、思维导图、时间戳和 Highlight 文件。")


def _filter_runs(runs: list[dict[str, Any]], selected_filter: str) -> list[dict[str, Any]]:
    if selected_filter == "文档生成":
        return [item for item in runs if item.get("type") == "document"]
    if selected_filter == "视频分析":
        return [item for item in runs if item.get("type") == "course_video"]
    if selected_filter == "已固定":
        return [item for item in runs if item.get("pinned")]
    if selected_filter == "失败记录":
        return [item for item in runs if item.get("status") != "success"]
    return runs


def _run_label(item: dict[str, Any]) -> str:
    type_label = "文档" if item.get("type") == "document" else "视频"
    title = item.get("title") or item.get("run_id")
    return f"{item.get('created_at', '')} · {type_label} · {title}"


def _artifact_label(name: str) -> str:
    labels = {
        "generated_presentation.pptx": "PPT",
        "final_video.mp4": "讲解视频",
        "summary.md": "摘要",
        "mindmap.png": "思维导图",
        "mindmap.mmd": "思维导图",
        "speech_script.md": "讲稿",
        "run_report.md": "运行报告",
        "course_video_analysis.md": "视频分析报告",
        "course_video_markers.json": "视频时间戳",
        "course_video_highlights.md": "Highlight 摘要",
        "course_video_mindmap.png": "视频思维导图",
    }
    return labels.get(name, Path(name).name)


def _mime_for_path(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".json":
        return "application/json"
    if suffix == ".png":
        return "image/png"
    return "text/plain"


def file_size_text(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _render_manifest_downloads(item: dict[str, Any], key_prefix: str) -> None:
    artifacts = item.get("artifacts") or {}
    if not artifacts:
        st.info("这条记录还没有可下载产物。")
        return
    columns = st.columns(3)
    for index, (name, path) in enumerate(artifacts.items()):
        with columns[index % 3]:
            download_button(_artifact_label(name), path, _mime_for_path(path), f"{key_prefix}_{name}")


def _render_history_detail(item: dict[str, Any]) -> None:
    run_id = str(item.get("run_id", "run"))
    st.markdown("#### 展示与下载")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("固定为展示版本", key=f"pin_{run_id}", use_container_width=True):
            set_pinned(run_id)
            st.rerun()
    with c2:
        if st.button("刷新历史", key=f"refresh_{run_id}", use_container_width=True):
            st.rerun()
    with c3:
        if st.button("删除记录", key=f"delete_{run_id}", use_container_width=True):
            delete_run(run_id)
            st.rerun()
    if st.button("在运行详情中查看", key=f"detail_{run_id}", use_container_width=True):
        st.session_state["active_detail_state"] = item
        st.rerun()
    _render_manifest_downloads(item, run_id)

    st.markdown("#### 运行信息")
    total = sum(float(value) for value in (item.get("timings") or {}).values())
    st.write(f"类型：{'文档生成' if item.get('type') == 'document' else '视频分析'}")
    st.write(f"状态：{item.get('status', '')}")
    st.write(f"生成时间：{item.get('created_at', '')}")
    st.write(f"总耗时记录：{total:.1f} 秒" if total else "总耗时记录：暂无")
    st.write(f"目录：{item.get('run_dir', '')}")
    if item.get("errors"):
        st.error("；".join(str(error) for error in item.get("errors", [])))
    with st.expander("查看 manifest"):
        st.json(item)


def render_asset_center(state: dict[str, Any] | None) -> None:
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Delivery center</div>
            <div class="section-title">产物中心</div>
          </div>
          <div class="section-note">按每次分析保存历史记录。这里不重复渲染工作台组件，所有下载按钮都绑定独立 run_id。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    runs = list_manifests()
    if not runs:
        st.info("还没有历史记录。完成一次文档生成或课堂视频分析后，这里会显示可复用的产物档案。")
        return

    pinned = next((item for item in runs if item.get("pinned")), None)
    if pinned:
        st.success(f"课堂展示版本：{pinned.get('title', pinned.get('run_id'))}")
        _render_manifest_downloads(pinned, "pinned")

    selected_filter = st.radio(
        "记录筛选",
        ["全部", "文档生成", "视频分析", "已固定", "失败记录"],
        index=0,
        horizontal=True,
        key="asset_history_filter",
    )
    filtered = _filter_runs(runs, selected_filter)
    if not filtered:
        st.info("当前筛选条件下没有记录。")
        return

    labels = [_run_label(item) for item in filtered]
    selected_label = st.selectbox("历史记录", labels, key="asset_history_select")
    selected = filtered[labels.index(selected_label)]

    left, right = st.columns([0.9, 1.1])
    with left:
        st.markdown("#### 历史记录")
        for item in filtered[:12]:
            status = item.get("status", "unknown")
            type_label = "文档生成" if item.get("type") == "document" else "视频分析"
            pinned_mark = " · 已固定" if item.get("pinned") else ""
            st.markdown(
                f"""
                <div class="marker-card">
                  <strong>{html.escape(str(item.get('title') or item.get('run_id')))}</strong><br>
                  <span>{type_label} · {html.escape(str(status))}{pinned_mark}</span><br>
                  <span>{html.escape(str(item.get('created_at', '')))} · {file_size_text(int(item.get('size_bytes', 0)))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with right:
        _render_history_detail(selected)


def render_run_details_center(state: dict[str, Any] | None) -> None:
    state = normalize_execution_state(state)
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Run diagnostics</div>
            <div class="section-title">运行详情</div>
          </div>
          <div class="section-note">查看 Agent 决策、执行轨迹、校验结果、错误修复和中间内容，适合排查生成质量或 API 问题。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not state:
        st.info("还没有可查看的运行记录。运行文档生成或课堂视频分析后，这里会显示 Agent 决策、执行日志和校验详情。")
        return
    if state.get("errors"):
        st.error("最近一次流程执行时遇到问题。")
        for error in state["errors"]:
            st.error(error)
        if state.get("logs"):
            with st.expander("查看已完成日志"):
                for log in state.get("logs", []):
                    st.write(f"- {log}")
    render_details(state)


def render_course_video_analysis(report: dict[str, Any]) -> None:
    analysis = report.get("analysis", {})
    markers = report.get("markers", [])
    highlights = report.get("highlights", [])

    col1, col2, col3 = st.columns(3)
    with col1:
        download_button("下载分析报告", report["analysis_markdown"], "text/markdown", "course_video_analysis_md")
    with col2:
        download_button("下载字幕 SRT", report["subtitles_path"], "text/plain", "course_video_srt")
    with col3:
        download_button("下载时间戳 JSON", report["markers_path"], "application/json", "course_video_markers_json")

    left, right = st.columns([1.05, 0.95])
    with left:
        st.markdown("#### 课程内容总结")
        summary_text = str(analysis.get("summary") or report.get("summary") or "")
        highlighted_summary = _highlight_html(summary_text, report.get("keywords", []))
        st.markdown(highlighted_summary, unsafe_allow_html=True)

        st.markdown("#### 核心知识点")
        for item in analysis.get("key_points", [])[:10]:
            st.markdown(
                f"""
                <div class="keypoint-card">
                  <strong>{html.escape(str(item.get('title', '知识点')))}</strong><br>
                  <span>{html.escape(str(item.get('explanation', '')))}</span><br>
                  <span>证据：{html.escape(str(item.get('evidence', '')))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        st.markdown("#### 思维导图")
        mindmap_path = Path(report.get("mindmap_visual", ""))
        if mindmap_path.exists() and mindmap_path.suffix.lower() == ".png":
            st.image(str(mindmap_path), use_container_width=True)
        elif mindmap_path.exists():
            st.code(mindmap_path.read_text(encoding="utf-8"), language="mermaid")
        download_button("下载视频思维导图", mindmap_path, "image/png" if mindmap_path.suffix.lower() == ".png" else "text/plain", "course_video_mindmap")

    st.markdown("#### 重点时间戳")
    render_marker_timeline(markers)
    render_marker_summary(markers)

    st.markdown("#### Highlight 重点片段")
    for item in highlights:
        quote = _highlight_html(str(item.get("quote", "")), item.get("tags", []) or report.get("keywords", []))
        start = seconds_to_clock(float(item.get("start", 0)))
        end = seconds_to_clock(float(item.get("end", 0)))
        reason = html.escape(str(item.get("reason", "")))
        st.markdown(
            f"""
            <div class="marker-card">
              <strong>{start} - {end}</strong><br>
              <span>{quote}</span><br>
              <span>{reason}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("查看分析 JSON"):
        st.json(report)


def _highlight_html(text: str, terms: list[str] | tuple[str, ...]) -> str:
    safe = html.escape(text)
    clean_terms = sorted({str(term).strip() for term in terms if str(term).strip()}, key=len, reverse=True)[:12]
    for term in clean_terms:
        safe_term = html.escape(term)
        safe = re.sub(f"({re.escape(safe_term)})", r"<mark>\1</mark>", safe)
    return safe


def render_video_toolkit() -> None:
    st.markdown(
        """
        <div class="section-head">
          <div>
            <div class="section-kicker">Lecture video workspace</div>
            <div class="section-title">课堂视频分析工作台</div>
          </div>
          <div class="section-note">上传老师课堂录屏或已有课程视频，识别/读取字幕后生成知识点总结、思维导图、重点时间戳和 Highlight 重点标记。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1])
    with left:
        analysis_video = st.file_uploader("上传课堂视频", type=["mp4", "mov", "mkv"], key="analysis_video_upload")
        analysis_srt = st.file_uploader("上传字幕 SRT（可选，推荐）", type=["srt"], key="analysis_srt_upload")
    with right:
        transcribe_if_missing = st.checkbox("未上传 SRT 时尝试本地语音识别", value=True)
        whisper_model_size = st.selectbox("本地识别模型", ["base", "small", "medium"], index=0)
        if whisper_model_size == "medium":
            st.warning("medium 模型占用更高，当前会隔离运行；课堂演示建议优先使用 base/small，或直接上传 SRT。")
        st.caption("如果本地没有安装 faster-whisper，仍可通过上传 SRT 完成分析。")

    if st.button("分析课堂视频并生成知识结构", use_container_width=True):
        if analysis_video is None:
            st.warning("请先上传课堂视频。")
        else:
            video_path = save_uploaded_file(analysis_video)
            srt_path = save_uploaded_file(analysis_srt) if analysis_srt is not None else None
            run_dir = None
            started = time.perf_counter()
            try:
                run_dir = create_run_dir("course_video", video_path)
                with st.spinner("正在识别字幕并分析课程知识点..."):
                    report = analyze_course_video(
                        str(video_path),
                        subtitle_path=str(srt_path) if srt_path else None,
                        output_dir=run_dir,
                        transcribe_if_missing=transcribe_if_missing,
                        whisper_model_size=whisper_model_size,
                    )
                report["run_id"] = run_dir.name
                report["output_dir"] = str(run_dir)
                report["timings"] = {"course_video_analysis": round(time.perf_counter() - started, 3)}
                artifacts = collect_artifacts(
                    run_dir,
                    [
                        "course_video_analysis.md",
                        "course_video_analysis.json",
                        "course_video_highlights.md",
                        "course_video_markers.json",
                        "course_video_mindmap.json",
                        "course_video_mindmap.png",
                        "course_video_mindmap.mmd",
                        "course_video_transcript.txt",
                        "course_video_auto_subtitles.srt",
                    ],
                )
                if srt_path:
                    artifacts["uploaded_subtitles.srt"] = str(srt_path)
                selected_tools = ["read_uploaded_subtitles" if srt_path else "transcribe_video", "analyze_course_video", "generate_video_mindmap"]
                plan = {
                    "goal": f"分析课堂视频：{Path(video_path).stem}",
                    "strategy": "课堂视频分析工作流",
                    "reasoning": "先获得字幕文本，再提炼知识点、重点时间戳、highlight 和思维导图，最后写入历史记录供课堂展示复用。",
                    "steps": [{"tool": tool, "name": _display_tool_name(tool)} for tool in selected_tools],
                }
                trace = [
                    {
                        "step": index,
                        "thought": f"课堂视频分析需要执行“{_display_tool_name(tool)}”。",
                        "action": tool,
                        "observation": TOOL_OBSERVATIONS.get(tool, "已完成该工具步骤。"),
                    }
                    for index, tool in enumerate(selected_tools, start=1)
                ]
                logs = [TOOL_OBSERVATIONS.get(tool, f"已完成 {_display_tool_name(tool)}。") for tool in selected_tools]
                logs.append("视频分析产物已写入历史记录。")
                report.update(
                    {
                        "type": "course_video",
                        "status": "success",
                        "title": Path(video_path).stem,
                        "source_file": str(video_path),
                        "subtitle_file": str(srt_path) if srt_path else "",
                        "artifacts": artifacts,
                        "selected_tools": selected_tools,
                        "plan": plan,
                        "trace": trace,
                        "logs": logs,
                        "errors": [],
                    }
                )
                write_manifest(
                    run_dir,
                    {
                        "type": "course_video",
                        "status": "success",
                        "title": Path(video_path).stem,
                        "source_file": str(video_path),
                        "subtitle_file": str(srt_path) if srt_path else "",
                        "artifacts": artifacts,
                        "selected_tools": selected_tools,
                        "plan": plan,
                        "trace": trace,
                        "logs": logs,
                        "timings": report["timings"],
                        "errors": [],
                    },
                )
                st.session_state["course_video_analysis_report"] = report
                st.session_state["active_detail_state"] = report
            except Exception as exc:
                if run_dir is not None:
                    failed_artifacts = collect_artifacts(
                        run_dir,
                        [
                            "course_video_analysis.md",
                            "course_video_analysis.json",
                            "course_video_highlights.md",
                            "course_video_markers.json",
                            "course_video_mindmap.json",
                            "course_video_mindmap.png",
                            "course_video_mindmap.mmd",
                            "course_video_transcript.txt",
                            "course_video_auto_subtitles.srt",
                        ],
                    )
                    selected_tools = ["read_uploaded_subtitles" if srt_path else "transcribe_video", "analyze_course_video", "generate_video_mindmap"]
                    plan = {
                        "goal": f"分析课堂视频：{Path(video_path).stem}",
                        "strategy": "课堂视频分析工作流",
                        "reasoning": "分析过程异常中断，仍保留已生成的中间产物和错误信息，便于继续排查。",
                        "steps": [{"tool": tool, "name": _display_tool_name(tool)} for tool in selected_tools],
                    }
                    trace = [
                        {
                            "step": index,
                            "thought": f"课堂视频分析需要执行“{_display_tool_name(tool)}”。",
                            "action": tool,
                            "observation": TOOL_OBSERVATIONS.get(tool, "已完成该工具步骤。"),
                        }
                        for index, tool in enumerate(selected_tools, start=1)
                    ]
                    write_manifest(
                        run_dir,
                        {
                            "type": "course_video",
                            "status": "failed",
                            "title": Path(video_path).stem,
                            "source_file": str(video_path),
                            "subtitle_file": str(srt_path) if srt_path else "",
                            "artifacts": failed_artifacts,
                            "selected_tools": selected_tools,
                            "plan": plan,
                            "trace": trace,
                            "logs": [f"课堂视频分析失败：{exc}"],
                            "timings": {"course_video_analysis": round(time.perf_counter() - started, 3)},
                            "errors": [str(exc)],
                        },
                    )
                st.error(str(exc))

    analysis_report = st.session_state.get("course_video_analysis_report")
    if analysis_report:
        st.success("课堂视频分析已完成。")
        st.video(analysis_report["source_video"])
        render_course_video_analysis(analysis_report)


inject_style()
api_settings = get_api_settings()
mode_name = "本地模式" if api_settings["mock_mode"] else "API 模式"
api_note = "未检测到 API Key" if not api_settings["api_key"] else "已检测到 API Key"

st.markdown(
    f"""
    <div class="topbar">
      <div>
        <div class="hero-kicker">CourseAgent Workspace</div>
        <h1>课程资料与课堂视频工作台</h1>
        <p>上传课程文档后，一键生成摘要、关键词、思维导图、PPT、讲稿、讲解视频、字幕、重点时间戳和运行报告；也可以分析课堂录屏，沉淀复习知识结构。</p>
        <div class="status-row">
          <span class="chip">文档一键生成</span>
          <span class="chip">课堂视频分析</span>
          <span class="chip">本地校验与修复</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="hero-panel-title">当前运行环境</div>
        <div class="metric-grid">
          <div class="metric-tile"><div class="metric-label">运行模式</div><div class="metric-value">{html.escape(mode_name)}</div></div>
          <div class="metric-tile"><div class="metric-label">API 状态</div><div class="metric-value">{html.escape(api_note)}</div></div>
          <div class="metric-tile"><div class="metric-label">模型</div><div class="metric-value">{html.escape(api_settings.get('model', ''))}</div></div>
          <div class="metric-tile"><div class="metric-label">输出目录</div><div class="metric-value">{html.escape(str(OUTPUT_DIR))}</div></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("运行控制")
    st.markdown(
        f"""
        <div class="sidebar-status">
          <div><span>供应商</span><strong>{html.escape(api_settings.get('provider', 'openai'))}</strong></div>
          <div><span>模式</span><strong>{html.escape(mode_name)}</strong></div>
          <div><span>模型</span><strong>{html.escape(api_settings['model'])}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("没有 API Key 时使用本地提取式规则；接入 API 后内容更自然，并继续经过原文一致性校验。")
    demo_clicked = st.button("使用交互设计示例演示", use_container_width=True)
    st.divider()
    st.subheader("API 配置")
    st.caption(f"Base URL：`{api_settings['base_url']}`")
    with st.expander("连接测试 / 临时配置"):
        provider_names = {
            "openai": "OpenAI",
            "gemini": "Google Gemini",
            "deepseek": "DeepSeek",
            "custom": "OpenAI-compatible Custom",
        }
        current_provider = api_settings.get("provider", "openai")
        provider_keys = list(provider_names.keys())
        provider_index = provider_keys.index(current_provider) if current_provider in provider_keys else 0
        test_provider = st.selectbox("供应商", provider_keys, index=provider_index, format_func=lambda key: provider_names[key])
        preset = PROVIDER_PRESETS[test_provider]
        default_models = {
            "openai": ["gpt-5.4-mini", "gpt-5.5", "gpt-5.4"],
            "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
            "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
            "custom": [api_settings["model"], "gpt-5.4-mini", "deepseek-chat", "qwen-plus"],
        }
        test_base_url = st.text_input("Base URL", value=preset["base_url"] if test_provider != "custom" else api_settings["base_url"])
        test_model = st.selectbox("模型", default_models[test_provider], index=0)
        test_api_type = st.selectbox("接口优先级", ["auto", "responses", "chat_completions"], index=["auto", "responses", "chat_completions"].index(preset["api_type"]))
        test_api_key = st.text_input("API Key（只用于本次运行，不会写入代码）", value="", type="password")
        st.caption("如果截图里曾露出 Key，建议去控制台删除并重新创建。")
        if st.button("测试 API 连接", use_container_width=True):
            with st.spinner("正在测试 API 连接..."):
                result = test_llm_connection(
                    api_key=test_api_key or api_settings["api_key"],
                    base_url=test_base_url,
                    model=test_model,
                    api_type=test_api_type,
                )
            if result.get("ok"):
                st.success(f"连接成功：{result.get('mode')} / {result.get('model')}")
            else:
                error_kind = result.get("error_kind", "")
                if error_kind == "quota_or_rate_limit":
                    st.warning(result.get("message", "供应商额度或频率限制，请稍后重试。"))
                    st.info("Gemini 免费层额度比较紧，测试连接和正式生成都会消耗请求。你可以等待额度恢复、切换模型，或暂时不填 Key 使用本地模式。")
                elif error_kind == "endpoint_key_mismatch":
                    st.error(result.get("message", "API Key 与 Base URL 不匹配。"))
                    st.info("如果使用 Google AI Studio 的 Gemini Key，请把供应商选为 Google Gemini，Base URL 保持 Gemini 预设。")
                elif error_kind == "invalid_key":
                    st.error(result.get("message", "API Key 未通过校验。"))
                elif error_kind == "local_encoding_error":
                    st.error(result.get("message", "本地编码异常。"))
                else:
                    st.warning(f"连接未成功：{result.get('message')}")
                if result.get("raw_message"):
                    with st.expander("查看原始错误"):
                        st.code(str(result["raw_message"]))
        if st.button("应用到本次运行", use_container_width=True):
            if not test_api_key and not api_settings["api_key"]:
                st.warning("请先输入 API Key，或在 .env 中配置 API Key。")
            else:
                os.environ["LLM_PROVIDER"] = test_provider
                os.environ["OPENAI_API_KEY"] = test_api_key or api_settings["api_key"]
                os.environ["OPENAI_BASE_URL"] = test_base_url
                os.environ["OPENAI_MODEL"] = test_model
                os.environ["LLM_API_TYPE"] = test_api_type
                os.environ["MOCK_MODE"] = "false"
                st.success("已应用到本次 Streamlit 会话。")
    st.divider()
    st.subheader("工作流")
    st.write("Planner -> Tool Executor -> Verifier -> Auto-Repair -> Report")
    st.subheader("支持格式")
    st.write(".txt / .docx / .pdf")

state = st.session_state.get("agent_state")
detail_state = st.session_state.get("active_detail_state") or state

document_tab, video_tab, assets_tab, details_tab = st.tabs(["课程文档生成", "课堂视频分析", "产物中心", "运行详情"])

with document_tab:
    render_document_workflow(demo_clicked)

with video_tab:
    render_video_toolkit()

with assets_tab:
    render_asset_center(state)

with details_tab:
    render_run_details_center(detail_state)
