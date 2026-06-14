from __future__ import annotations

from typing import Any, Dict

from config import is_mock_mode
from tools.llm_client import call_llm
from tools.prompt_loader import load_prompt


def plan_task(user_goal: str, document_preview: str) -> Dict[str, Any]:
    """Use the model, or local rules, to create the execution plan."""
    fallback_plan = local_plan_task(user_goal, document_preview)
    if is_mock_mode():
        return fallback_plan

    prompt = load_prompt(
        "planner_prompt.txt",
        user_goal=user_goal,
        document_preview=document_preview[:1500],
    )
    result = call_llm(prompt, expect_json=True, schema_name="planner", fallback=fallback_plan)
    if isinstance(result, dict) and "steps" in result:
        return complete_plan_from_goal(result, user_goal, document_preview)
    return fallback_plan


def complete_plan_from_goal(plan: Dict[str, Any], user_goal: str, document_preview: str = "") -> Dict[str, Any]:
    """Merge model-proposed steps with locally required goal constraints."""
    required_plan = local_plan_task(user_goal, document_preview)
    existing_tools: list[str] = []
    merged_steps: list[dict[str, Any]] = []

    for step in plan.get("steps", []):
        tool = str(step.get("tool", "")).strip()
        if tool and tool not in existing_tools:
            existing_tools.append(tool)
            merged_steps.append(dict(step))

    added_tools = []
    for step in required_plan.get("steps", []):
        tool = step["tool"]
        if tool not in existing_tools:
            existing_tools.append(tool)
            added_tools.append(tool)
            merged_steps.append({**step, "description": f"{step['description']}（由目标约束自动补全）"})

    for index, step in enumerate(merged_steps, start=1):
        step["step_id"] = index

    completed = {
        **plan,
        "goal": plan.get("goal") or required_plan["goal"],
        "strategy": required_plan.get("strategy", plan.get("strategy", "动态工具调用")),
        "reasoning": (
            (plan.get("reasoning") or "模型生成初始计划。")
            + " 系统随后根据用户目标进行约束校正，确保显式要求的产物不会被遗漏。"
        ),
        "steps": merged_steps,
    }
    if added_tools:
        completed["auto_completed_tools"] = added_tools
    return completed


def local_plan_task(user_goal: str, document_preview: str = "") -> Dict[str, Any]:
    """Create a deterministic but goal-aware plan for local mode."""
    goal = user_goal or "整理课程资料"
    text = goal.lower()
    combined_text = f"{goal}\n{document_preview}".lower()

    explicit_brief_only = _contains_any(
        text,
        [
            "summary only",
            "only summary",
            "keywords only",
            "no ppt",
            "without ppt",
            "no video",
            "without video",
            "只要摘要",
            "仅摘要",
            "只生成摘要",
            "只要关键词",
            "只生成思维导图",
            "只要思维导图",
            "仅思维导图",
            "只生成导图",
            "只要导图",
            "仅导图",
            "不要ppt",
            "不用ppt",
            "不需要ppt",
            "不要视频",
            "不用视频",
            "不需要视频",
        ],
    )
    course_pack_context = _contains_any(
        combined_text,
        [
            "course",
            "lecture",
            "presentation",
            "ppt",
            "slide",
            "video",
            "mindmap",
            "subtitle",
            "timestamp",
            "klm",
            "keystroke-level model",
            "interface timings",
            "calculation rules",
            "temperature converter",
            "课程",
            "课堂",
            "课件",
            "答辩",
            "讲解",
            "讲稿",
            "幻灯片",
            "思维导图",
            "字幕",
            "时间戳",
            "交互",
            "效率模型",
        ],
    )
    wants_course_pack = bool(document_preview.strip()) and course_pack_context and not explicit_brief_only

    wants_all = _contains_any(text, ["全部", "完整", "一键", "全流程", "所有"])
    wants_all = wants_all or wants_course_pack
    wants_summary = wants_all or _contains_any(text, ["摘要", "总结", "概括", "整理", "答辩", "ppt", "presentation"])
    wants_keywords = wants_all or _contains_any(text, ["关键词", "重点词", "核心概念", "思维导图", "导图", "知识结构", "答辩", "ppt"])
    wants_mindmap = wants_all or _contains_any(text, ["思维导图", "导图", "知识结构", "结构图"])
    wants_ppt = wants_all or _contains_any(text, ["ppt", "演示", "幻灯片", "答辩", "presentation"])
    wants_script = wants_ppt or wants_all or _contains_any(text, ["讲稿", "讲解词", "演讲稿", "口播"])
    wants_video = wants_all or _contains_any(text, ["视频", "讲解视频", "mp4"])

    if _contains_any(text, ["字幕", "srt", "时间戳", "章节"]):
        wants_video = True

    if wants_mindmap or wants_ppt:
        wants_keywords = True
    if wants_ppt or wants_script or wants_video:
        wants_summary = True
        wants_keywords = True
        wants_ppt = True
        wants_script = True

    steps = [
        ("读取文档", "read_document", "读取上传文件并抽取纯文本，作为后续工具输入。"),
    ]
    if wants_summary:
        steps.append(("生成摘要", "generate_summary", "概括文档主题、核心内容和可答辩重点。"))
    if wants_keywords:
        steps.append(("提取关键词", "extract_keywords", "提取核心概念、方法、对象和应用场景。"))
    if wants_mindmap:
        steps.append(("生成思维导图", "generate_mindmap", "根据文档结构生成层级化知识导图。"))
    if wants_ppt:
        steps.append(("生成 PPT 大纲", "generate_ppt_outline", "组织适合课堂答辩的幻灯片结构。"))
    if wants_script:
        steps.append(("生成每页讲稿", "generate_slide_scripts", "为每页幻灯片生成口语化讲解词。"))
    if wants_ppt:
        steps.append(("生成 PPT 文件", "create_ppt", "把大纲、要点、导图和讲稿写入可下载 PPT。"))
    if wants_video:
        steps.append(("生成讲解视频", "create_video", "根据 PPT 大纲和讲稿生成字幕式讲解视频、字幕、章节和重点时间戳。"))

    if len(steps) == 1:
        steps.extend(
            [
                ("生成摘要", "generate_summary", "先给出文档摘要，帮助用户快速理解内容。"),
                ("提取关键词", "extract_keywords", "再提取关键词，形成可复用的学习线索。"),
            ]
        )

    return {
        "goal": goal,
        "strategy": _strategy_label(wants_ppt, wants_video, wants_mindmap),
        "reasoning": (
            "Planner 根据用户目标中的输出类型和下游依赖选择工具。"
            "例如视频需要先有 PPT 大纲和讲稿；PPT 需要摘要、关键词和结构化要点。"
        ),
        "steps": [
            {"step_id": index, "name": name, "tool": tool, "description": description}
            for index, (name, tool, description) in enumerate(steps, start=1)
        ],
    }


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word.lower() in text for word in words)


def _strategy_label(wants_ppt: bool, wants_video: bool, wants_mindmap: bool) -> str:
    if wants_video:
        return "答辩材料 + 讲解视频生成"
    if wants_ppt:
        return "答辩 PPT 生成"
    if wants_mindmap:
        return "知识结构整理"
    return "文档理解与摘要整理"
