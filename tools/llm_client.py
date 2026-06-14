from __future__ import annotations

import json
import re
from typing import Any, Dict

from config import get_api_settings
from tools.mock_data import (
    default_keywords,
    default_mindmap,
    default_outline,
    default_plan,
    default_scripts,
    default_summary,
)


JSON_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "planner": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "goal": {"type": "string"},
            "strategy": {"type": "string"},
            "reasoning": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "step_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "tool": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["step_id", "name", "tool", "description"],
                },
            },
        },
        "required": ["goal", "strategy", "reasoning", "steps"],
    },
    "summary": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    },
    "keywords": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"keywords": {"type": "array", "items": {"type": "string"}}},
        "required": ["keywords"],
    },
    "mindmap": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "children": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "name": {"type": "string"},
                                    "children": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {"name": {"type": "string"}},
                                            "required": ["name"],
                                        },
                                    },
                                },
                                "required": ["name", "children"],
                            },
                        },
                    },
                    "required": ["name", "children"],
                },
            },
        },
        "required": ["title", "children"],
    },
    "ppt_outline": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "page": {"type": "integer"},
                        "title": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["page", "title", "bullets"],
                },
            },
        },
        "required": ["title", "slides"],
    },
    "slide_scripts": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scripts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "page": {"type": "integer"},
                        "title": {"type": "string"},
                        "script": {"type": "string"},
                    },
                    "required": ["page", "title", "script"],
                },
            }
        },
        "required": ["scripts"],
    },
}


DEFAULT_SYSTEM_PROMPT = (
    "你是课程资料整理助手。必须严格依据上传资料内容输出符合要求的 JSON，"
    "不要加入与资料无关的系统实现、项目说明或工具说明。"
)


def call_llm(
    prompt: str,
    system_prompt: str = "",
    expect_json: bool = False,
    schema_name: str | None = None,
    fallback: Any | None = None,
) -> str | dict:
    """
    Call an OpenAI or OpenAI-compatible model.

    Preferred path: Responses API with structured JSON schema.
    Compatibility path: Chat Completions with JSON response format.
    Mock path: deterministic local fallback.
    """
    if fallback is None:
        fallback = _mock_response(prompt)

    settings = get_api_settings()
    if settings["mock_mode"] or not settings["api_key"]:
        return fallback if expect_json else json.dumps(fallback, ensure_ascii=False)

    prompt = prompt[:30000]
    try:
        if settings["api_type"] in {"auto", "responses"}:
            text = _call_responses_api(prompt, system_prompt, schema_name, settings)
            return parse_json_response(text, fallback) if expect_json else text
    except Exception:
        if settings["api_type"] == "responses":
            return fallback if expect_json else json.dumps(fallback, ensure_ascii=False)

    try:
        text = _call_chat_completions(prompt, system_prompt, expect_json, schema_name, settings)
        return parse_json_response(text, fallback) if expect_json else text
    except Exception:
        return fallback if expect_json else json.dumps(fallback, ensure_ascii=False)


def test_llm_connection(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_type: str = "auto",
) -> Dict[str, Any]:
    """Return a small connection-test report without changing .env."""
    settings = get_api_settings()
    if api_key is not None:
        settings["api_key"] = api_key
    if base_url is not None:
        settings["base_url"] = base_url
    if model is not None:
        settings["model"] = model
    settings["api_type"] = api_type
    settings["mock_mode"] = not bool(settings["api_key"])

    if not settings["api_key"]:
        return {"ok": False, "mode": "mock", "message": "未提供 API Key，当前会使用本地模式。"}

    prompt = 'Output valid JSON only: {"ok": true, "message": "connected"}'
    fallback = {"ok": False, "message": "connection failed"}
    try:
        if settings["api_type"] in {"auto", "responses"}:
            text = _call_responses_api(prompt, "You are an API connectivity test assistant.", "connection", settings)
            data = parse_json_response(text, fallback)
            return {"ok": bool(data.get("ok")), "mode": "responses", "model": settings["model"], "message": data.get("message", "")}
    except Exception as exc:
        if settings["api_type"] == "responses":
            return {
                "ok": False,
                "mode": "responses",
                "model": settings["model"],
                **normalize_api_error(exc, settings),
            }

    try:
        text = _call_chat_completions(prompt, "You are an API connectivity test assistant.", True, "connection", settings)
        data = parse_json_response(text, fallback)
        return {"ok": bool(data.get("ok")), "mode": "chat_completions", "model": settings["model"], "message": data.get("message", "")}
    except Exception as exc:
        return {
            "ok": False,
            "mode": "chat_completions",
            "model": settings["model"],
            **normalize_api_error(exc, settings),
        }


