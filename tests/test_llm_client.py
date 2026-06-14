from tools.llm_client import call_llm, parse_json_response, test_llm_connection as run_connection_test


def test_parse_json_response_from_fence() -> None:
    result = parse_json_response("```json\n{\"ok\": true}\n```", {"ok": False})

    assert result == {"ok": True}


def test_call_llm_mock_returns_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "true")
    result = call_llm("任意提示词", expect_json=True, fallback={"value": 1})

    assert result == {"value": 1}


def test_connection_without_key_is_mock_report(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_MODE", "true")

    result = run_connection_test(api_key="")

    assert result["ok"] is False
    assert result["mode"] == "mock"
