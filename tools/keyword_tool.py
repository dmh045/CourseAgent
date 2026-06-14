from __future__ import annotations

from typing import Any, Dict

from config import is_mock_mode
from tools.content_guard import contains_unrelated_project_terms
from tools.local_content import local_keywords
from tools.llm_client import call_llm
from tools.mock_data import default_keywords
from tools.prompt_loader import load_prompt


def extract_keywords(text: str) -> Dict[str, Any]:
    """Extract 8-12 concise keywords from course material."""
    if is_mock_mode():
        return local_keywords(text)
    prompt = load_prompt("keyword_prompt.txt", text=text[:26000])
    result = call_llm(prompt, expect_json=True, schema_name="keywords", fallback=local_keywords(text))
    if isinstance(result, dict) and "keywords" in result and not contains_unrelated_project_terms(result, text):
        return result
    return local_keywords(text) or default_keywords()
