from __future__ import annotations

import json
from typing import Any, Dict, List

from config import is_mock_mode
from tools.content_guard import contains_unrelated_project_terms, is_sparse_outline
from tools.local_content import _looks_like_klm, local_outline
from tools.llm_client import call_llm
from tools.mock_data import default_outline
from tools.prompt_loader import load_prompt


def generate_ppt_outline(
    text: str, summary: str, keywords: List[str], slide_count: int = 6
) -> Dict[str, Any]:
    """Generate a 5-minute defense PPT outline."""
    if is_mock_mode():
        return local_outline(text, summary, keywords, slide_count)
    prompt = load_prompt(
        "ppt_outline_prompt.txt",
        summary=summary,
        keywords=json.dumps(keywords, ensure_ascii=False),
        text_preview=text[:26000],
    )
    result = call_llm(prompt, expect_json=True, schema_name="ppt_outline", fallback=local_outline(text, summary, keywords, slide_count))
    if isinstance(result, dict) and "slides" in result:
        result["slides"] = result["slides"][: max(slide_count, 1)]
        if contains_unrelated_project_terms(result, text) or is_sparse_outline(result) or _domain_mismatch(result, text):
            return local_outline(text, summary, keywords, slide_count)
        return result
    return local_outline(text, summary, keywords, slide_count) or default_outline()


def _domain_mismatch(outline: Dict[str, Any], source_text: str) -> bool:
    if not _looks_like_klm(source_text):
        return False
    outline_text = json.dumps(outline, ensure_ascii=False).lower()
    required_signals = ["klm", "keystroke", "interface timings", "calculation rules", "rule 0", "temperature converter"]
    return sum(signal in outline_text for signal in required_signals) < 2 or "交互设计过程" in outline_text
