from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from config import is_mock_mode
from tools.content_guard import contains_unrelated_project_terms
from tools.local_content import local_scripts
from tools.llm_client import call_llm
from tools.mock_data import default_scripts
from tools.prompt_loader import load_prompt


def generate_slide_scripts(outline: Dict[str, Any]) -> Dict[str, Any]:
    """Generate classroom-defense narration for each PPT slide."""
    if is_mock_mode():
        return local_scripts(outline)
    prompt = load_prompt(
        "slide_script_prompt.txt",
        outline=json.dumps(outline, ensure_ascii=False, indent=2),
    )
    fallback = local_scripts(outline)
    result = call_llm(prompt, expect_json=True, schema_name="slide_scripts", fallback=fallback)
    if isinstance(result, dict) and "scripts" in result and not contains_unrelated_project_terms(result, json.dumps(outline, ensure_ascii=False)):
        return result
    return fallback or default_scripts(outline)


def save_speech_script(scripts: Dict[str, Any], output_path: str | Path) -> str:
    """Save slide scripts as a readable Markdown file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 每页讲稿", ""]
    for item in scripts.get("scripts", []):
        lines.extend(
            [
                f"## 第 {item.get('page', '')} 页：{item.get('title', '')}",
                "",
                item.get("script", ""),
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
