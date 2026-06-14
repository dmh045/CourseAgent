from __future__ import annotations

from config import PROMPT_DIR


def load_prompt(name: str, **kwargs: object) -> str:
    """Load a prompt template from prompts/ and format it with keyword values."""
    template = (PROMPT_DIR / name).read_text(encoding="utf-8")
    return template.format(**kwargs)