def normalize_api_error(exc: Exception, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Turn provider exceptions into UI-friendly diagnostics."""
    raw = str(exc)
    raw_lower = raw.lower()
    base_url = str(settings.get("base_url", "")).lower()
    model = str(settings.get("model", ""))
    api_key = str(settings.get("api_key", ""))
    retry_after = _extract_retry_after(raw)

    if "invalid_api_key" in raw_lower or "incorrect api key" in raw_lower or "401" in raw:
        if api_key.startswith("AQ.") and "api.openai.com" in base_url:
            return {
                "error_kind": "endpoint_key_mismatch",
                "message": "当前像是把 Google Gemini API Key 填到了 OpenAI Base URL。请选择 Google Gemini，并使用 https://generativelanguage.googleapis.com/v1beta/openai/。",
                "raw_message": raw,
            }
        return {
            "error_kind": "invalid_key",
            "message": "API Key 未通过校验。请确认 Key 没有复制多余空格、没有被删除，并且供应商与 Base URL 匹配。",
            "raw_message": raw,
        }

    if "ascii" in raw_lower and "encode" in raw_lower:
        return {
            "error_kind": "local_encoding_error",
            "message": "本地请求编码遇到 ASCII 限制。已将连接测试改为纯英文内容；如果仍出现，请检查 Base URL/API Key 是否包含异常字符。",
            "raw_message": raw,
        }

    if "response_format" in raw_lower and "unavailable" in raw_lower:
        return {
            "error_kind": "response_format_unavailable",
            "message": "当前模型暂不支持 response_format 强制 JSON 参数。项目已改为对该供应商跳过该参数，并使用提示词与本地 JSON 解析兜底。",
            "raw_message": raw,
        }

    if "quota" in raw_lower or "rate limit" in raw_lower or "resource_exhausted" in raw_lower or "429" in raw:
        retry_text = f" 可等待约 {retry_after} 秒后再试。" if retry_after else " 可以稍后重试。"
        return {
            "error_kind": "quota_or_rate_limit",
            "retry_after_seconds": retry_after,
            "message": f"{model} 当前触发了供应商额度或频率限制。{retry_text}也可以切换到另一个模型，或暂时使用本地模式继续生成。",
            "raw_message": raw,
        }

    return {
        "error_kind": "generic_api_error",
        "message": f"API 连接失败：{raw}",
        "raw_message": raw,
    }


def _extract_retry_after(raw: str) -> int | None:
    retry_match = re.search(r"retry(?:Delay| in)?[^\d]{0,20}(\d+)", raw, flags=re.I)
    if retry_match:
        return int(retry_match.group(1))
    seconds_match = re.search(r"retry in ([0-9.]+)s", raw, flags=re.I)
    if seconds_match:
        return round(float(seconds_match.group(1)))
    return None


def parse_json_response(text: str, fallback: Any) -> Any:
    """Parse JSON from raw model text, including fenced Markdown blocks."""
    cleaned = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    return fallback


def _call_responses_api(prompt: str, system_prompt: str, schema_name: str | None, settings: Dict[str, Any]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"], timeout=settings["timeout"])
    kwargs: Dict[str, Any] = {
        "model": settings["model"],
        "input": [
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    schema = _schema_for(schema_name)
    if schema:
        kwargs["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name or "course_material_schema",
                "schema": schema,
                "strict": True,
            }
        }
    response = client.responses.create(**kwargs)
    return _extract_response_text(response)


def _call_chat_completions(
    prompt: str,
    system_prompt: str,
    expect_json: bool,
    schema_name: str | None,
    settings: Dict[str, Any],
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=settings["api_key"], base_url=settings["base_url"], timeout=settings["timeout"])
    if expect_json and _should_skip_response_format(settings):
        prompt = (
            f"{prompt}\n\n"
            "Return valid JSON only. Do not include Markdown fences, comments, or any explanatory text."
        )
    kwargs: Dict[str, Any] = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    schema = _schema_for(schema_name)
    if _should_skip_response_format(settings):
        pass
    elif schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name or "course_material_schema",
                "schema": schema,
                "strict": True,
            },
        }
    elif expect_json:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _should_skip_response_format(settings: Dict[str, Any]) -> bool:
    base_url = str(settings.get("base_url", "")).lower()
    provider = str(settings.get("provider", "")).lower()
    return provider == "deepseek" or "api.deepseek.com" in base_url


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def _schema_for(schema_name: str | None) -> Dict[str, Any] | None:
    if schema_name == "connection":
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"ok": {"type": "boolean"}, "message": {"type": "string"}},
            "required": ["ok", "message"],
        }
    if not schema_name:
        return None
    return JSON_SCHEMAS.get(schema_name)


def _mock_response(prompt: str) -> dict:
    if "任务规划器" in prompt or "执行计划" in prompt:
        return default_plan()
    if "关键词" in prompt:
        return default_keywords()
    if "思维导图" in prompt:
        return default_mindmap()
    if "PPT大纲" in prompt or "PPT 大纲" in prompt:
        return default_outline()
    if "每页讲稿" in prompt:
        return default_scripts()
    return default_summary()
