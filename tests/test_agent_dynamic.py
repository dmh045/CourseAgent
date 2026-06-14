from pathlib import Path

from agent_graph import run_agent
from tools.planner_tool import complete_plan_from_goal


def test_dynamic_goal_mindmap_only(tmp_path: Path) -> None:
    source = tmp_path / "course.txt"
    source.write_text("人工智能课程资料：介绍 Agent、工具调用、知识结构和课程复习。", encoding="utf-8")

    state = run_agent(str(source), "只生成思维导图")

    assert not state.get("errors")
    assert "generate_mindmap" in state.get("selected_tools", [])
    assert "create_ppt" not in state.get("selected_tools", [])
    assert "create_video" not in state.get("selected_tools", [])
    assert state.get("mindmap_image_path")
    assert not state.get("ppt_path")


def test_dynamic_goal_video_adds_dependencies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COURSEAGENT_ENABLE_TTS", "false")
    source = tmp_path / "course.txt"
    source.write_text("机器学习课程资料：介绍监督学习、模型评估、特征工程和项目答辩。", encoding="utf-8")

    state = run_agent(str(source), "生成答辩PPT和讲解视频")

    assert not state.get("errors")
    assert "generate_ppt_outline" in state.get("selected_tools", [])
    assert "generate_slide_scripts" in state.get("selected_tools", [])
    assert "create_ppt" in state.get("selected_tools", [])
    assert "create_video" in state.get("selected_tools", [])
    assert state.get("verification", {}).get("ok") is True
    assert Path(state["video_path"]).exists()


def test_llm_plan_is_completed_from_explicit_goal() -> None:
    weak_plan = {
        "goal": "整理课程资料",
        "steps": [
            {"step_id": 1, "name": "读取文档", "tool": "read_document", "description": "读取文档"},
            {"step_id": 2, "name": "生成摘要", "tool": "generate_summary", "description": "生成摘要"},
            {"step_id": 3, "name": "提取关键词", "tool": "extract_keywords", "description": "提取关键词"},
        ],
    }

    completed = complete_plan_from_goal(
        weak_plan,
        "请把这份课程资料整理成5分钟答辩PPT，并生成摘要、关键词、思维导图、每页讲稿和讲解视频。",
    )
    tools = [step["tool"] for step in completed["steps"]]

    assert "generate_mindmap" in tools
    assert "generate_ppt_outline" in tools
    assert "generate_slide_scripts" in tools
    assert "create_ppt" in tools
    assert "create_video" in tools
    assert completed["auto_completed_tools"]
