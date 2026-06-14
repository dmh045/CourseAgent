import os
from pathlib import Path
from typing import Any, Dict

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        """Allow config import before optional dependencies are installed."""
        return None


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(os.getenv("COURSEAGENT_RUNTIME_DIR", r"E:\CourseAgent"))
UPLOAD_DIR = Path(os.getenv("COURSEAGENT_UPLOAD_DIR", str(RUNTIME_DIR / "uploads")))
OUTPUT_DIR = Path(os.getenv("COURSEAGENT_OUTPUT_DIR", str(RUNTIME_DIR / "output")))
CACHE_DIR = Path(os.getenv("COURSEAGENT_CACHE_DIR", str(RUNTIME_DIR / "cache")))
RUNS_DIR = Path(os.getenv("COURSEAGENT_RUNS_DIR", str(OUTPUT_DIR / "runs")))
PROMPT_DIR = BASE_DIR / "prompts"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true" or not OPENAI_API_KEY

PROVIDER_PRESETS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.4-mini",
        "api_type": "auto",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "api_type": "chat_completions",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_type": "chat_completions",
    },
    "custom": {
        "label": "OpenAI-compatible Custom",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.4-mini",
        "api_type": "auto",
    },
}


def ensure_directories() -> None:
    """Create runtime directories used by the Streamlit app and Agent."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def get_api_settings() -> Dict[str, Any]:
    """Read API settings dynamically so UI/env updates are picked up at runtime."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    mock_mode = os.getenv("MOCK_MODE", "true").lower() == "true" or not api_key
    return {
        "provider": os.getenv("LLM_PROVIDER", "openai").lower(),
        "api_key": api_key,
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "mock_mode": mock_mode,
        "api_type": os.getenv("LLM_API_TYPE", "auto").lower(),
        "timeout": float(os.getenv("LLM_TIMEOUT", "60")),
    }


def is_mock_mode() -> bool:
    """Return whether the app should avoid network model calls."""
    return bool(get_api_settings()["mock_mode"])
