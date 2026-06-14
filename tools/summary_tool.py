from __future__ import annotations

from typing import Dict

from config import is_mock_mode
from tools.content_guard import contains_unrelated_project_terms
from tools.local_content import local_summary
from tools.llm_client import call_llm
from tools.mock_data import default_summary
from tools.prompt_loader import load_prompt


def generate_summary(text: str) -> Dict[str, str]:
    """Generate a 300-500 Chinese character summary for the course material."""
    if is_mock_mode():
        return local_summary(text)
    prompt = load_prompt("summary_prompt.txt", text=text[:26000])
    result = call_llm(prompt, expect_json=True, schema_name="summary", fallback=local_summary(text))
    if isinstance(result, dict) and "summary" in result and not contains_unrelated_project_terms(result, text):
        return result
    return local_summary(text) or default_summary()
