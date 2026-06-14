from __future__ import annotations

from typing import Any, Dict


def default_plan(user_goal: str = "生成5分钟课程答辩材料") -> Dict[str, Any]:
    return {
        "goal": user_goal or "生成5分钟课程答辩材料",
        "steps": [
            {"step_id": 1, "name": "读取文档", "tool": "read_document", "description": "读取用户上传的课程资料"},
            {"step_id": 2, "name": "生成摘要", "tool": "generate_summary", "description": "根据文档内容生成课程资料摘要"},
            {"step_id": 3, "name": "提取关键词", "tool": "extract_keywords", "description": "提取文档中的核心关键词"},
            {"step_id": 4, "name": "生成思维导图", "tool": "generate_mindmap", "description": "生成文档知识结构的思维导图"},
            {"step_id": 5, "name": "生成PPT大纲", "tool": "generate_ppt_outline", "description": "生成适合课堂答辩的PPT大纲"},
            {"step_id": 6, "name": "生成每页讲稿", "tool": "generate_slide_scripts", "description": "为每页PPT生成口语化讲解词"},
            {"step_id": 7, "name": "生成PPT文件", "tool": "create_ppt", "description": "根据大纲和讲稿生成PPT文件"},
            {"step_id": 8, "name": "生成讲解视频", "tool": "create_video", "description": "根据讲稿生成字幕式讲解视频"},
        ],
    }


def default_summary() -> Dict[str, str]:
    return {
        "summary": (
            "本课程资料围绕基于大语言模型 Agent 的课程文档自动整理系统展开，重点说明了项目背景、"
            "系统目标、技术路线和核心功能。系统面向课程期末答辩场景，用户上传课程资料并输入任务目标后，"
            "Agent 会自动规划执行步骤，依次调用文档解析、摘要生成、关键词提取、思维导图生成、PPT 大纲生成、"
            "讲稿生成和 PPT 文件生成等工具。项目采用 Streamlit 构建交互界面，以 Python 模块组织核心逻辑，"
            "并通过 Mock 模式保证在没有 API Key 的情况下仍可完成完整演示。该项目体现了 Agent 的计划、工具调用、"
            "状态记录和结果汇总能力，适合作为 AI 与文档自动化方向的课程作品。"
        )
    }


def default_keywords() -> Dict[str, list[str]]:
    return {
        "keywords": [
            "Agent",
            "文档自动化",
            "课程资料",
            "摘要生成",
            "关键词提取",
            "思维导图",
            "PPT生成",
            "讲稿生成",
            "Streamlit",
            "Mock模式",
        ]
    }


def default_mindmap() -> Dict[str, Any]:
    return {
        "title": "CourseAgent",
        "children": [
            {"name": "项目背景", "children": [{"name": "课程答辩"}, {"name": "资料整理"}, {"name": "效率提升"}]},
            {"name": "系统目标", "children": [{"name": "自动规划"}, {"name": "材料生成"}, {"name": "本地演示"}]},
            {"name": "Agent架构", "children": [{"name": "Planner"}, {"name": "Tool调用"}, {"name": "状态记录"}]},
            {"name": "核心功能", "children": [{"name": "摘要关键词"}, {"name": "思维导图"}, {"name": "PPT讲稿"}]},
            {"name": "运行测试", "children": [{"name": "Mock模式"}, {"name": "文件输出"}, {"name": "异常处理"}]},
        ],
    }


def default_outline() -> Dict[str, Any]:
    return {
        "slides": [
            {"page": 1, "title": "项目背景与意义", "bullets": ["课程资料整理重复且耗时", "AI 可以辅助内容理解和组织", "Agent 能把目标拆解为可执行流程"]},
            {"page": 2, "title": "系统目标与功能", "bullets": ["上传课程文档并读取文本", "生成摘要、关键词和思维导图", "自动生成 PPT 大纲、讲稿和文件"]},
            {"page": 3, "title": "Agent 系统架构", "bullets": ["Planner 负责生成任务计划", "Tool Executor 顺序调用工具模块", "State 记录中间结果和错误信息"]},
            {"page": 4, "title": "核心功能实现", "bullets": ["支持 txt、docx、pdf 文档读取", "Mock 与真实 API 共用同一接口", "使用 python-pptx 输出答辩 PPT"]},
            {"page": 5, "title": "运行测试结果", "bullets": ["无 API Key 时可完整演示", "输出文件统一保存到 output 目录", "界面可展示日志并下载结果"]},
            {"page": 6, "title": "总结与改进", "bullets": ["项目体现 Agent 的计划和工具调用思想", "后续可加入语音和视频生成", "可继续优化提示词和页面交互"]},
        ]
    }


def default_scripts(outline: Dict[str, Any] | None = None) -> Dict[str, Any]:
    slides = (outline or default_outline()).get("slides", [])
    scripts = []
    for slide in slides:
        title = slide.get("title", "")
        bullets = "、".join(slide.get("bullets", [])[:3])
        scripts.append(
            {
                "page": slide.get("page"),
                "title": title,
                "script": (
                    f"这一页介绍{title}。我会从{bullets}几个方面展开说明，帮助大家快速理解项目为什么要做、"
                    "系统做了什么，以及它如何通过 Agent 的任务规划和工具调用完成课程材料整理。"
                ),
            }
        )
    return {"scripts": scripts}
