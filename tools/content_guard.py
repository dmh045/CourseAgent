from __future__ import annotations

import json
from typing import Any


PROJECT_TERMS = ["CourseAgent", "Agent", "Streamlit", "OpenAI", "LLM", "Mock", "python-pptx", "Graphviz"]


def source_allows_project_terms(source_text: str) -> bool:
    lowered = (source_text or "").lower()
    return any(term.lower() in lowered for term in PROJECT_TERMS)


def contains_unrelated_project_terms(value: Any, source_text: str) -> bool:
    """Return True when generated content mentions project/runtime terms absent from the source."""
    if source_allows_project_terms(source_text):
        return False
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    lowered = text.lower()
    return any(term.lower() in lowered for term in PROJECT_TERMS)


def is_sparse_outline(outline: dict[str, Any]) -> bool:
    slides = outline.get("slides", [])
    if not isinstance(slides, list) or len(slides) < 3:
        return True
    bullet_count = 0
    weak_words = {"Design", "Mock", "the", "核心内容概览", "关键词与知识结构"}
    for slide in slides:
        bullets = slide.get("bullets", []) if isinstance(slide, dict) else []
        bullet_count += len([item for item in bullets if str(item).strip()])
        for item in bullets:
            if str(item).strip() in weak_words:
                return True
    return bullet_count < len(slides) * 2


def is_sparse_mindmap(mindmap: dict[str, Any]) -> bool:
    children = mindmap.get("children", [])
    if not isinstance(children, list) or len(children) < 3:
        return True
    return _node_count(children) < 14


def _node_count(nodes: list[Any]) -> int:
    total = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        total += 1
        child_nodes = node.get("children", [])
        if isinstance(child_nodes, list):
            total += _node_count(child_nodes)
    return total
